"""Dynamic relationship state (issue #6): how the player has moved a character.

A character's stance starts from their static `disposition`; this tracks how the ongoing
interaction has SHIFTED their feelings — warmth, trust, respect — plus an acute current mood.
Framing it as *movement from baseline* (not an absolute stance) means a fresh, unshaped state
is simply "unchanged" and doesn't fight the profile. Persisted per character, updated in the
background (folded into the salience call), and injected so the evolving relationship colors
responses. Character-aware: a guarded character moves slowly; a warm one warms fast.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings
from .long_term import _safe_name


def _word(v: float, low: str, mid: str, high: str) -> str:
    return low if v < 0.4 else (high if v > 0.6 else mid)


@dataclass
class RelationshipState:
    affection: float = 0.5  # 0.5 = unchanged from baseline; >0.6 warmer, <0.4 cooler
    trust: float = 0.5
    respect: float = 0.5
    mood: str = ""          # acute current feeling ("amused", "guarded", "stung", "furious")
    turns: int = 0          # how many exchanges have shaped this

    def render(self) -> str:
        """The injected 'how the player has affected you' section, or "" if nothing has
        shaped it yet (turn 0 — the static disposition still speaks for itself)."""
        if self.turns <= 0:
            return ""
        lines = [
            f"- Warmth toward them: {_word(self.affection, 'cooled', 'unchanged', 'grown warmer')}",
            f"- Trust in them: {_word(self.trust, 'eroded', 'unchanged', 'grown')}",
            f"- Respect for them: {_word(self.respect, 'fallen', 'unchanged', 'risen')}",
        ]
        if self.mood:
            lines.append(f"- Right now you feel: {self.mood}")
        return (
            "# How the player has affected you\n"
            "Your baseline is your disposition above; this interaction has moved you as below. "
            "Let it color your tone naturally, in character — don't narrate it.\n" + "\n".join(lines)
        )

    def apply(self, *, d_affection: float = 0.0, d_trust: float = 0.0,
              d_respect: float = 0.0, mood: str | None = None) -> None:
        clamp = lambda x: max(0.0, min(1.0, x))
        self.affection = clamp(self.affection + d_affection)
        self.trust = clamp(self.trust + d_trust)
        self.respect = clamp(self.respect + d_respect)
        if mood is not None:
            self.mood = mood.strip()
        self.turns += 1


class RelationshipStore:
    """One evolving relationship state per character (toward the player), persisted as JSON."""

    def __init__(self, namespace: str, *, readonly: bool = False) -> None:
        settings = get_settings()
        self.readonly = readonly
        self._path = Path(settings.memory_dir) / f"{_safe_name(namespace)}.relationship.json"
        self._state: RelationshipState | None = None

    def get(self) -> RelationshipState:
        if self._state is None:
            self._state = self._load()
        return self._state

    def _load(self) -> RelationshipState:
        if not self._path.exists():
            return RelationshipState()
        try:
            d = json.loads(self._path.read_text(encoding="utf-8"))
            return RelationshipState(
                affection=float(d.get("affection", 0.5)), trust=float(d.get("trust", 0.5)),
                respect=float(d.get("respect", 0.5)), mood=str(d.get("mood", "")),
                turns=int(d.get("turns", 0)),
            )
        except Exception:
            return RelationshipState()

    def save(self) -> None:
        if self.readonly:
            return
        s = self.get()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({
            "affection": s.affection, "trust": s.trust, "respect": s.respect,
            "mood": s.mood, "turns": s.turns,
        }), encoding="utf-8")

    def update(self, **deltas) -> RelationshipState:
        self.get().apply(**deltas)
        self.save()
        return self._state
