"""Evolving intent / short-term goals (issue #8): what the character is trying to DO right now.

Beyond their STATIC profile goals (standing wants), a character forms a SHORT-TERM intention
toward the current interaction — an agenda it pursues, sharpens, and abandons as the scene and
its feelings shift. Injected so the character acts PROACTIVELY (not merely reacts), and folded
into the arena query so recall serves the aim — RR: relevance is realized relative to the
agent's goals, so a dynamic goal is a dynamic frame. Character-aware: a schemer's intent is to
probe and use; a lonely flirt's is to be chosen. Updated in the background (folded into the
salience call), persisted per character.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings
from .base_store import atomic_write_text, lock_for, quarantine
from .base_store import safe_name as _safe_name


@dataclass
class IntentState:
    intent: str = ""  # the character's current short-term aim with the player / scene
    turns: int = 0

    def render(self) -> str:
        if not self.intent:
            return ""
        return (
            "# What you're trying to do right now\n"
            f"Beyond your standing goals, your immediate aim with the player is: {self.intent}\n"
            "Pursue it through what you say and do — proactively and in character. Don't announce it."
        )

    def query_hint(self) -> str:
        """Folded into the arena query so recall serves the current aim (RR-deepening)."""
        return self.intent

    def set(self, intent: str | None) -> None:
        intent = (intent or "").strip()
        if intent:
            self.intent = intent
        self.turns += 1

    def to_dict(self) -> dict:
        return {"intent": self.intent, "turns": self.turns}


class IntentStore:
    """One evolving short-term intent per character, persisted as JSON."""

    def __init__(self, namespace: str, *, readonly: bool = False) -> None:
        settings = get_settings()
        self.readonly = readonly
        self._path = Path(settings.memory_dir) / f"{_safe_name(namespace)}.intent.json"
        self._lock = lock_for(self._path)
        self._state: IntentState | None = None

    def get(self) -> IntentState:
        if self._state is None:
            self._state = self._load()
        return self._state

    def _load(self) -> IntentState:
        if not self._path.exists():
            return IntentState()
        try:
            d = json.loads(self._path.read_text(encoding="utf-8"))
            return IntentState(intent=str(d.get("intent", "")), turns=int(d.get("turns", 0)))
        except Exception as e:
            quarantine(self._path, f"unreadable intent state ({type(e).__name__})")  # loud, never silent
            return IntentState()

    def save(self) -> None:
        if self.readonly:
            return
        with self._lock:
            atomic_write_text(self._path, json.dumps(self.get().to_dict()))

    def update(self, intent: str | None) -> IntentState:
        if self.readonly:  # frozen: readonly state must not evolve even in memory
            return self.get()
        with self._lock:
            self.get().set(intent)
            self.save()
            return self._state
