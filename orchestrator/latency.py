"""Latency instrumentation for the voice loop.

Records wall-clock offsets (ms) from the moment the user stopped talking through to
first audio playback. This is both a debugging tool and a portfolio detail: it makes
the streaming-overlap budget visible — you can see the first audio chunk leave before
the full reply is generated.

Stages, in order:
    vad_stop          -> user finished speaking (t0)
    transcript_ready  -> STT produced a transcript
    llm_first_token   -> LLM emitted its first delta
    first_audio       -> first synthesized audio chunk left the server
    turn_complete     -> full reply generated + spoken
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class LatencyTracker:
    def __init__(self) -> None:
        self._t0: float | None = None
        self._marks: dict[str, float] = {}

    def start(self, stage: str = "vad_stop") -> None:
        self._t0 = time.perf_counter()
        self._marks = {stage: 0.0}

    def mark(self, stage: str) -> float:
        """Record `stage` as ms since t0; returns the offset."""
        if self._t0 is None:
            self.start(stage)
            return 0.0
        offset_ms = (time.perf_counter() - self._t0) * 1000.0
        self._marks[stage] = round(offset_ms, 1)
        return self._marks[stage]

    def summary(self) -> dict[str, float]:
        return dict(self._marks)

    def log(self, label: str = "turn") -> None:
        parts = " | ".join(f"{k}={v}ms" for k, v in self._marks.items())
        logger.info("latency[%s]: %s", label, parts)
