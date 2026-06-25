"""Incremental sentence chunker.

This is the heart of the streaming-overlap requirement. As LLM text deltas arrive
token-by-token, we accumulate them and hand back *complete sentences* the moment
each one is ready — so TTS can start synthesizing sentence 1 while the LLM is still
generating sentence 2.

Usage (push/flush return `Segment(text, para_break)`):
    chunker = SentenceChunker()
    async for delta in llm_stream:
        for seg in chunker.push(delta):
            await tts.speak(seg.text)
    tail = chunker.flush()
    if tail:
        await tts.speak(tail.text)
"""
from __future__ import annotations

import re
from typing import NamedTuple


class Segment(NamedTuple):
    """A completed sentence plus whether a paragraph (blank-line) break followed
    it in the source text. The pipeline uses `para_break` to leave a longer beat
    of silence at paragraph boundaries than between sentences within a paragraph."""

    text: str
    para_break: bool


# Sentence-ending punctuation followed by whitespace, captured in two groups:
# (1) the punctuation run, (2) the trailing whitespace — so we can tell a within-
# paragraph break (a space) from a paragraph break (a blank line), AND tell a real
# sentence end from a mid-thought ellipsis. Kept simple and fast; perfect linguistic
# segmentation is not the goal — low latency to the *first* speakable chunk is.
_BOUNDARY = re.compile(r"([.!?]+)(\s+)")

# A blank line in the separator = a paragraph break (handles "\n\n", "\n \n").
_PARA_BREAK = re.compile(r"\n\s*\n")

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

    def push(self, delta: str) -> list[Segment]:
        """Add a text delta; return any newly-completed sentences (in order)."""
        if not delta:
            return []
        self._buf += delta
        out: list[Segment] = []
        search_start = 0

        while True:
            match = _BOUNDARY.search(self._buf, search_start)
            if match is None:
                break

            end = match.end()
            punct, sep = match.group(1), match.group(2)
            text_before_punct = self._buf[: match.start()]
            candidate = self._buf[:end].strip()
            para_break = bool(_PARA_BREAK.search(sep))

            # A mid-paragraph ellipsis ("...") is a trailing-off PAUSE, not a sentence
            # end. Cutting there strands the continuation as its own utterance, which a
            # per-utterance TTS (Inworld) renders with reset prosody — so the tail
            # ("...honey.") lands flat and robotic. Let it ride; the TTS voices the
            # pause itself. A paragraph break right after the ellipsis is still a real
            # boundary. (A unicode "…" isn't matched by _BOUNDARY at all, so it never
            # splits — same intent.)
            is_ellipsis = len(punct) >= 2 and set(punct) == {"."}

            # Skip false boundaries (abbreviations), tiny fragments, boundaries inside an
            # open `*stage direction*` (odd asterisk count so far), and mid-thought
            # ellipses. Splitting an action across sentences would strand a lone `*` on
            # each half, defeating clean_for_speech and letting the action be spoken.
            if (
                self._is_false_boundary(text_before_punct)
                or len(candidate) < _MIN_CHARS
                or candidate.count("*") % 2 == 1
                or (is_ellipsis and not para_break)
            ):
                search_start = end
                continue

            out.append(Segment(candidate, para_break))
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

    def flush(self) -> Segment | None:
        """Return whatever text remains (the final, unterminated sentence). It ends
        the reply, so there's no following break — para_break is always False."""
        tail = self._buf.strip()
        self._buf = ""
        return Segment(tail, False) if tail else None
