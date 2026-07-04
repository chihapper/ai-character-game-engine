"""Chatterbox TTS adapter (bake-off candidate: open source, self-hosted).

Resemble AI's MIT-licensed model, served by the tts-lab microservice on localhost
(its own Python 3.11 venv + torch — pinned deps stay out of the engine venv). Voice
identity = a reference clip path on disk (zero-shot cloning); `exaggeration` is its
one emotion dial, so tone tags don't render inline — expressivity comes from the dial
and the reference clip's character.

THE open question for this candidate is speed on the local GPU (GTX 1080 Ti, Pascal):
the service logs a realtime factor per request — that number decides its viability.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx
import numpy as np

from ..config import AUDIO_SAMPLE_RATE, get_settings
from ..expressivity import has_speakable, render_tags
from .base import TTSAdapter

logger = logging.getLogger(__name__)


class ChatterboxTTS(TTSAdapter):
    def __init__(self) -> None:
        settings = get_settings()
        self._url = settings.chatterbox_url.rstrip("/")
        self._exaggeration = settings.chatterbox_exaggeration
        self._cfg_weight = settings.chatterbox_cfg_weight

    async def stream_speech(self, text: str, voice_id: str) -> AsyncIterator[bytes]:
        text = render_tags(text, "chatterbox")
        if not has_speakable(text):
            return
        body = {"text": text, "voice": voice_id or "",
                "exaggeration": self._exaggeration, "cfg_weight": self._cfg_weight}
        # local model, no streaming: one clip back, resample if its rate differs
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
            resp = await client.post(f"{self._url}/tts", json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"Chatterbox error {resp.status_code}: {resp.text[:300]}")
            rate = int(resp.headers.get("X-Sample-Rate", AUDIO_SAMPLE_RATE))
            pcm = resp.content
        if rate != AUDIO_SAMPLE_RATE and pcm:
            x = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype=np.int16).astype(np.float32)
            n_out = int(len(x) * AUDIO_SAMPLE_RATE / rate)
            xp = np.linspace(0.0, 1.0, num=len(x), endpoint=False)
            xq = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
            pcm = np.clip(np.interp(xq, xp, x), -32768, 32767).astype(np.int16).tobytes()
        if pcm:
            yield pcm

    async def clone_voice(self, sample_audio: bytes, display_name: str) -> str:
        """A 'clone' here is just saving the reference clip; its path IS the voice id."""
        from pathlib import Path
        vdir = Path(__file__).resolve().parents[2] / "tts_voices"
        vdir.mkdir(exist_ok=True)
        path = vdir / f"{display_name.lower().replace(' ', '_')}.wav"
        path.write_bytes(sample_audio)
        logger.info("Chatterbox reference clip saved: %s", path)
        return str(path)
