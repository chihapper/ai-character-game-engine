"""Hume Octave TTS adapter (bake-off front-runner: emotion via natural-language direction).

Octave is an LLM-based voice, and its docs want structure, not a text blob:
  - MULTIPLE UTTERANCES in one request — prosody and voice continue across them, so we
    split a reply into sentences and let Octave breathe between them (the cadence fix).
  - `description` per utterance (<=100 chars, Octave 1): our leading [tone] tags become
    acting instructions per sentence — tone can TURN mid-reply, same as the face.
  - `trailing_silence` per utterance: how a line HANGS, derived from how the sentence
    ends and feels ("..." trails long; "!" snaps; grief lingers) — fluctuating delivery,
    not a fixed gap.
  - [pause] / [long pause] are native inline markers — kept verbatim in text.

Docs consulted (verified 2026-07): dev.hume.ai TTS overview / acting-instructions /
continuation / timestamps. POST /v0/tts/stream/file, X-Hume-Api-Key auth, PCM = 48 kHz
s16le mono -> resampled to our wire rate. Timestamps (word/phoneme, /stream/json v2)
exist for precise lip-sync alignment later. EVI (speech-to-speech, custom-LLM capable)
is a separate product — a Track V full-loop candidate, not this adapter.
"""
from __future__ import annotations

import logging
import re
from typing import AsyncIterator

import httpx
import numpy as np

from ..config import AUDIO_SAMPLE_RATE, get_settings
from ..expressivity import has_speakable, render_tags
from .base import TTSAdapter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.hume.ai"

# cross-TURN prosody continuation: Octave can continue from the previous generation, so a
# conversation keeps one emotional through-line instead of starting cold each reply.
# Keyed per voice (per character), module-level because adapters are constructed per call;
# TTL'd so a new scene doesn't inherit a stale mood.
_LAST_GENERATION: dict[str, tuple[str, float]] = {}
_CONTINUATION_TTL_S = 300.0
_HUME_PCM_RATE = 48000
_LEAD_TAG = re.compile(r"^\s*\[([^\[\]]{1,120})\]\s*")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_PAUSE_MARK = re.compile(r"\[(long )?pause\]", re.IGNORECASE)
_QUOTES = re.compile(r'("[^"]*"|“[^”]*”)')   # alternating narration/quoted split

# tone words that make a line linger after it lands
_HEAVY_TONES = ("quiet", "grief", "sad", "somber", "broken", "wounded", "tired",
                "distant", "cold", "hollow", "soft", "gentle", "wistful")
# stage business that explicitly TAKES TIME — the line before it must hang
_BEAT_WORDS = ("trails off", "falls silent", "silence", "long moment", "a moment", "beat",
               "pauses", "waits", "lingers", "says nothing", "lets it", "studies",
               "considers", "watches", "slowly", "turns away", "looks away", "sips",
               "drinks", "sets down", "fingers", "traces")


def _beat_silence(narration: str) -> float:
    """How much TIME a piece of between-lines stage business takes. Bigger business,
    longer beat; explicit hang-words ('trails off', 'a long moment') stretch it."""
    n = (narration or "").strip()
    if not n:
        return 0.0
    beat = min(1.6, 0.55 + len(n) / 130.0)
    if any(w in n.lower() for w in _BEAT_WORDS):
        beat += 0.7
    return round(min(beat, 2.6), 2)
# tone words that change pace (Octave speed: 0.5-2.0, 1.0 = neutral)
_SLOW_TONES = ("whisper", "quiet", "soft", "grief", "broken", "measured", "careful",
               "wistful", "to herself", "to himself")
_FAST_TONES = ("excited", "urgent", "panick", "frantic", "rushed", "breathless", "eager")


def _speed_for(description: str) -> float | None:
    d = (description or "").lower()
    if any(w in d for w in _SLOW_TONES):
        return 0.9
    if any(w in d for w in _FAST_TONES):
        return 1.1
    return None


def _consume_lead_tag(text: str) -> tuple[str | None, str]:
    """Consume a leading [tag] as an acting direction — EXCEPT pause marks, which are
    Octave-native inline markers kept verbatim in the text (module contract), never a
    description. A pause mark is skipped over (left in place) so a real tag right behind
    it still directs: "[pause] [warm] Easy now." -> ("warm", "[pause] Easy now.")."""
    kept = ""
    rest = text
    while True:
        m = _LEAD_TAG.match(rest)
        if not m:
            return None, text
        if _PAUSE_MARK.fullmatch(f"[{m.group(1).strip()}]"):
            kept += rest[: m.end()]
            rest = rest[m.end():]
            continue
        return m.group(1).strip(), kept + rest[m.end():]


def _compact_direction(narration: str) -> str:
    """Stage business -> a short acting instruction (Octave wants <=100 chars): keep the
    LAST sentence of the narration (the beat closest to the words) and trim."""
    n = (narration or "").strip().strip("*").strip()
    if not n:
        return ""
    sentences = [s.strip() for s in _SENTENCE_END.split(n) if s.strip()]
    if sentences:
        n = sentences[-1]
    n = n.rstrip(".")
    if len(n) > 100:
        n = n[:100].rsplit(" ", 1)[0].rstrip(",;")
    return n


def _resample_to_wire(pcm48: bytes) -> bytes:
    """48 kHz s16le mono -> AUDIO_SAMPLE_RATE, linear interp (plenty for speech)."""
    if not pcm48 or AUDIO_SAMPLE_RATE == _HUME_PCM_RATE:
        return pcm48
    x = np.frombuffer(pcm48[: len(pcm48) // 2 * 2], dtype=np.int16).astype(np.float32)
    n_out = int(len(x) * AUDIO_SAMPLE_RATE / _HUME_PCM_RATE)
    if n_out <= 0:
        return b""
    xp = np.linspace(0.0, 1.0, num=len(x), endpoint=False)
    xq = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.clip(np.interp(xq, xp, x), -32768, 32767).astype(np.int16).tobytes()


def _trailing_silence(sentence: str, description: str, is_last: bool) -> float:
    """How long the line hangs, from how it ends and how it feels. Seconds."""
    s = sentence.rstrip()
    if s.endswith(("...", "…", "—", "--")):
        gap = 0.9       # trailing off — let it hang
    elif s.endswith("!"):
        gap = 0.2       # snapped — move on
    elif s.endswith("?"):
        gap = 0.45      # leaving room for an answer
    else:
        gap = 0.35      # a natural period breath
    if any(w in (description or "").lower() for w in _HEAVY_TONES):
        gap += 0.3      # heavy feelings linger
    if is_last and gap < 0.5:
        gap = 0.5       # the reply's final beat always lands before the world moves
    return round(min(gap, 1.5), 2)


class HumeTTS(TTSAdapter):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.hume_api_key:
            raise RuntimeError("HUME_API_KEY is not set. Add it to your .env file.")
        self._api_key = settings.hume_api_key
        self._instant = settings.hume_instant

    def _utterances(self, text: str, voice_id: str) -> list[dict]:
        """A reply becomes per-sentence utterances with acting instructions, from BOTH
        sources the character gives us: leading [tags] AND the third-person stage
        business around the quotes ('she laughs softly, leaning in' — silenced as
        speech, delivered as direction; Octave is built to act stage directions).
        Octave carries prosody forward on its own — we only re-state on a TURN."""
        out: list[dict] = []
        active_desc = ""

        # narration/quoted alternation: narration becomes the NEXT quote's direction — and,
        # between or after quotes, a TIMED BEAT: stage business takes time, so the line
        # before it hangs for as long as the business plausibly lasts
        parts = _QUOTES.split(text or "")
        segments: list[tuple[str, str, str]] = []  # (spoken_text, direction, narration_raw)
        trailing_beat = 0.0
        pending_direction = ""
        pending_raw = ""
        any_quotes = any(i % 2 == 1 and p.strip() for i, p in enumerate(parts))
        if any_quotes:
            for i, p in enumerate(parts):
                if i % 2 == 0:
                    if p.strip():
                        pending_direction = _compact_direction(p)
                        pending_raw = p.strip()
                else:
                    q = p[1:-1].strip() if len(p) >= 2 else ""
                    if q:
                        segments.append((q, pending_direction, pending_raw))
                        pending_direction = ""
                        pending_raw = ""
            trailing_beat = _beat_silence(pending_raw)   # business AFTER the last line hangs it
        else:
            segments.append((text or "", "", ""))

        beat_boosts: dict[int, float] = {}   # utterance index -> minimum trailing silence
        for spoken, direction, narration_raw in segments:
            if out and narration_raw:
                # this stage business sits between the previous line and this one:
                # the PREVIOUS utterance holds while it happens
                beat_boosts[len(out) - 1] = max(beat_boosts.get(len(out) - 1, 0.0),
                                                _beat_silence(narration_raw))
            tag, spoken = _consume_lead_tag(spoken)
            if tag:  # an explicit [tag] outranks inferred stage business
                direction = tag
            if direction:
                active_desc = direction
            desc_new = bool(direction)
            for s in (x for x in _SENTENCE_END.split(spoken) if x.strip()):
                tag, s = _consume_lead_tag(s)
                if tag:
                    active_desc = tag
                    desc_new = True
                pauses = [p.group(0) for p in _PAUSE_MARK.finditer(s)]
                if pauses:
                    # pause marks stay verbatim (Octave-native) — but the REST of the
                    # sentence still passes the drop-risky-tags safety net: shield the
                    # pauses behind a placeholder, render, then put them back.
                    s = render_tags(_PAUSE_MARK.sub("\x00", s), "hume")
                    for mark in pauses:
                        s = s.replace("\x00", mark, 1)
                else:
                    s = render_tags(s, "hume")
                if not has_speakable(s) and not pauses:
                    continue
                utt: dict = {"text": s.strip()}
                if active_desc and (desc_new or not out):
                    utt["description"] = active_desc[:100]
                    speed = _speed_for(active_desc)
                    if speed:
                        utt["speed"] = speed
                    desc_new = False
                out.append(utt)
        if not out:
            return out
        if voice_id:
            # instant mode wants the voice on EVERY utterance (identity is stable anyway;
            # prosody still continues utterance-to-utterance within the request)
            is_id = bool(re.fullmatch(r"[0-9a-f\-]{36}", voice_id.lower()))
            voice = ({"id": voice_id, "provider": "CUSTOM_VOICE"} if is_id
                     else {"name": voice_id, "provider": "HUME_AI"})
            for utt in out:
                utt["voice"] = voice
        for i, utt in enumerate(out):
            silence = _trailing_silence(utt["text"], utt.get("description", ""), i == len(out) - 1)
            silence = max(silence, beat_boosts.get(i, 0.0))
            if i == len(out) - 1 and trailing_beat:
                silence = max(silence, trailing_beat)   # the reply's closing stage business
            utt["trailing_silence"] = round(silence, 2)
        return out

    async def stream_speech(self, text: str, voice_id: str) -> AsyncIterator[bytes]:
        """Streams via /v0/tts/stream/json — unlike /stream/file, it reports REAL errors
        (the file endpoint returns 200 + zero bytes on e.g. exhausted credits) and is the
        endpoint that carries generation_id (continuation) and timestamps when we want them."""
        import base64 as _b64
        import json as _json
        utterances = self._utterances(text, voice_id)
        if not utterances:
            return
        # instant mode measurably flattens the acting (furious/whisper energy ratio 1.5x vs
        # 2.7x full quality) — quality is the default; HUME_INSTANT=1 buys ~1s of latency back
        body = {"utterances": utterances, "format": {"type": "pcm"},
                "instant_mode": bool(voice_id) and self._instant}
        import time as _time
        prev = _LAST_GENERATION.get(voice_id)
        if prev and _time.monotonic() - prev[1] < _CONTINUATION_TTL_S:
            body["context"] = {"generation_id": prev[0]}   # carry the mood across turns
        headers = {"X-Hume-Api-Key": self._api_key, "Content-Type": "application/json"}
        first = True
        got_audio = False
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
            async with client.stream("POST", f"{_BASE_URL}/v0/tts/stream/json",
                                     json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread()).decode("utf-8", "replace")
                    raise RuntimeError(f"Hume TTS error {resp.status_code}: {detail[:300]}")
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = _json.loads(line)
                    except ValueError:
                        continue
                    if msg.get("error") or msg.get("message") and not msg.get("audio"):
                        _LAST_GENERATION.pop(voice_id, None)   # a failed context must not persist
                        raise RuntimeError(f"Hume TTS error: {str(msg)[:300]}")
                    gid = msg.get("generation_id")
                    if gid:
                        import time as _time
                        _LAST_GENERATION[voice_id] = (gid, _time.monotonic())
                    audio = msg.get("audio")
                    if not audio:
                        continue
                    pcm48 = _b64.b64decode(audio)
                    if first:
                        # Octave starts speech at sample zero; give the first word room to land
                        yield b"\x00\x00" * (AUDIO_SAMPLE_RATE * 15 // 100)
                        first = False
                    got_audio = True
                    yield _resample_to_wire(pcm48)
        if not got_audio:
            raise RuntimeError("Hume TTS returned no audio (check credits at platform.hume.ai/billing)")

    async def clone_voice(self, sample_audio: bytes, display_name: str) -> str:
        raise NotImplementedError("Hume voice cloning: create the voice in Hume's UI and use its id")
