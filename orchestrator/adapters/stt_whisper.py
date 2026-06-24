"""Whisper STT adapter (local, free, cross-platform).

Concrete `STTAdapter` backed by faster-whisper. Endpointing in this app is
primarily click-to-talk (the browser decides when the user stopped), and we layer
Silero VAD on top server-side via faster-whisper's built-in `vad_filter`, which
trims non-speech before transcription for cleaner, faster results.

faster-whisper is CPU/GPU-bound and blocking, so we run it in a worker thread to
keep the event loop responsive.
"""
from __future__ import annotations

import asyncio
import io
import logging

from ..config import get_settings
from .base import STTAdapter

logger = logging.getLogger(__name__)


class WhisperSTT(STTAdapter):
    def __init__(self, model_size: str | None = None) -> None:
        settings = get_settings()
        self._model_size = model_size or settings.whisper_model
        self._device = settings.whisper_device
        self._compute_type = settings.whisper_compute_type
        self._model = None

    def _load(self):
        if self._model is None:
            # Imported lazily so the app boots even when the optional STT extra
            # (faster-whisper) isn't installed; voice input then surfaces a clear
            # error while text input keeps working.
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "Speech-to-text isn't installed. Run "
                    "`pip install -r requirements-optional.txt` to enable voice input."
                ) from exc
            logger.info(
                "Loading faster-whisper model '%s' (device=%s)...",
                self._model_size,
                self._device,
            )
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
        return self._model

    def _transcribe_sync(self, audio_bytes: bytes) -> str:
        model = self._load()
        # faster-whisper decodes the container (e.g. WebM/Opus from MediaRecorder)
        # via bundled ffmpeg/PyAV. `vad_filter=True` applies Silero VAD.
        segments, _info = model.transcribe(
            io.BytesIO(audio_bytes),
            vad_filter=True,
            beam_size=1,  # greedy: fastest, good enough for short utterances
        )
        return "".join(seg.text for seg in segments).strip()

    async def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes:
            return ""
        return await asyncio.to_thread(self._transcribe_sync, audio_bytes)
