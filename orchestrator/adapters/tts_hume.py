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
_HUME_PCM_RATE = 48000
_LEAD_TAG = re.compile(r"^\s*\[([^\[\]]{1,120})\]\s*")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_PAUSE_MARK = re.compile(r"\[(long )?pause\]", re.IGNORECASE)

# tone words that make a line linger after it lands
_HEAVY_TONES = ("quiet", "grief", "sad", "somber", "broken", "wounded", "tired",
                "distant", "cold", "hollow", "soft", "gentle", "wistful")


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

    def _utterances(self, text: str, voice_id: str) -> list[dict]:
        """Split a reply into per-sentence utterances with acting instructions.
        A leading [tag] sets the description from that sentence onward (Octave carries
        prosody forward on its own — we only re-state when the tone TURNS)."""
        out: list[dict] = []
        active_desc = ""
        m = _LEAD_TAG.match(text)
        if m:
            active_desc = m.group(1).strip()
            text = text[m.end():]
        sentences = [s for s in _SENTENCE_END.split(text) if s.strip()]
        for s in sentences:
            desc_new = False
            m = _LEAD_TAG.match(s)
            if m:
                active_desc = m.group(1).strip()
                desc_new = True
                s = s[m.end():]
            # keep [pause]/[long pause] (native markers) + non-verbal sounds; clean the rest
            pauses = {p.span(): p.group(0) for p in _PAUSE_MARK.finditer(s)}
            s = render_tags(s, "hume") if not pauses else s
            if not has_speakable(s) and not pauses:
                continue
            utt: dict = {"text": s.strip()}
            if active_desc and (desc_new or not out):
                utt["description"] = active_desc[:100]
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
            utt["trailing_silence"] = _trailing_silence(
                utt["text"], utt.get("description", ""), i == len(out) - 1)
        return out

    async def stream_speech(self, text: str, voice_id: str) -> AsyncIterator[bytes]:
        utterances = self._utterances(text, voice_id)
        if not utterances:
            return
        body = {"utterances": utterances, "format": {"type": "pcm"},
                "instant_mode": bool(voice_id)}
        headers = {"X-Hume-Api-Key": self._api_key, "Content-Type": "application/json"}
        carry = b""
        block = _HUME_PCM_RATE * 2 // 10   # resample in ~100ms blocks; stream stays a stream
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
            async with client.stream("POST", f"{_BASE_URL}/v0/tts/stream/file",
                                     json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread()).decode("utf-8", "replace")
                    raise RuntimeError(f"Hume TTS error {resp.status_code}: {detail[:300]}")
                async for chunk in resp.aiter_bytes():
                    carry += chunk
                    while len(carry) >= block:
                        yield _resample_to_wire(carry[:block])
                        carry = carry[block:]
        if carry:
            yield _resample_to_wire(carry)

    async def clone_voice(self, sample_audio: bytes, display_name: str) -> str:
        raise NotImplementedError("Hume voice cloning: create the voice in Hume's UI and use its id")
