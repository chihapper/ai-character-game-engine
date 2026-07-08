"""TTS provider registry — the single source of truth for "which text-to-speech, and how".

The engine has two provider-keyed seams (see architecture reminder in CLAUDE.md):
  1. PROMPTING — how the LLM is told to write deliverable text for a provider's markup, and how
     that markup is rendered/dropped. Lives on the per-provider VoiceProfile in expressivity.py
     (directive(), render_tags). THIS is what makes "pick Inworld → prompt for Inworld; switch to
     Hume → prompt for Hume" correct.
  2. TRANSPORT — turning that text into audio via the provider's API. A TTSAdapter subclass.

This registry ties those together with everything else a "bring-your-own-key, pick-your-TTS" flow
needs: the adapter factory, the required API-key env var(s), capability flags (so behavior is
driven by DECLARED capabilities, not `provider == "inworld"` string-checks scattered around the
codebase), and a readiness STATUS. A provider is only "ready" once its directive + adapter have
been VERIFIED against that provider's live docs (CLAUDE.md rule) — everything else is
"coming_soon" so a stranger's setup never gets an unverified, mis-prompted voice.

Add a provider = add ONE entry here (+ its adapter file + its VoiceProfile). Nothing else.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from .config import get_settings

if TYPE_CHECKING:
    from .adapters.base import TTSAdapter
    from .expressivity import VoiceProfile

READY = "ready"
COMING_SOON = "coming_soon"


@dataclass(frozen=True)
class TTSCaps:
    """What a provider can do — declared, so the pipeline/UI branch on capabilities not names."""
    streaming: bool = False        # yields PCM incrementally (vs one whole clip)
    batch: bool = False            # a run of same-tone sentences can share ONE request (Inworld:
                                   #   per-utterance prosody reset, so batching keeps intonation)
    continuation: bool = False     # carries prosody across TURNS (Hume Octave generation_id)
    voice_clone: bool = False      # can instant-clone a voice from an audio sample in-engine
    instant_mode: bool = False     # exposes a low-latency mode (trades acting fidelity)
    local: bool = False            # runs on our own hardware (no third-party key)


@dataclass(frozen=True)
class TTSProviderInfo:
    name: str                      # engine id (matches VoiceProfile.name and character.tts_provider)
    display_name: str              # human label for a picker
    status: str                    # READY | COMING_SOON
    key_env: tuple[str, ...]       # required API-key env var(s); () for local/no-key
    caps: TTSCaps
    make: Callable[[], "TTSAdapter"]   # lazy adapter factory (imports the adapter on call)
    notes: str = ""

    @property
    def ready(self) -> bool:
        return self.status == READY

    def profile(self) -> "VoiceProfile":
        from .expressivity import profile_for
        return profile_for(self.name)

    def missing_keys(self, settings=None) -> list[str]:
        """Required key env vars that are currently empty (settings field == env name lowercased)."""
        s = settings or get_settings()
        return [env for env in self.key_env if not getattr(s, env.lower(), "")]

    def has_keys(self, settings=None) -> bool:
        return not self.missing_keys(settings)

    def public_dict(self) -> dict:
        return {"name": self.name, "display_name": self.display_name, "status": self.status,
                "requires_keys": list(self.key_env), "has_keys": self.has_keys(),
                "capabilities": self.caps.__dict__, "notes": self.notes}


# ---- lazy adapter factories (import inside so the registry itself is import-cheap + cycle-free)

def _inworld():   from .adapters.tts_inworld import InworldTTS;      return InworldTTS()
def _hume():      from .adapters.tts_hume import HumeTTS;            return HumeTTS()
def _elevenlabs():from .adapters.tts_elevenlabs import ElevenLabsTTS;return ElevenLabsTTS()
def _cartesia():  from .adapters.tts_cartesia import CartesiaTTS;    return CartesiaTTS()
def _fish():      from .adapters.tts_fish import FishTTS;            return FishTTS()
def _chatterbox():from .adapters.tts_chatterbox import ChatterboxTTS;return ChatterboxTTS()


_REGISTRY: dict[str, TTSProviderInfo] = {
    "inworld": TTSProviderInfo(
        "inworld", "Inworld TTS", READY, ("INWORLD_API_KEY",),
        TTSCaps(streaming=True, batch=True, voice_clone=True), _inworld,
        "Leading bracket = natural-language steering; per-utterance, so same-tone runs are batched."),
    "hume": TTSProviderInfo(
        "hume", "Hume Octave", READY, ("HUME_API_KEY",),
        TTSCaps(streaming=True, continuation=True, instant_mode=True), _hume,
        "Acting via per-utterance description (Octave 1 pinned); prosody continues across turns."),
    # --- adapters exist but are NOT yet verified against their live docs → gated coming_soon ---
    "elevenlabs": TTSProviderInfo(
        "elevenlabs", "ElevenLabs v3", COMING_SOON, ("ELEVENLABS_API_KEY",),
        TTSCaps(streaming=True, voice_clone=True), _elevenlabs, "Inline audio tags anywhere in the line."),
    "cartesia": TTSProviderInfo(
        "cartesia", "Cartesia", COMING_SOON, ("CARTESIA_API_KEY",),
        TTSCaps(streaming=True, voice_clone=True), _cartesia, "Categorical tags only; also the outage fallback."),
    "fish": TTSProviderInfo(
        "fish", "Fish Audio", COMING_SOON, ("FISH_API_KEY",),
        TTSCaps(streaming=True), _fish, ""),
    "chatterbox": TTSProviderInfo(
        "chatterbox", "Chatterbox (self-hosted)", COMING_SOON, (),
        TTSCaps(streaming=True, local=True), _chatterbox, "Runs locally; no third-party key."),
}

_DEFAULT = "inworld"   # unknown provider names fall back here (matches the historical make_tts default)


# --------------------------------------------------------------------------- public API

def get_provider(name: str) -> TTSProviderInfo:
    return _REGISTRY.get(name) or _REGISTRY[_DEFAULT]


def list_providers(*, include_coming_soon: bool = True) -> list[TTSProviderInfo]:
    """All providers for a picker — ready ones first, then coming-soon."""
    items = [p for p in _REGISTRY.values() if include_coming_soon or p.ready]
    return sorted(items, key=lambda p: (not p.ready, p.display_name))


def ready_providers() -> list[TTSProviderInfo]:
    return [p for p in list_providers() if p.ready]


def caps(name: str) -> TTSCaps:
    return get_provider(name).caps


def make_tts(name: str) -> "TTSAdapter":
    """Construct the adapter for `name`. Unknown names fall back to the default provider (so a
    stale character sheet never crashes); a known-but-keyless provider surfaces the adapter's own
    'API key not set' error, which is the actionable message for a BYO-key user."""
    return get_provider(name).make()


# ---- bring-your-own-key: inject a user's key at runtime and refresh the cached settings ----

def set_provider_key(name: str, key: str) -> None:
    """Set a provider's API key for THIS process (BYO-key). Writes the env var(s) and clears the
    settings cache so the next make_tts() sees it. (Persisting/securing user keys is the caller's
    concern — this only wires an already-obtained key into the running engine.)"""
    prov = get_provider(name)
    for env in prov.key_env:
        os.environ[env] = key
    get_settings.cache_clear()   # lru_cache — force a re-read of the environment


async def validate_provider_key(name: str) -> tuple[bool, str]:
    """Cheaply prove a provider's key works by synthesizing one short word. Returns (ok, detail).
    Never raises — a bad key / outage comes back as (False, message)."""
    prov = get_provider(name)
    if prov.missing_keys():
        return False, f"missing key(s): {', '.join(prov.missing_keys())}"
    try:
        adapter = prov.make()
        got = False
        async for chunk in adapter.stream_speech("Test.", ""):
            if chunk:
                got = True
                break
        return (True, "ok") if got else (False, "no audio returned")
    except Exception as exc:  # noqa: BLE001 — validation must never explode
        return False, str(exc)[:200]
