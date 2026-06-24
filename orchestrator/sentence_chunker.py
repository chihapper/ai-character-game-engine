"""Incremental sentence chunker.

This is the heart of the streaming-overlap requirement. As LLM text deltas arrive
token-by-token, we accumulate them and hand back *complete sentences* the moment
each one is ready — so TTS can start synthesizing sentence 1 while the LLM is still
generating sentence 2.

Usage:
    chunker = SentenceChunker()
    async for delta in llm_stream:
        for sentence in chunker.push(delta):
            await tts.speak(sentence)
    tail = chunker.flush()
    if tail:
        await tts.speak(tail)
"""
from __future__ import annotations

import re

# Sentence-ending punctuation followed by whitespace. We deliberately keep this
# simple and fast; perfect linguistic segmentation is not the goal — low latency
# to the *first* speakable chunk is.
_BOUNDARY = re.compile(r"[.!?]+\s+")

# Tokens that end in a period but usually do not end a sentence. Guards against
# cutting "Mr. Smith" or "e.g. this" into fragments mid-stream.
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "a.m", "p.m", "no", "fig", "inc", "ltd", "co",
}

# Don't emit absurdly short fragments as their own TTS call; let them accumulate.
_MIN_CHARS = 2


class SentenceChunker:
    def __init__(self) -> None:
        self._buf = ""

    def push(self, delta: str) -> list[str]:
        """Add a text delta; return any newly-completed sentences (in order)."""
        if not delta:
            return []
        self._buf += delta
        out: list[str] = []
        search_start = 0

        while True:
            match = _BOUNDARY.search(self._buf, search_start)
            if match is None:
                break

            end = match.end()
            text_before_punct = self._buf[: match.start()]
            candidate = self._buf[:end].strip()

            # Skip false boundaries (abbreviations) and tiny fragments: leave them
            # in the buffer and keep scanning past this boundary for a real one.
            if self._is_false_boundary(text_before_punct) or len(candidate) < _MIN_CHARS:
                search_start = end
                continue

            out.append(candidate)
            self._buf = self._buf[end:]
            search_start = 0

        return out

    @staticmethod
    def _is_false_boundary(text_before_punct: str) -> bool:
        """True if the word right before the punctuation is a known abbreviation."""
        words = text_before_punct.split()
        if not words:
            return False
        last = words[-1].lower().strip(".")
        return last in _ABBREVIATIONS

    def flush(self) -> str | None:
        """Return whatever text remains (the final, unterminated sentence)."""
        tail = self._buf.strip()
        self._buf = ""
        return tail or None
