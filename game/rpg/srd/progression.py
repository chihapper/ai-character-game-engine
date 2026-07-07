"""XP advancement + a deliberately thin class SKELETON (SRD phase 6).

Full class features (fighting styles, sneak attack, spell lists, subclasses) are LATER work — this
pass covers exactly what combat needs from a class: a hit die, save/skill proficiencies, an attack
profile, and a starting-kit AC. Original implementation of the *system* (game mechanics aren't
copyrightable); all prose here is our own. The character-advancement XP thresholds are SRD 5.1
material (see LICENSE-SRD.md).

Deterministic on purpose: NO randomness in this module. HP gains use the fixed average of the hit
die (rounded up) so leveling is reproducible and never a dice-luck tax — the one source of chance
in the rules system stays in `dice.Dice`, and progression doesn't use it.

Class carrier: `Combatant.creature_type` (a free string the model already has) doubles as the
class tag — `apply_class` stamps `"humanoid (<class_key>)"` and `class_of` parses it back. This
keeps the sheet model untouched; if a slice needs a non-humanoid PC later, promote the class to a
real field then.
"""
from __future__ import annotations

from .mechanics import ABILITIES, SKILLS, proficiency_bonus_for_level

# level -> TOTAL XP required to REACH it (SRD 5.1 advancement values for levels 2-6).
XP_THRESHOLDS: dict[int, int] = {2: 300, 3: 900, 4: 2700, 5: 6500, 6: 14000}
LEVEL_CAP = 6

# Victory XP per defeated foe by CR — these ARE the SRD 5.1 XP-per-CR values (SRD material,
# attributed in LICENSE-SRD.md), mirrored by encounters.py's CR cost anchors so budget and payout
# speak the same scale. Odd CR values resolve to the nearest LOWER entry.
XP_BY_CR: dict[float, int] = {
    0: 10, 0.125: 25, 0.25: 50, 0.5: 100, 1: 200, 2: 450, 3: 700, 4: 1100, 5: 1800,
}

# The class skeleton. `hp_per_level` is the FIXED per-level HP gain (hit-die average rounded up,
# before the CON mod). `attack` is the level-1 attack profile stamped onto the sheet — for the
# wizard it's a scorching jet of flame (a skeleton stand-in for cantrips; ranged, INT-driven).
# The `ranged` flag is NOT stamped (the sheet has no field for it); the combat/game layer reads it
# from this table via `class_of` when it needs range semantics. Blurbs are original prose.
CLASSES: dict[str, dict] = {
    "fighter": {
        "hit_die": "1d10", "hp_per_level": 6,
        "saves": ["STR", "CON"], "skills": ["athletics", "intimidation"],
        "attack": {"damage_dice": "1d8", "ability": "STR", "damage_type": "slashing", "ranged": False},
        "ac_base": 16,
        "blurb": "A hard-bitten soldier who answers most problems with steel and shrugs off blows that would drop anyone else.",
    },
    "rogue": {
        "hit_die": "1d8", "hp_per_level": 5,
        "saves": ["DEX", "INT"], "skills": ["stealth", "sleight_of_hand"],
        "attack": {"damage_dice": "1d8", "ability": "DEX", "damage_type": "piercing", "ranged": False},
        "ac_base": 14,
        "blurb": "A light-footed opportunist who slips past notice and puts the blade exactly where it hurts.",
    },
    "cleric": {
        "hit_die": "1d8", "hp_per_level": 5,
        "saves": ["WIS", "CHA"], "skills": ["insight", "medicine"],
        "attack": {"damage_dice": "1d6", "ability": "STR", "damage_type": "bludgeoning", "ranged": False},
        "ac_base": 16,
        "blurb": "A steady-handed devotee whose faith closes wounds and whose mace ends arguments.",
    },
    "wizard": {
        "hit_die": "1d6", "hp_per_level": 4,
        "saves": ["INT", "WIS"], "skills": ["arcana", "investigation"],
        "attack": {"damage_dice": "1d10", "ability": "INT", "damage_type": "fire", "ranged": True},
        "ac_base": 12,
        "blurb": "A book-fed scholar who traded muscle for a mind that can set the air itself alight.",
    },
}


def _validate_classes() -> None:
    """Fail LOUD at import if the skeleton references an unknown skill/ability (mechanics style:
    a typo'd key must never resolve silently)."""
    for key, spec in CLASSES.items():
        bad_skills = [s for s in spec["skills"] if s not in SKILLS]
        bad_saves = [a for a in spec["saves"] if a not in ABILITIES]
        if bad_skills or bad_saves or spec["attack"]["ability"] not in ABILITIES:
            raise ValueError(f"class {key!r} references unknown keys: "
                             f"skills={bad_skills} saves={bad_saves} "
                             f"attack_ability={spec['attack']['ability']!r}")


_validate_classes()


def _hit_die_faces(hit_die: str) -> int:
    """'1d10' -> 10."""
    return int(str(hit_die).lower().rsplit("d", 1)[-1])


def apply_class(player, class_key: str) -> None:
    """Stamp the class skeleton onto a `PlayerCharacter` IN PLACE (character creation).

    Sets: hit_dice, saving_throw_profs, skill_profs, the attack profile (damage_dice /
    attack_ability / damage_type), ac (max of current and the class starting kit — never lowers
    a better authored AC), max_hp derived from the player's ACTUAL level (hit-die max + CON at
    level 1, plus the class per-level gain for each level beyond — so a slice that starts a
    veteran at level 2+ gets a coherent sheet), hp = max_hp, and an explicit prof_bonus for that
    level. The class key itself is carried in `creature_type` as `"humanoid (<class_key>)"`
    (see module docstring) — `class_of` reads it back.

    Raises ValueError on an unknown class key rather than guessing.
    """
    key = str(class_key).strip().lower()
    spec = CLASSES.get(key)
    if spec is None:
        raise ValueError(f"unknown class {class_key!r}; known: {', '.join(sorted(CLASSES))}")
    player.hit_dice = spec["hit_die"]
    player.saving_throw_profs = list(spec["saves"])
    player.skill_profs = list(spec["skills"])
    attack = spec["attack"]
    player.damage_dice = attack["damage_dice"]
    player.attack_ability = attack["ability"]
    player.damage_type = attack["damage_type"]
    player.ac = max(player.ac, int(spec["ac_base"]))
    # HP from the player's ACTUAL level, not a hard-coded level 1 (a slice may start a veteran):
    # hit-die max + CON at level 1, plus the class per-level gain for every level beyond.
    level = max(1, int(getattr(player, "level", 1) or 1))
    con = player.stats.mod("CON")
    per_level = max(1, int(spec["hp_per_level"]) + con)
    player.max_hp = max(1, _hit_die_faces(spec["hit_die"]) + con) + (level - 1) * per_level
    player.hp = player.max_hp
    player.prof_bonus = proficiency_bonus_for_level(level)
    player.creature_type = f"humanoid ({key})"


def class_of(player) -> str:
    """The player's class key, parsed from `creature_type` ('humanoid (rogue)' -> 'rogue').
    Defaults to 'fighter' so a pre-skeleton save or an unstamped sheet still levels sanely."""
    ct = str(getattr(player, "creature_type", "") or "").strip().lower()
    if "(" in ct and ")" in ct:
        inner = ct[ct.index("(") + 1:ct.rindex(")")].strip()
        if inner in CLASSES:
            return inner
    return ct if ct in CLASSES else "fighter"


def xp_for_crs(crs: list[float]) -> int:
    """Total victory XP for a list of defeated foes' CRs. Off-table CR values resolve to the
    nearest LOWER entry (a CR 3.5 oddity pays as CR 3; anything above the table pays as CR 5)."""
    total = 0
    for cr in crs:
        c = max(0.0, float(cr))
        key = max((k for k in XP_BY_CR if k <= c), default=0)
        total += XP_BY_CR[key]
    return total


def award_xp(player, xp: int) -> list[dict]:
    """Add XP IN PLACE and apply every level-up it pays for (capped at LEVEL_CAP).

    Per level gained: level += 1; HP gain = the class's fixed `hp_per_level` + CON mod, min 1
    total — added to BOTH max_hp and hp (leveling invigorates but does not full-heal);
    prof_bonus re-derived from the new level. XP is never removed and levels never regress.

    Returns one {"level": int, "hp_gain": int} per level gained, in order — the game narrates
    them; this module prints nothing.
    """
    player.xp += int(xp)
    gains: list[dict] = []
    spec = CLASSES[class_of(player)]
    while player.level < LEVEL_CAP:
        needed = XP_THRESHOLDS.get(player.level + 1)
        if needed is None or player.xp < needed:
            break
        player.level += 1
        hp_gain = max(1, int(spec["hp_per_level"]) + player.stats.mod("CON"))
        player.max_hp += hp_gain
        player.hp += hp_gain
        player.prof_bonus = proficiency_bonus_for_level(player.level)
        gains.append({"level": player.level, "hp_gain": hp_gain})
    return gains


def next_threshold(player) -> int | None:
    """TOTAL XP required to reach the next level, or None at the cap. (Remaining XP is simply
    `next_threshold(p) - p.xp`; the game formats the readout.)"""
    if player.level >= LEVEL_CAP:
        return None
    return XP_THRESHOLDS.get(player.level + 1)
