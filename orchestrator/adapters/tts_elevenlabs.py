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
from ..expressivity import has_speakable, render_tags
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
        self._ttv_model = settings.elevenlabs_ttv_model  # text-to-voice (voice design)
        # Low stability + non-zero style = the most emotional/variable delivery (the
        # "Creative/Natural" region for v3). These are the expressivity dials.
        self._stability = settings.elevenlabs_stability
        self._style = settings.elevenlabs_style

    async def stream_speech(
        self, text: str, voice_id: str
    ) -> AsyncIterator[bytes]:
        # render_tags keeps the model's tags ([sarcastic], [whispering], [laughs])
        # inline for v3 to act on, and drops physical stage directions.
        text = render_tags(text, "elevenlabs")
        if not has_speakable(text):
            return
        body = {
            "text": text,
            "model_id": self._model,
            "voice_settings": {
                "stability": self._stability,
                "similarity_boost": 0.75,
                "style": self._style,
                "use_speaker_boost": True,
            },
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

    async def list_voices(
        self, gender: str | None = None, q: str | None = None, limit: int = 100
    ) -> list[dict]:
        """List the account's voices (premade + owned) for the picker. On the free
        tier these are the only usable voices (shared-library voices are paid). Each
        has a public `preview_url` the browser can play directly (no auth)."""
        # Map the picker's gender values to ElevenLabs' label vocabulary.
        el_gender = {"feminine": "female", "masculine": "male", "gender_neutral": "neutral"}
        want_gender = el_gender.get((gender or "").lower(), (gender or "").lower())

        headers = {"xi-api-key": self._api_key}
        params: dict = {"page_size": str(max(1, min(limit, 100)))}
        if q:
            params["search"] = q
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
            resp = await client.get(f"{_BASE_URL}/v2/voices", headers=headers, params=params)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"ElevenLabs list-voices error {resp.status_code}: {resp.text[:200]}"
                )
            voices = resp.json().get("voices", [])

        out: list[dict] = []
        for v in voices:
            labels = v.get("labels") or {}
            g = (labels.get("gender") or "").lower()
            if want_gender and g and want_gender not in g:
                continue
            desc = v.get("description") or ", ".join(
                x for x in (labels.get("descriptive"), labels.get("accent"), labels.get("use_case")) if x
            )
            out.append(
                {
                    "id": v.get("voice_id"),
                    "name": v.get("name"),
                    "description": desc,
                    "gender": g or None,
                    "preview_url": v.get("preview_url"),
                    "is_owner": bool(v.get("is_owner")),
                }
            )
        return out

    async def design_voice(self, description: str, preview_text: str | None = None) -> list[dict]:
        """Design a voice from a text description. Returns preview voices, each a dict
        with `voice_id` (the ephemeral generated_voice_id), `audio_b64`, and `mime`.
        Same shape the Inworld adapter returns, so the API layer is provider-agnostic."""
        headers = {"xi-api-key": self._api_key, "Content-Type": "application/json"}
        body: dict = {"voice_description": description, "model_id": self._ttv_model}
        pt = (preview_text or "").strip()
        if 100 <= len(pt) <= 1000:  # preview text must be 100-1000 chars, else auto.
            body["text"] = pt
        else:
            body["auto_generate_text"] = True
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            resp = await client.post(
                f"{_BASE_URL}/v1/text-to-voice/design", headers=headers, json=body
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"ElevenLabs voice-design error {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()
        out: list[dict] = []
        for p in data.get("previews") or []:
            gid, audio = p.get("generated_voice_id"), p.get("audio_base_64")
            if gid and audio:
                out.append({"voice_id": gid, "audio_b64": audio, "mime": p.get("media_type") or "audio/mpeg"})
        if not out:
            raise RuntimeError(f"ElevenLabs voice-design returned no previews: {str(data)[:200]}")
        return out

    async def create_designed_voice(
        self, generated_voice_id: str, name: str, description: str
    ) -> str:
        """Promote a designed preview into a permanent, reusable voice id."""
        headers = {"xi-api-key": self._api_key, "Content-Type": "application/json"}
        body = {
            "voice_name": name,
            "voice_description": description or name,
            "generated_voice_id": generated_voice_id,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            resp = await client.post(f"{_BASE_URL}/v1/text-to-voice", headers=headers, json=body)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"ElevenLabs voice-create error {resp.status_code}: {resp.text[:300]}"
                )
            voice_id = resp.json().get("voice_id")
            if not voice_id:
                raise RuntimeError(f"ElevenLabs voice-create returned no voice_id: {resp.text[:200]}")
            logger.info("Created designed ElevenLabs voice '%s' -> %s", name, voice_id)
            return voice_id

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
