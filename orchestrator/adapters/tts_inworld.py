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
_DESIGN_PATH = "/voices/v1/voices:design"
_PUBLISH_PATH = "/voices/v1/voices/{voice_id}:publish"


def _detect_audio_mime(data: bytes) -> str:
    """Best-effort container sniff so the browser can play the preview."""
    if data[:4] == b"RIFF":
        return "audio/wav"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if data[:4] == b"OggS":
        return "audio/ogg"
    return "audio/wav"


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
        self._delivery_mode = settings.inworld_delivery_mode
        self._temperature = settings.inworld_temperature

    async def stream_speech(self, text: str, voice_id: str) -> AsyncIterator[bytes]:
        payload = {
            "text": text,
            "voiceId": voice_id,
            "modelId": self._model,
            "audioConfig": {
                "audioEncoding": "LINEAR16",  # headerless 16-bit PCM
                "sampleRateHertz": AUDIO_SAMPLE_RATE,
            },
            # Keep the voice consistent across per-sentence calls.
            "deliveryMode": self._delivery_mode,
            "temperature": self._temperature,
        }
        headers = {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
        }
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
                    # Inworld wraps EVERY streamed chunk in its own WAV header, so
                    # we strip the header off each one (not just the first) — an
                    # un-stripped header plays as a click at every chunk boundary.
                    pcm = strip_wav_header(base64.b64decode(audio_b64))
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

    async def design_voice(
        self, description: str, preview_text: str, num_samples: int = 1
    ) -> list[dict]:
        """Design a voice from a text description. Returns preview voices, each a
        dict with `voice_id` (ephemeral until published), `audio_b64`, and `mime`."""
        payload = {
            "designPrompt": description,
            "langCode": "EN_US",
            "previewText": preview_text,
            "voiceDesignConfig": {"numberOfSamples": max(1, min(num_samples, 3))},
        }
        headers = {"Authorization": self._auth_header, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            resp = await client.post(
                f"{_BASE_URL}{_DESIGN_PATH}", json=payload, headers=headers
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Inworld voice-design error {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()
            # Field names vary across SDK/docs — be defensive.
            previews = (
                data.get("previewVoices")
                or data.get("voicePreviews")
                or data.get("voice_previews")
                or []
            )
            out: list[dict] = []
            for p in previews:
                vid = p.get("voiceId") or p.get("voice_id") or p.get("previewId")
                audio_b64 = p.get("previewAudio") or p.get("audioData") or p.get("audio_data")
                if not vid or not audio_b64:
                    continue
                mime = _detect_audio_mime(base64.b64decode(audio_b64))
                out.append({"voice_id": vid, "audio_b64": audio_b64, "mime": mime})
            if not out:
                raise RuntimeError(f"Inworld voice-design returned no previews: {data}")
            return out

    async def publish_voice(self, preview_voice_id: str, display_name: str) -> str:
        """Promote a designed preview voice into a permanent, reusable voice id."""
        url = f"{_BASE_URL}{_PUBLISH_PATH.format(voice_id=preview_voice_id)}"
        payload = {"displayName": display_name}
        headers = {"Authorization": self._auth_header, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Inworld publish error {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()
            voice_id = data.get("voiceId") or data.get("voice_id")
            if not voice_id:
                raise RuntimeError(f"Inworld publish returned no voiceId: {data}")
            logger.info("Published designed voice '%s' -> %s", display_name, voice_id)
            return voice_id
