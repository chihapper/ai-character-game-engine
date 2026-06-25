"""Adapter interfaces — the architectural spine.

Every external provider (speech-to-text, LLM, text-to-speech) sits behind one of
these abstract base classes. The pipeline depends only on these interfaces and
never on a concrete provider, so swapping Inworld for Cartesia, or Anthropic for
another LLM, is a one-file change with no pipeline edits.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class STTAdapter(ABC):
    """Speech-to-text: raw audio bytes in, transcript text out."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe a complete utterance. Returns the (possibly empty) transcript."""
        raise NotImplementedError


class LLMAdapter(ABC):
    """Large language model: a list of chat messages in, a stream of text deltas out."""

    @abstractmethod
    def stream_reply(self, messages: list[dict], system: str = "") -> AsyncIterator[str]:
        """Yield text deltas as they are generated.

        `messages` is a list of {"role": "user"|"assistant", "content": str} dicts.
        `system` is the system prompt, passed separately (most chat APIs, including
        Anthropic's, treat the system prompt as a distinct field, not a message).
        """
        raise NotImplementedError


class TTSAdapter(ABC):
    """Text-to-speech: a sentence + voice id in, a stream of audio chunks out.

    Implementations MUST yield raw PCM (signed 16-bit little-endian, mono) at the
    sample rate defined in `config.AUDIO_SAMPLE_RATE`, so the browser playback path
    is identical regardless of provider.
    """

    @abstractmethod
    def stream_speech(
        self,
        text: str,
        voice_id: str,
        *,
        emotion: str | None = None,
        speed: float | None = None,
        volume: float | None = None,
    ) -> AsyncIterator[bytes]:
        """Yield PCM audio chunks for `text` spoken in voice `voice_id`. Optional
        per-utterance expressivity (`emotion`, `speed`, `volume`) is rendered however
        the provider supports it; adapters ignore controls they can't honor."""
        raise NotImplementedError

    @abstractmethod
    async def clone_voice(self, sample_audio: bytes, display_name: str) -> str:
        """Instant-clone a voice from an audio sample; return the new voice id."""
        raise NotImplementedError
