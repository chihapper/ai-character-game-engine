"""Deterministic dice — a seedable RNG behind a small API.

Never module-level `random`: a campaign is replayable and save/load-safe, so every roll comes from
a held/injected `random.Random`. This is the one source of chance the whole rules system uses.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

_DICE = re.compile(r"^\s*(\d*)\s*[dD]\s*(\d+)\s*([+-]\s*\d+)?\s*$")


@dataclass
class Roll:
    total: int
    rolls: list[int] = field(default_factory=list)
    modifier: int = 0
    spec: str = ""


class Dice:
    """A seeded dice roller. `roll('2d6+1')`, `d20(advantage=1)`, etc."""

    def __init__(self, rng: random.Random | None = None, *, seed: int | None = None) -> None:
        self.rng = rng or random.Random(seed)

    def die(self, faces: int) -> int:
        return self.rng.randint(1, faces)

    def roll(self, spec: str) -> int:
        return self.roll_detail(spec).total

    def roll_detail(self, spec: str) -> Roll:
        """Parse + roll 'NdF+M' (N optional -> 1; +M optional). A bare integer is a constant."""
        s = str(spec).strip()
        m = _DICE.match(s)
        if not m:
            try:
                v = int(s)
                return Roll(total=v, rolls=[], modifier=v, spec=s)
            except ValueError as e:
                raise ValueError(f"bad dice spec: {spec!r}") from e
        n = int(m.group(1) or 1)
        faces = int(m.group(2))
        mod = int((m.group(3) or "0").replace(" ", ""))
        rolls = [self.die(faces) for _ in range(max(0, n))]
        return Roll(total=sum(rolls) + mod, rolls=rolls, modifier=mod, spec=s)

    def d20(self, advantage: int = 0) -> int:
        """A d20: advantage>0 rolls twice and takes the higher, <0 the lower, 0 a straight roll.
        (5e: advantage/disadvantage never stack, and one of each cancels to a straight roll — the
        caller nets the sources to a single -1/0/+1 before calling.)"""
        a = self.die(20)
        if advantage == 0:
            return a
        b = self.die(20)
        return max(a, b) if advantage > 0 else min(a, b)
