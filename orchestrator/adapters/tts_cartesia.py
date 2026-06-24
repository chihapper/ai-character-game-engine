"""Cartesia TTS adapter (alternative provider, for A/B against Inworld).

Streaming synthesis over Cartesia's low-latency WebSocket, plus instant voice
cloning over REST. We request raw `pcm_s16le` at our canonical sample rate, so the
bytes we yield are byte-for-byte compatible with the Inworld path and the browser
player — swapping providers changes the voice, not the playback code.

Docs consulted:
  - wss://api.cartesia.ai/tts/websocket?cartesia_version=2026-03-01  (streaming)
  - POST https://api.cartesia.ai/voices/clone                         (instant clone)
Auth: WebSocket uses `X-API-Key`; REST uses `Authorization: Bearer`. Both require
the `Cartesia-Version` header/param.
"""
from __future__ import annotations

import base64
import json
import logging
import uuid
from typing import AsyncIterator

import httpx
import websockets

from ..config import AUDIO_SAMPLE_RATE, get_settings
from .base import TTSAdapter

logger = logging.getLogger(__name__)

_API_VERSION = "2026-03-01"
_WS_URL = f"wss://api.cartesia.ai/tts/websocket?cartesia_version={_API_VERSION}"
_CLONE_URL = "https://api.cartesia.ai/voices/clone"


class CartesiaTTS(TTSAdapter):
    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.cartesia_api_key:
            raise RuntimeError(
                "CARTESIA_API_KEY is not set. Add it to your .env file (sk_car_...)."
            )
        self._model = model or settings.cartesia_model
        self._api_key = settings.cartesia_api_key

    async def stream_speech(self, text: str, voice_id: str) -> AsyncIterator[bytes]:
        request = {
            "model_id": self._model,
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",  # 16-bit PCM, matches our wire format
                "sample_rate": AUDIO_SAMPLE_RATE,
            },
            "language": "en",
            "context_id": uuid.uuid4().hex,
            "continue": False,
            "max_buffer_delay_ms": 0,  # minimize latency
        }
        async with websockets.connect(
            _WS_URL, additional_headers={"X-API-Key": self._api_key}
        ) as ws:
            await ws.send(json.dumps(request))
            async for raw in ws:
                msg = json.loads(raw)
                msg_type = msg.get("type")
                if msg_type == "chunk":
                    data = msg.get("data")
                    if data:
                        yield base64.b64decode(data)
                elif msg_type == "done":
                    break
                elif msg_type == "error":
                    raise RuntimeError(f"Cartesia TTS error: {msg}")

    async def clone_voice(self, sample_audio: bytes, display_name: str) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Cartesia-Version": _API_VERSION,
        }
        files = {"clip": ("sample.wav", sample_audio, "audio/wav")}
        data = {"name": display_name, "language": "en"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            resp = await client.post(
                _CLONE_URL, headers=headers, files=files, data=data
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(
                    f"Cartesia clone error {resp.status_code}: {resp.text[:300]}"
                )
            voice_id = resp.json().get("id")
            if not voice_id:
                raise RuntimeError(f"Cartesia clone returned no id: {resp.text[:300]}")
            logger.info("Cloned Cartesia voice '%s' -> %s", display_name, voice_id)
            return voice_id
