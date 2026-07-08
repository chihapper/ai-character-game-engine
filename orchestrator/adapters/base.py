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
    def stream_reply(
        self, messages: list[dict], system: str | list = "", *, cache_messages: bool = False
    ) -> AsyncIterator[str]:
        """Yield text deltas as they are generated.

        `messages` is a list of {"role": "user"|"assistant", "content": str} dicts.
        `system` is the system prompt, passed separately (most chat APIs, including
        Anthropic's, treat the system prompt as a distinct field, not a message); a
        list opts its FIRST segment (the stable prefix) into provider-side prompt
        caching where supported.
        `cache_messages` asks the provider to cache the conversation-history prefix —
        a cost/latency hint only, and a no-op for providers without prompt caching.
        """
        raise NotImplementedError


class FaceAnimAdapter(ABC):
    """Audio -> facial animation: PCM speech in, timestamped blendshape frames out.

    Provider-agnostic by construction: the input is the same PCM the TTS adapters
    emit, so swapping TTS (or moving to a full-loop provider) never touches this
    seam. The engine's chosen emotion is passed EXPLICITLY — the character's
    psychology overrides any audio-inferred mood (expression-relevance mechanic)."""

    @abstractmethod
    async def animate(
        self, pcm16: bytes, sample_rate: int,
        emotion: str | None = None, emotion_strength: float = 1.0,
        emotion_timeline: list[tuple[float, str, float]] | None = None,
    ) -> "FaceAnimResult":
        """Solve facial animation for a complete PCM16-mono clip.

        `emotion` is an engine-side tag (happy/sad/angry/fear/surprise/... or None
        for neutral); each adapter maps it to its provider's emotion space.
        `emotion_timeline` [(time_sec, tag, strength), ...] supersedes `emotion` and
        lets the performance TURN mid-clip (starts amused, hardens halfway)."""
        raise NotImplementedError


class FaceAnimResult:
    """Timestamped blendshape track for one spoken clip."""

    def __init__(self, blendshape_names: list[str],
                 frames: list[tuple[float, list[float]]],
                 emotions: list[tuple[float, dict[str, float]]] | None = None):
        self.blendshape_names = blendshape_names  # e.g. the ARKit-52 names
        self.frames = frames                      # [(time_sec, [weight per name]), ...]
        # provider's DETECTED per-window emotions [(time_sec, {name: weight}), ...] —
        # diagnostic gold for the TTS bake-off: how much feeling the audio actually carries
        self.emotions = emotions or []

    def to_dict(self) -> dict:
        return {"blendshape_names": self.blendshape_names,
                "frames": [{"t": t, "w": w} for t, w in self.frames],
                "detected_emotions": [{"t": t, "e": e} for t, e in self.emotions]}


class TTSAdapter(ABC):
    """Text-to-speech: a sentence + voice id in, a stream of audio chunks out.

    Implementations MUST yield raw PCM (signed 16-bit little-endian, mono) at the
    sample rate defined in `config.AUDIO_SAMPLE_RATE`, so the browser playback path
    is identical regardless of provider.
    """

    @abstractmethod
    def stream_speech(self, text: str, voice_id: str) -> AsyncIterator[bytes]:
        """Yield PCM audio chunks for `text` spoken in voice `voice_id`. The text may
        carry inline performance tags ([whispering], [laughs], ...); each adapter
        renders or drops them per its provider (see expressivity.render_tags)."""
        raise NotImplementedError

    @abstractmethod
    async def clone_voice(self, sample_audio: bytes, display_name: str) -> str:
        """Instant-clone a voice from an audio sample; return the new voice id."""
        raise NotImplementedError

    def reset_continuation(self, voice_id: str | None = None) -> None:
        """Lifecycle hint: a new scene/situate began — forget any cross-turn prosodic
        through-line carried for `voice_id` (or all voices if None), so the next line
        starts cold instead of inheriting the prior scene's mood. Stateless providers
        have nothing to forget and ignore this (the default no-op); a stateful one (Hume
        Octave continuation) overrides it. Continuity state is ALWAYS scoped to a single
        adapter instance, so this only ever resets THIS session — never a concurrent one."""
        return None
