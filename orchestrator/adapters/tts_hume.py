"""Hume Octave TTS adapter (bake-off candidate: emotion via natural-language direction).

Octave is an LLM-based voice: each utterance takes a free-text `description` of HOW the
line should sound ("wounded but hiding it, brittle cheer"). That maps beautifully onto
our engine's tone tags — the leading [bracket] direction becomes the description instead
of an inline token, so the whole tone-carry machinery drives it.

Docs consulted (verified 2026-07):
  - POST https://api.hume.ai/v0/tts/stream/file   (raw audio bytes, instant mode)
  - auth: X-Hume-Api-Key header. Body: {utterances: [{text, description, voice}], format}.
  - PCM output is 48 kHz s16le mono -> resampled here to our canonical rate.
Voice ids: use a Hume voice NAME (voice library) or a CUSTOM_VOICE id saved on the account.
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


class HumeTTS(TTSAdapter):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.hume_api_key:
            raise RuntimeError("HUME_API_KEY is not set. Add it to your .env file.")
        self._api_key = settings.hume_api_key

    async def stream_speech(self, text: str, voice_id: str) -> AsyncIterator[bytes]:
        # Octave wants the performance as a DESCRIPTION, not inline tokens: lift the
        # leading [tone] off the line, keep the words clean.
        description = None
        m = _LEAD_TAG.match(text)
        if m:
            description = m.group(1).strip()
            text = text[m.end():]
        text = render_tags(text, "hume")
        if not has_speakable(text):
            return
        utterance: dict = {"text": text}
        if description:
            utterance["description"] = description
        if voice_id:
            # a UUID means a saved custom voice; anything else is a library voice name
            is_id = bool(re.fullmatch(r"[0-9a-f\-]{36}", voice_id.lower()))
            utterance["voice"] = ({"id": voice_id, "provider": "CUSTOM_VOICE"} if is_id
                                  else {"name": voice_id, "provider": "HUME_AI"})
        body = {"utterances": [utterance], "format": {"type": "pcm"}, "instant_mode": bool(voice_id)}
        headers = {"X-Hume-Api-Key": self._api_key, "Content-Type": "application/json"}
        # resample in ~100ms blocks so the stream stays a stream
        carry = b""
        block = _HUME_PCM_RATE * 2 // 10
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
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
