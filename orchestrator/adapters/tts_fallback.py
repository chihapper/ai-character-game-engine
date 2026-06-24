"""Resilience wrapper: try a primary TTS, fall back to a secondary on failure.

If the primary provider hangs or errors before producing audio, we synthesize the
sentence with the fallback provider (a different voice) instead of leaving the
character silent. The failure is sticky for the rest of the session — once the
primary is known bad we go straight to the fallback, so we don't burn a timeout on
every sentence while a provider is down. A new session retries the primary (so the
app self-heals when the provider recovers).
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from .base import TTSAdapter

logger = logging.getLogger(__name__)


class FallbackTTS(TTSAdapter):
    def __init__(
        self, primary: TTSAdapter, fallback: TTSAdapter, fallback_voice: str
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._fallback_voice = fallback_voice
        self._primary_failed = False

    async def stream_speech(self, text: str, voice_id: str) -> AsyncIterator[bytes]:
        if not self._primary_failed:
            produced = False
            try:
                async for chunk in self._primary.stream_speech(text, voice_id):
                    produced = True
                    yield chunk
                return
            except Exception as exc:
                if produced:
                    # Already emitted partial audio for this sentence; don't replay.
                    logger.warning("Primary TTS failed mid-sentence: %s", exc)
                    return
                self._primary_failed = True
                logger.warning(
                    "Primary TTS failed before audio — using fallback for the rest "
                    "of this session: %s",
                    exc,
                )
        async for chunk in self._fallback.stream_speech(text, self._fallback_voice):
            yield chunk

    async def clone_voice(self, sample_audio: bytes, display_name: str) -> str:
        return await self._primary.clone_voice(sample_audio, display_name)
