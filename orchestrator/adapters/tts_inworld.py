"""Inworld TTS adapter (default provider).

Streaming synthesis over Inworld's NDJSON HTTP endpoint, plus instant voice
cloning. We ask Inworld for LINEAR16 PCM at our canonical sample rate so the bytes
we yield drop straight into the browser's audio player with no transcoding.

Docs consulted:
  - POST https://api.inworld.ai/tts/v1/voice:stream   (NDJSON streaming)
  - POST https://api.inworld.ai/voices/v1/voices:clone (instant clone)
Auth: `Authorization: Basic <INWORLD_API_KEY>` — the Portal's Base64 signature,
pasted verbatim (already base64-encoded; do not re-encode).
"""
from __future__ import annotations

import base64
import json
import logging
from typing import AsyncIterator

import httpx

from ..config import AUDIO_SAMPLE_RATE, get_settings
from .base import TTSAdapter
from ._audio import strip_wav_header

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.inworld.ai"
_STREAM_PATH = "/tts/v1/voice:stream"
_CLONE_PATH = "/voices/v1/voices:clone"


class InworldTTS(TTSAdapter):
    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.inworld_api_key:
            raise RuntimeError(
                "INWORLD_API_KEY is not set. Add it to your .env file "
                "(the Portal's Base64 signature, pasted verbatim)."
            )
        self._model = model or settings.inworld_model
        self._auth_header = f"Basic {settings.inworld_api_key}"

    async def stream_speech(self, text: str, voice_id: str) -> AsyncIterator[bytes]:
        payload = {
            "text": text,
            "voiceId": voice_id,
            "modelId": self._model,
            "audioConfig": {
                "audioEncoding": "LINEAR16",  # headerless 16-bit PCM
                "sampleRateHertz": AUDIO_SAMPLE_RATE,
            },
        }
        headers = {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
        }
        first_chunk = True
        # A generous read timeout: synthesis can take a moment for long sentences,
        # but connect should be quick.
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{_BASE_URL}{_STREAM_PATH}", json=payload, headers=headers
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise RuntimeError(
                        f"Inworld TTS error {resp.status_code}: {body[:300]}"
                    )
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    err = obj.get("error")
                    if err and err.get("code"):
                        raise RuntimeError(f"Inworld TTS stream error: {err}")
                    audio_b64 = (obj.get("result") or {}).get("audioContent")
                    if not audio_b64:
                        continue
                    pcm = base64.b64decode(audio_b64)
                    if first_chunk:
                        pcm = strip_wav_header(pcm)
                        first_chunk = False
                    if pcm:
                        yield pcm

    async def clone_voice(self, sample_audio: bytes, display_name: str) -> str:
        payload = {
            "displayName": display_name,
            "langCode": "EN_US",
            "voiceSamples": [
                {"audioData": base64.b64encode(sample_audio).decode("ascii")}
            ],
            "audioProcessingConfig": {"removeBackgroundNoise": True},
        }
        headers = {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            resp = await client.post(
                f"{_BASE_URL}{_CLONE_PATH}", json=payload, headers=headers
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Inworld clone error {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()
            voice_id = (data.get("voice") or {}).get("voiceId")
            if not voice_id:
                raise RuntimeError(f"Inworld clone returned no voiceId: {data}")
            logger.info("Cloned Inworld voice '%s' -> %s", display_name, voice_id)
            return voice_id
