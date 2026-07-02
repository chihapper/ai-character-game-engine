"""Short-term memory: a rolling buffer of the most recent turns.

Kept verbatim and injected into every prompt so the character has immediate
conversational context. Older turns fall out of this buffer but are still
recoverable via long-term (vector) memory.
"""
from __future__ import annotations


class ShortTermMemory:
    def __init__(self, max_turns: int = 8) -> None:
        # One "turn" = one user message + one assistant reply (2 messages).
        self._max_messages = max_turns * 2
        self._messages: list[dict] = []

    def add_user(self, text: str) -> None:
        self._messages.append({"role": "user", "content": text})
        self._trim()

    def add_assistant(self, text: str) -> None:
        self._messages.append({"role": "assistant", "content": text})
        self._trim()

    def _trim(self) -> None:
        # Trim in CHUNKS, not one message at a time: a per-turn slide changes the history PREFIX
        # every turn, so the prompt-cache breakpoint the LLM adapter writes at the end of history
        # would never be read back once the buffer fills. Dropping two full turns at once keeps
        # the prefix byte-stable (cache HITS) between trims, at the cost of the window briefly
        # running two turns leaner.
        if len(self._messages) > self._max_messages:
            keep = max(2, self._max_messages - 4)
            self._messages = self._messages[-keep:]

    def messages(self) -> list[dict]:
        """A copy of the buffered messages, oldest first."""
        return list(self._messages)

    def clear(self) -> None:
        """Drop the live conversation buffer — e.g. a new session/scene begins after
        in-game time has passed. Durable state (long-term memory, relationship, intent)
        is untouched; only the verbatim recent-turns context resets."""
        self._messages = []
