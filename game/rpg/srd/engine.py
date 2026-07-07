"""Rules5e — the deterministic, tool-surfaced game-layer rules engine (SRD-based).

Extends the lightweight `D20Rules` toward BG3-depth: Phase 1 resolves checks / saves / skills;
combat, bestiary, encounters, and loot layer on in later phases behind this same object. The engine
RESOLVES every mechanical outcome; the DM/LLM narrates what it returns and never invents a result.
`tools()` surfaces the resolutions to the engine/DM as function-calls so mechanics fire through the
voiced conversation.
"""
from __future__ import annotations

import random

from . import mechanics as M
from .dice import Dice


class Rules5e:
    def __init__(self, rng: random.Random | None = None, *, seed: int | None = None) -> None:
        self.dice = Dice(rng=rng, seed=seed)

    # ---- resolutions (Phase 1: checks / saves / skills) ----
    def roll_check(self, sheet, ability: str, dc: int, *, proficient: bool = False,
                   expertise: bool = False, advantage: int = 0) -> M.CheckResult:
        return M.ability_check(self.dice, sheet, ability, dc, proficient=proficient,
                               expertise=expertise, advantage=advantage)

    def roll_skill(self, sheet, skill: str, dc: int, *, advantage: int = 0) -> M.CheckResult:
        return M.skill_check(self.dice, sheet, skill, dc, advantage=advantage)

    def roll_saving_throw(self, sheet, ability: str, dc: int, *, advantage: int = 0) -> M.CheckResult:
        return M.saving_throw(self.dice, sheet, ability, dc, advantage=advantage)

    def passive(self, sheet, skill: str) -> int:
        return M.passive_score(sheet, skill)

    def proficiency_bonus(self, sheet) -> int:
        return M.proficiency_bonus(sheet)

    # ---- tool schemas surfaced to the engine / DM (results are AUTHORITATIVE) ----
    def tools(self) -> list[dict]:
        adv = {"type": "integer", "enum": [-1, 0, 1],
               "description": "-1 disadvantage, 0 none, 1 advantage"}
        return [
            {"name": "roll_check",
             "description": "Resolve a d20 ability or skill check vs a DC. The result is authoritative "
                            "— narrate the SUCCESS/FAILURE it returns, never a different outcome.",
             "input_schema": {"type": "object", "properties": {
                 "actor_id": {"type": "string", "description": "id of the acting creature"},
                 "ability": {"type": "string", "enum": list(M.ABILITIES)},
                 "skill": {"type": "string", "enum": sorted(M.SKILLS),
                           "description": "optional; if given, sets the ability + adds proficiency"},
                 "dc": {"type": "integer", "description": "difficulty class, 5 (trivial)-30 (legendary)"},
                 "advantage": adv},
                 "required": ["actor_id", "dc"]}},
            {"name": "roll_saving_throw",
             "description": "Resolve a d20 saving throw vs a DC (uses the actor's save proficiencies). "
                            "Authoritative.",
             "input_schema": {"type": "object", "properties": {
                 "actor_id": {"type": "string"},
                 "ability": {"type": "string", "enum": list(M.ABILITIES)},
                 "dc": {"type": "integer"},
                 "advantage": adv},
                 "required": ["actor_id", "ability", "dc"]}},
        ]
