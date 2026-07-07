"""Deterministic CHECKS core (d20) — the interim authority on ability checks and the DM's tools.

Scope note: COMBAT (initiative, attacks, damage, death saves) lives in `srd/combat.py`
(`CombatEngine`) — this module's combat members were deleted when that engine shipped, so there is
exactly ONE attack implementation in the tree. What remains here: `ability_check` (used by the
door-force gate and the DM's `ability_check` tool) and the tool schemas. The full RAW check path
(proficiency/expertise/save profs, `srd.mechanics`) supersedes this module as SRD phases 3-6 land.

Surfaced to the DM as TOOLS (`tools()` → Anthropic function-call schemas) so a check fires
THROUGH the voiced conversation; the model narrates, the rules core decides the outcome.

Determinism: holds a SEEDED `random.Random` shared with the combat engine — one stream, never
module-level `random`. (Same-seed REPLAY is not a supported property: LLM outputs gate how many
draws the stream consumes, and the RNG state is not persisted in saves.)
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod

from pydantic import BaseModel

from .state import ABILITIES, Combatant


class CheckResult(BaseModel):
    roll: int                    # the raw d20
    modifier: int
    total: int
    dc: int
    success: bool
    critical: str = ""           # "" | "hit" (nat 20) | "miss" (nat 1)


class RulesEngine(ABC):
    """The interface everything else depends on. Swap or extend the implementation to add 5e
    depth; callers (door gate, DM) never see the change. Combat is NOT here — see srd/combat.py."""

    @abstractmethod
    def ability_check(self, actor: Combatant, ability: str, dc: int, *, advantage: int = 0) -> CheckResult: ...

    @abstractmethod
    def tools(self) -> list[dict]:
        """Anthropic tool-use schemas the DM/engine calls so mechanics resolve through the scene."""


def _parse_dice(spec: str) -> tuple[int, int]:
    """'2d6' -> (2, 6); 'd20' -> (1, 20)."""
    n, _, faces = spec.lower().partition("d")
    return int(n or 1), int(faces)


class D20Rules(RulesEngine):
    """The lightweight MVP ruleset. Deterministic via an injected seeded RNG."""

    def __init__(self, rng: random.Random | None = None, *, seed: int | None = None) -> None:
        self.rng = rng or random.Random(seed)

    # --- dice ---
    def roll(self, spec: str) -> int:
        n, faces = _parse_dice(spec)
        return sum(self.rng.randint(1, faces) for _ in range(n))

    def d20(self, advantage: int = 0) -> int:
        a, b = self.rng.randint(1, 20), self.rng.randint(1, 20)
        return max(a, b) if advantage > 0 else min(a, b) if advantage < 0 else a

    # --- resolutions ---
    def ability_check(self, actor, ability, dc, *, advantage=0) -> CheckResult:
        roll = self.d20(advantage)
        mod = actor.stats.mod(ability)
        total = roll + mod
        crit = "hit" if roll == 20 else "miss" if roll == 1 else ""
        # nat 20 auto-succeeds, nat 1 auto-fails (a light 5e-flavored touch; tune later)
        success = roll == 20 or (roll != 1 and total >= dc)
        return CheckResult(roll=roll, modifier=mod, total=total, dc=dc, success=success, critical=crit)

    def tools(self) -> list[dict]:
        return [
            {"name": "ability_check",
             "description": "Resolve a d20 ability check (roll + modifier vs a DC). Use for a skill "
                            "attempt, saving throw, or contest — the outcome is authoritative.",
             "input_schema": {"type": "object", "properties": {
                 "actor_id": {"type": "string", "description": "id of the acting combatant"},
                 "ability": {"type": "string", "enum": list(ABILITIES)},
                 "dc": {"type": "integer", "description": "difficulty class"},
                 "advantage": {"type": "integer", "enum": [-1, 0, 1],
                               "description": "-1 disadvantage, 0 none, 1 advantage"}},
                 "required": ["actor_id", "ability", "dc"]}},
        ]
