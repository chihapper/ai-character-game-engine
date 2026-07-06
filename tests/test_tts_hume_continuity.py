"""Hume Octave cross-turn continuity scoping (concurrency fix).

Octave carries an emotional through-line across turns by echoing the previous generation_id
back as `context.generation_id`. That carry state used to be a MODULE-GLOBAL dict keyed only
by voice_id, so two concurrent sessions/scenes on the SAME NPC voice cross-contaminated each
other's mood (e.g. two people talking to Bri on the hosted ferry demo). The fix scopes the
carry to a per-session adapter INSTANCE and adds an explicit reset hook for a new scene.

These tests fake the Hume HTTP endpoint (no network, per the test seam) and inspect the exact
request body the adapter would send, which is where the bug was observable. No pytest-asyncio
in this repo, so the coroutines are driven with asyncio.run."""
import asyncio
import base64
import json

import httpx
import pytest

from orchestrator.adapters import tts_hume
from orchestrator.adapters.tts_hume import HumeTTS


class _FakeSettings:
    hume_api_key = "test-key"
    hume_instant = False


class _FakeResp:
    status_code = 200

    def __init__(self, lines):
        self._lines = lines

    async def aread(self):
        return b""

    async def aiter_lines(self):
        for ln in self._lines:
            yield ln


class _FakeStreamCtx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


class _FakeHume:
    """Stands in for httpx.AsyncClient. Records every request body and answers each call with a
    fresh, unique generation_id so we can trace exactly which id (if any) got echoed back."""

    def __init__(self, sent_bodies, counter):
        self._sent = sent_bodies
        self._counter = counter

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method, url, json=None, headers=None):  # body arrives as `json=`
        self._sent.append(json)                       # the body the adapter actually sent
        self._counter[0] += 1
        gid = f"gen-{self._counter[0]}"
        audio = base64.b64encode(b"\x00\x00" * 8).decode("ascii")
        line = _dumps({"generation_id": gid, "audio": audio})
        return _FakeStreamCtx(_FakeResp([line]))


def _dumps(obj):
    return json.dumps(obj)


@pytest.fixture
def hume_env(monkeypatch):
    """A HumeTTS whose settings are stubbed and whose HTTP client is the fake above. Returns
    (make_adapter, sent_bodies) — `sent_bodies` accumulates every request body sent, in order,
    across ALL adapters built in the test, so we can assert on cross-instance behaviour."""
    monkeypatch.setattr(tts_hume, "get_settings", lambda: _FakeSettings())
    sent_bodies: list = []
    counter = [0]
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **k: _FakeHume(sent_bodies, counter))
    return (lambda: HumeTTS()), sent_bodies


async def _drain(adapter, text, voice_id):
    async for _ in adapter.stream_speech(text, voice_id):
        pass


def _context_id(body):
    return (body.get("context") or {}).get("generation_id")


def test_continuity_carries_within_one_session(hume_env):
    make, sent = hume_env
    adapter = make()
    voice = "bri-voice"

    async def go():
        await _drain(adapter, "Hello there.", voice)
        await _drain(adapter, "How are you?", voice)

    asyncio.run(go())
    assert len(sent) == 2
    # first turn starts cold; the second echoes the first turn's generation_id
    assert _context_id(sent[0]) is None
    assert _context_id(sent[1]) == "gen-1"


def test_concurrent_sessions_same_voice_never_cross_contaminate(hume_env):
    """THE bug: two sessions, same NPC voice. Session B must never inherit session A's mood."""
    make, sent = hume_env
    a, b = make(), make()          # two concurrent sessions/scenes
    voice = "bri-voice"            # the SAME NPC voice in both

    async def go():
        await _drain(a, "A first line.", voice)   # -> gen-1, stored on A only
        await _drain(b, "B first line.", voice)   # -> gen-2, stored on B only
        await _drain(a, "A second line.", voice)  # must echo gen-1, NOT gen-2
        await _drain(b, "B second line.", voice)  # must echo gen-2, NOT gen-1

    asyncio.run(go())
    assert [_context_id(x) for x in sent] == [None, None, "gen-1", "gen-2"]
    # and the two instances hold independent maps
    assert a._last_generation[voice][0] == "gen-3"
    assert b._last_generation[voice][0] == "gen-4"


def test_reset_continuation_clears_the_carry(hume_env):
    make, sent = hume_env
    adapter = make()
    voice = "bri-voice"

    async def go():
        await _drain(adapter, "Before the cut.", voice)   # stores gen-1
        adapter.reset_continuation()                       # new scene / situate
        await _drain(adapter, "After the cut.", voice)     # must start cold again

    asyncio.run(go())
    assert _context_id(sent[0]) is None
    assert _context_id(sent[1]) is None                    # the reset worked


def test_reset_continuation_is_voice_scoped(hume_env):
    make, sent = hume_env
    adapter = make()
    voice = "bri-voice"

    async def go():
        await _drain(adapter, "One.", voice)              # stores gen-1
        await _drain(adapter, "Two.", voice)              # carries gen-1, stores gen-2
        adapter.reset_continuation("some-other-voice")    # unrelated voice — no effect here
        await _drain(adapter, "Three.", voice)            # still carrying gen-2

    asyncio.run(go())
    assert _context_id(sent[1]) == "gen-1"
    assert _context_id(sent[2]) == "gen-2"                # our voice's carry survived


def test_base_adapter_reset_is_a_safe_noop():
    """Drivers call reset_continuation() provider-agnostically; stateless adapters must ignore
    it without error (the base-class default)."""
    from orchestrator.adapters.base import TTSAdapter

    class _Stateless(TTSAdapter):
        async def stream_speech(self, text, voice_id):
            yield b""

        async def clone_voice(self, sample_audio, display_name):
            return "x"

    _Stateless().reset_continuation()             # no crash
    _Stateless().reset_continuation("bri-voice")  # no crash
