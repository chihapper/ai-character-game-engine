"""Core d20 mechanics — ability checks, saving throws, skills, proficiency, advantage.

Original implementation of the *system* (game mechanics aren't copyrightable). Pure + deterministic:
the `Dice` is injected. Works on any `sheet` that exposes `.stats.mod(ability)` plus the optional 5e
fields on `Combatant` (saving_throw_profs, skill_profs, expertise, level/cr/prof_bonus).

RAW note: on ability checks and saving throws a natural 20/1 is just 20/1 — no auto success/failure
(that's an attack-roll rule, handled in the combat layer). We still REPORT the nat20/nat1 as
`critical` for flavor/narration.
"""
from __future__ import annotations

from dataclasses import dataclass

from .dice import Dice

ABILITIES: tuple[str, ...] = ("STR", "DEX", "CON", "INT", "WIS", "CHA")

# skill -> governing ability (the 18 SRD skills)
SKILLS: dict[str, str] = {
    "athletics": "STR",
    "acrobatics": "DEX", "sleight_of_hand": "DEX", "stealth": "DEX",
    "arcana": "INT", "history": "INT", "investigation": "INT", "nature": "INT", "religion": "INT",
    "animal_handling": "WIS", "insight": "WIS", "medicine": "WIS", "perception": "WIS", "survival": "WIS",
    "deception": "CHA", "intimidation": "CHA", "performance": "CHA", "persuasion": "CHA",
}


def proficiency_bonus_for_level(level: int) -> int:
    """+2 (1-4), +3 (5-8), +4 (9-12), +5 (13-16), +6 (17-20)."""
    return 2 + max(0, (int(level) - 1) // 4)


def proficiency_bonus_for_cr(cr: float) -> int:
    """Monster PB tracks CR the same way a character's PB tracks level (CR<1 -> +2)."""
    return 2 if cr < 1 else 2 + max(0, (int(cr) - 1) // 4)


def proficiency_bonus(sheet) -> int:
    """From an explicit `prof_bonus`, else a character `level`, else a monster `cr`, else +2."""
    pb = getattr(sheet, "prof_bonus", None)
    if pb is not None:
        return int(pb)
    level = getattr(sheet, "level", None)
    if level is not None:
        return proficiency_bonus_for_level(level)
    cr = getattr(sheet, "cr", None)
    if cr is not None:
        return proficiency_bonus_for_cr(cr)
    return 2


def ability_mod(sheet, ability: str) -> int:
    return sheet.stats.mod(ability)


def _norm(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_")


@dataclass
class CheckResult:
    roll: int          # the raw d20
    modifier: int      # ability (+ proficiency, + expertise) applied
    total: int
    dc: int
    success: bool
    critical: str = "" # "" | "hit" (nat 20) | "miss" (nat 1) — informational on checks/saves


def _resolve(d20: int, mod: int, dc: int) -> CheckResult:
    crit = "hit" if d20 == 20 else "miss" if d20 == 1 else ""
    return CheckResult(roll=d20, modifier=mod, total=d20 + mod, dc=int(dc),
                       success=(d20 + mod) >= int(dc), critical=crit)


def ability_check(dice: Dice, sheet, ability: str, dc: int, *, proficient: bool = False,
                  expertise: bool = False, advantage: int = 0) -> CheckResult:
    mod = ability_mod(sheet, ability)
    if proficient:
        mod += proficiency_bonus(sheet) * (2 if expertise else 1)
    return _resolve(dice.d20(advantage), mod, dc)


def saving_throw(dice: Dice, sheet, ability: str, dc: int, *, advantage: int = 0) -> CheckResult:
    profs = {a.strip().upper() for a in getattr(sheet, "saving_throw_profs", [])}
    return ability_check(dice, sheet, ability, dc, proficient=ability.strip().upper() in profs,
                         advantage=advantage)


def _skill_ability(skill_key: str) -> str:
    """The governing ability for a skill — RAISE on an unknown key rather than silently guessing.
    (The two entry points once fell back to DIFFERENT abilities — STR vs WIS — so the same typo'd
    key resolved inconsistently depending on the code path. Fail loud instead.)"""
    ability = SKILLS.get(skill_key)
    if ability is None:
        raise ValueError(f"unknown skill {skill_key!r}; known: {', '.join(sorted(SKILLS))}")
    return ability


def skill_check(dice: Dice, sheet, skill: str, dc: int, *, advantage: int = 0) -> CheckResult:
    key = _norm(skill)
    ability = _skill_ability(key)
    profs = {_norm(s) for s in getattr(sheet, "skill_profs", [])}
    exps = {_norm(s) for s in getattr(sheet, "expertise", [])}
    return ability_check(dice, sheet, ability, dc, proficient=key in profs or key in exps,
                         expertise=key in exps, advantage=advantage)


def passive_score(sheet, skill: str) -> int:
    """10 + the modifiers that would apply to the check (5e passive: e.g. passive Perception)."""
    key = _norm(skill)
    ability = _skill_ability(key)
    mod = ability_mod(sheet, ability)
    profs = {_norm(s) for s in getattr(sheet, "skill_profs", [])}
    exps = {_norm(s) for s in getattr(sheet, "expertise", [])}
    if key in exps:
        mod += proficiency_bonus(sheet) * 2
    elif key in profs:
        mod += proficiency_bonus(sheet)
    return 10 + mod
