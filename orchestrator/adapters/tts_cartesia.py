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
from ..expressivity import has_speakable, render_tags
from .base import TTSAdapter
from ._audio import pcm_to_wav

logger = logging.getLogger(__name__)

_API_VERSION = "2026-03-01"
_WS_URL = f"wss://api.cartesia.ai/tts/websocket?cartesia_version={_API_VERSION}"
_CLONE_URL = "https://api.cartesia.ai/voices/clone"
_VOICES_URL = "https://api.cartesia.ai/voices"
_FILES_HOST = "https://files.cartesia.ai/"  # where preview audio is served
# Only ~a third of library voices ship a stored preview file; for the rest we
# synthesize this short line on demand so every voice can be auditioned.
_PREVIEW_TEXT = "Hi there — here's a quick sample of how I sound."


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
        # sonic-3.5 renders [laughter]; drop other tags it can't voice. (Cartesia is
        # deprecated here — no emotion control since the shared vocab was removed.)
        text = render_tags(text, "cartesia")
        if not has_speakable(text):
            return  # nothing left to say (e.g. an unsupported-only non-verbal line)
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

    async def list_voices(
        self,
        gender: str | None = None,
        q: str | None = None,
        language: str | None = "en",
        limit: int = 30,
    ) -> list[dict]:
        """Browse the Cartesia voice library (public presets + any we own). Unlike
        Inworld, Cartesia has no design-from-text — picking a library voice is how
        you 'choose a voice'. Returns lightweight dicts the picker UI renders, each
        with a `preview_url` (a playable audio file) so the user can audition it."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Cartesia-Version": _API_VERSION,
        }
        params: list[tuple[str, str]] = [
            ("limit", str(max(1, min(limit, 100)))),
            ("expand[]", "preview_file_url"),
        ]
        if language:
            params.append(("language", language))
        if gender:
            params.append(("gender", gender))
        if q:
            params.append(("q", q))
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
            resp = await client.get(_VOICES_URL, headers=headers, params=params)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Cartesia list-voices error {resp.status_code}: {resp.text[:300]}"
                )
            items = resp.json().get("data") or []
        return [
            {
                "id": v.get("id"),
                "name": v.get("name"),
                "description": v.get("description") or "",
                "gender": v.get("gender"),
                "language": v.get("language"),
                "preview_url": v.get("preview_file_url"),
                "is_owner": bool(v.get("is_owner")),
            }
            for v in items
            if v.get("id")
        ]

    async def fetch_preview(self, url: str) -> tuple[bytes, str]:
        """Fetch a library voice's preview audio. The `preview_file_url` from the
        list endpoint is auth-gated (401 without the key), so the browser can't load
        it directly — we proxy it here. Returns (audio_bytes, content_type). The host
        check is a hard guard: we attach our API key, so we must never fetch an
        arbitrary URL with it."""
        if not url.startswith(_FILES_HOST):
            raise ValueError("Preview URL must be a Cartesia files URL.")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Cartesia-Version": _API_VERSION,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Cartesia preview error {resp.status_code}: {resp.text[:200]}"
                )
            return resp.content, resp.headers.get("content-type", "audio/wav")

    async def synthesize_preview(self, voice_id: str) -> tuple[bytes, str]:
        """Render a short sample in `voice_id`, returned as a self-contained WAV.
        Used to preview library voices that have no stored preview file."""
        pcm = bytearray()
        async for chunk in self.stream_speech(_PREVIEW_TEXT, voice_id):
            pcm.extend(chunk)
        return pcm_to_wav(bytes(pcm), AUDIO_SAMPLE_RATE), "audio/wav"

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
