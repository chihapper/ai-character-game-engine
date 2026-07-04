"""Fish Audio TTS adapter (bake-off candidate: S2 Pro).

Plain REST: POST /v1/tts with Bearer auth and a `model` HEADER selecting s2-pro.
PCM out at our exact wire rate (their pcm is headerless s16le mono and takes a
sample_rate field) — no resampling needed. Voice = a fish.audio voice model id
(`reference_id`), from their library or a clone on the account.

Docs consulted (verified 2026-07): https://docs.fish.audio -> POST https://api.fish.audio/v1/tts
S2 Pro reads emotion markers like (angry) / (whispering) inline; we map our
[bracket] tags to that form rather than dropping them.
"""
from __future__ import annotations

import logging
import re
from typing import AsyncIterator

import httpx

from ..config import AUDIO_SAMPLE_RATE, get_settings
from ..expressivity import has_speakable, render_tags
from .base import TTSAdapter

logger = logging.getLogger(__name__)

_TTS_URL = "https://api.fish.audio/v1/tts"
_BRACKET = re.compile(r"\[([^\[\]]{1,60})\]")


class FishTTS(TTSAdapter):
    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.fish_api_key:
            raise RuntimeError("FISH_API_KEY is not set. Add it to your .env file.")
        self._api_key = settings.fish_api_key
        self._model = model or settings.fish_model

    async def stream_speech(self, text: str, voice_id: str) -> AsyncIterator[bytes]:
        text = render_tags(text, "fish")
        # S2 Pro's marker syntax is (parenthesized); convert surviving [tags]
        text = _BRACKET.sub(lambda m: f"({m.group(1).strip().lower()})", text)
        if not has_speakable(text):
            return
        body = {
            "text": text,
            "reference_id": voice_id or None,
            "format": "pcm",
            "sample_rate": AUDIO_SAMPLE_RATE,
            "latency": "balanced",
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "model": self._model,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            async with client.stream("POST", _TTS_URL, json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread()).decode("utf-8", "replace")
                    raise RuntimeError(f"Fish TTS error {resp.status_code}: {detail[:300]}")
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk

    async def clone_voice(self, sample_audio: bytes, display_name: str) -> str:
        """Create a voice model from a sample (their /model endpoint)."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        files = {"voices": ("sample.wav", sample_audio, "audio/wav")}
        data = {"title": display_name, "type": "tts", "train_mode": "fast"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            resp = await client.post("https://api.fish.audio/model", headers=headers,
                                     files=files, data=data)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Fish clone error {resp.status_code}: {resp.text[:300]}")
            vid = resp.json().get("_id") or resp.json().get("id")
            if not vid:
                raise RuntimeError(f"Fish clone returned no id: {resp.text[:200]}")
            logger.info("Cloned Fish voice '%s' -> %s", display_name, vid)
            return vid
