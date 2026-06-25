"""ElevenLabs TTS adapter (the expressive provider, for the emotion bake-off).

Streams over the HTTP endpoint with `output_format=pcm_{sample_rate}` — raw signed
16-bit little-endian mono PCM at our canonical rate, byte-for-byte compatible with
the Inworld/Cartesia paths and the browser player. We default to the `eleven_v3`
model because it is the only one that interprets inline AUDIO TAGS ([whispers],
[laughs], [angry], ...) — the whole point of using ElevenLabs here. v3 is alpha and
NOT a low-latency model; that's the deliberate trade for maximum expressivity.

Docs consulted (verified 2026-06):
  - POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream
  - audio tags: only `eleven_v3`. voice_settings: stability/similarity_boost/style.
Auth: `xi-api-key: <key>` (raw, no Bearer).
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx

from ..config import AUDIO_SAMPLE_RATE, get_settings
from ..expressivity import clamp, el_tag_for, has_speakable, render_tags
from .base import TTSAdapter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.elevenlabs.io"


class ElevenLabsTTS(TTSAdapter):
    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.elevenlabs_api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY is not set. Add it to your .env file."
            )
        self._api_key = settings.elevenlabs_api_key
        self._model = model or settings.elevenlabs_model
        # Low stability + non-zero style = the most emotional/variable delivery (the
        # "Creative/Natural" region for v3). These are the expressivity dials.
        self._stability = settings.elevenlabs_stability
        self._style = settings.elevenlabs_style

    async def stream_speech(
        self,
        text: str,
        voice_id: str,
        *,
        emotion: str | None = None,
        speed: float | None = None,
        volume: float | None = None,
    ) -> AsyncIterator[bytes]:
        # Keep free-form tags ([whispering], [nervous laugh]) for v3 to interpret.
        text = render_tags(text, "elevenlabs")
        if not has_speakable(text):
            return
        # Emotion becomes a leading v3 audio tag, e.g. "[angry] You think...".
        tag = el_tag_for(emotion)
        if tag:
            text = f"[{tag}] {text}"

        voice_settings: dict = {
            "stability": self._stability,
            "similarity_boost": 0.75,
            "style": self._style,
            "use_speaker_boost": True,
        }
        if speed is not None:
            voice_settings["speed"] = clamp(speed, 0.7, 1.2)

        body = {
            "text": text,
            "model_id": self._model,
            "voice_settings": voice_settings,
        }
        # pcm_<rate> is headerless s16le mono — drops straight into our player.
        url = (
            f"{_BASE_URL}/v1/text-to-speech/{voice_id}/stream"
            f"?output_format=pcm_{AUDIO_SAMPLE_RATE}"
        )
        headers = {"xi-api-key": self._api_key, "Content-Type": "application/json"}
        # v3 is not low-latency; allow a generous read window before first audio.
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread()).decode("utf-8", "replace")
                    raise RuntimeError(
                        f"ElevenLabs TTS error {resp.status_code}: {detail[:300]}"
                    )
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk

    async def clone_voice(self, sample_audio: bytes, display_name: str) -> str:
        url = f"{_BASE_URL}/v1/voices/add"
        files = {"files": ("sample.webm", sample_audio, "audio/webm")}
        data = {"name": display_name}
        headers = {"xi-api-key": self._api_key}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"ElevenLabs clone error {resp.status_code}: {resp.text[:300]}"
                )
            voice_id = resp.json().get("voice_id")
            if not voice_id:
                raise RuntimeError(f"ElevenLabs clone returned no voice_id: {resp.text[:300]}")
            logger.info("Cloned ElevenLabs voice '%s' -> %s", display_name, voice_id)
            return voice_id
