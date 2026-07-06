"""Deterministic rules core (d20) — the SOLE authority on mechanical outcomes.

Lightweight now (roll + modifier vs DC, simple attacks, initiative), but behind a clean
`RulesEngine` interface so it can grow toward BG3-depth 5e (full actions, conditions, spells,
reactions) later WITHOUT disturbing the map, DM, or engine-integration layers. Do not hard-wire
lightweight assumptions elsewhere — add depth HERE.

Surfaced to the DM/engine as TOOLS (`tools()` → Anthropic function-call schemas) so a check fires
THROUGH the voiced conversation; the model narrates, the rules core decides the outcome.

Determinism: the engine holds a SEEDED `random.Random` so a campaign is replayable and
save/load-safe — never call module-level `random`.
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


class AttackResult(BaseModel):
    hit: bool
    attack_roll: int
    attack_total: int
    target_ac: int
    damage: int = 0
    critical: str = ""
    target_id: str = ""
    target_hp: int = 0
    target_down: bool = False


class RulesEngine(ABC):
    """The interface everything else depends on. Swap or extend the implementation to add 5e
    depth; callers (map, DM, combat loop) never see the change."""

    @abstractmethod
    def ability_check(self, actor: Combatant, ability: str, dc: int, *, advantage: int = 0) -> CheckResult: ...

    @abstractmethod
    def attack(self, attacker: Combatant, target: Combatant, *, ability: str = "STR",
               damage_dice: str = "1d6", bonus: int = 0) -> AttackResult: ...

    @abstractmethod
    def roll_initiative(self, combatants: list[Combatant]) -> list[str]:
        """Return combatant ids in initiative order (also stamps each `.initiative`)."""

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

    def attack(self, attacker, target, *, ability="STR", damage_dice="1d6", bonus=0) -> AttackResult:
        roll = self.d20()
        mod = attacker.stats.mod(ability)
        total = roll + mod + bonus
        crit = "hit" if roll == 20 else "miss" if roll == 1 else ""
        hit = roll == 20 or (roll != 1 and total >= target.ac)
        dmg = 0
        if hit:
            dmg = max(1, self.roll(damage_dice) + mod + (self.roll(damage_dice) if roll == 20 else 0))
            target.hp = max(0, target.hp - dmg)
        return AttackResult(hit=hit, attack_roll=roll, attack_total=total, target_ac=target.ac,
                            damage=dmg, critical=crit, target_id=target.id, target_hp=target.hp,
                            target_down=not target.alive)

    def roll_initiative(self, combatants) -> list[str]:
        rolled = [(self.d20() + c.stats.mod("DEX"), c.id) for c in combatants]
        by_id = dict((cid, init) for init, cid in rolled)
        for c in combatants:
            c.initiative = by_id[c.id]
        rolled.sort(key=lambda t: (-t[0], t[1]))   # highest first; id tiebreak = deterministic
        return [cid for _, cid in rolled]

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
            {"name": "attack",
             "description": "Resolve one melee/ranged attack of an attacker against a target.",
             "input_schema": {"type": "object", "properties": {
                 "attacker_id": {"type": "string"}, "target_id": {"type": "string"},
                 "ability": {"type": "string", "enum": list(ABILITIES)},
                 "damage_dice": {"type": "string", "description": "e.g. '1d8'"}},
                 "required": ["attacker_id", "target_id"]}},
        ]
