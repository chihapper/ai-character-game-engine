"""SRD-based game-layer rules system — the mechanical spine of the game.

Original mechanics (systems aren't copyrightable) + attributed SRD *data* (see LICENSE-SRD.md at the
repo root). Deterministic, tool-surfaced, renderer-agnostic, data-driven. Nothing here is named in
engine code — the engine (the mind) never learns a rule; the game layer owns all mechanics and
surfaces them to the DM/engine as tools.

Build phases: 1 core mechanics + creature model (here) -> 2 combat -> 3 bestiary -> 4 encounter
scaling -> 5 loot -> 6 progression + class skeleton.
"""
from .combat import AttackResult, CombatEngine
from .conditions import Condition, EFFECTS, effects_of, is_incapacitated, speed_is_zero
from .dice import Dice, Roll
from .engine import Rules5e
from .mechanics import (
    ABILITIES,
    SKILLS,
    CheckResult,
    proficiency_bonus,
    proficiency_bonus_for_cr,
    proficiency_bonus_for_level,
)

__all__ = [
    "Dice", "Roll", "Rules5e",
    "ABILITIES", "SKILLS", "CheckResult",
    "proficiency_bonus", "proficiency_bonus_for_level", "proficiency_bonus_for_cr",
    "Condition", "EFFECTS", "effects_of", "is_incapacitated", "speed_is_zero",
    "CombatEngine", "AttackResult",
]
