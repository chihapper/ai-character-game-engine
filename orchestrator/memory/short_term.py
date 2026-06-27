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
        if len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages :]

    def messages(self) -> list[dict]:
        """A copy of the buffered messages, oldest first."""
        return list(self._messages)

    def clear(self) -> None:
        """Drop the live conversation buffer — e.g. a new session/scene begins after
        in-game time has passed. Durable state (long-term memory, relationship, intent)
        is untouched; only the verbatim recent-turns context resets."""
        self._messages = []
