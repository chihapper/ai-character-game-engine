"""The condition set + their mechanical effects, as DATA.

Original implementation — a condition list is a game system, not copyrightable. The combat engine
(Phase 2) reads `EFFECTS` to apply advantage/disadvantage, block actions, zero movement, etc. Phase
1 defines the data + a couple of query helpers. (Exhaustion is a separate leveled track — deferred.)
"""
from __future__ import annotations

from enum import Enum


class Condition(str, Enum):
    blinded = "blinded"
    charmed = "charmed"
    deafened = "deafened"
    frightened = "frightened"
    grappled = "grappled"
    incapacitated = "incapacitated"
    invisible = "invisible"
    paralyzed = "paralyzed"
    petrified = "petrified"
    poisoned = "poisoned"
    prone = "prone"
    restrained = "restrained"
    stunned = "stunned"
    unconscious = "unconscious"


# Flag vocabulary (the combat engine consumes these):
#   incapacitated        — can take no actions or reactions
#   speed_zero           — movement is 0
#   self_attack_disadv   — this creature's own attacks have disadvantage
#   attacked_advantage   — attack rolls AGAINST this creature have advantage
#   attacked_disadvantage— attack rolls against it have disadvantage
#   auto_fail_str_dex_saves — automatically fails STR and DEX saving throws
#   melee_crit_within_5  — a melee attack that hits from within 5 ft is a critical hit
#   self_check_disadv    — ability checks have disadvantage
EFFECTS: dict[Condition, dict] = {
    Condition.blinded: {"self_attack_disadv": True, "attacked_advantage": True},
    Condition.charmed: {},
    Condition.deafened: {},
    Condition.frightened: {"self_attack_disadv": True, "self_check_disadv": True},
    Condition.grappled: {"speed_zero": True},
    Condition.incapacitated: {"incapacitated": True},
    Condition.invisible: {"self_attack_advantage": True, "attacked_disadvantage": True},
    Condition.paralyzed: {"incapacitated": True, "speed_zero": True, "auto_fail_str_dex_saves": True,
                          "attacked_advantage": True, "melee_crit_within_5": True},
    Condition.petrified: {"incapacitated": True, "speed_zero": True, "attacked_advantage": True,
                          "auto_fail_str_dex_saves": True, "resist_all": True},
    Condition.poisoned: {"self_attack_disadv": True, "self_check_disadv": True},
    Condition.prone: {"self_attack_disadv": True, "melee_attacked_advantage": True,
                      "ranged_attacked_disadvantage": True},
    Condition.restrained: {"speed_zero": True, "self_attack_disadv": True, "attacked_advantage": True,
                           "dex_save_disadvantage": True},
    Condition.stunned: {"incapacitated": True, "speed_zero": True, "auto_fail_str_dex_saves": True,
                        "attacked_advantage": True},
    Condition.unconscious: {"incapacitated": True, "speed_zero": True, "auto_fail_str_dex_saves": True,
                            "attacked_advantage": True, "melee_crit_within_5": True},
}


def coerce(c) -> Condition | None:
    if isinstance(c, Condition):
        return c
    try:
        return Condition(str(c).strip().lower())
    except ValueError:
        return None


def effects_of(conditions) -> dict:
    """Merge the effect flags of a list of conditions (any True flag wins)."""
    merged: dict = {}
    for c in conditions:
        cc = coerce(c)
        if cc is None:
            continue
        for k, v in EFFECTS[cc].items():
            merged[k] = merged.get(k, False) or v
    return merged


def is_incapacitated(conditions) -> bool:
    return bool(effects_of(conditions).get("incapacitated"))


def speed_is_zero(conditions) -> bool:
    return bool(effects_of(conditions).get("speed_zero"))
