"""Turn-based combat engine (SRD-based) — the deterministic authority on every combat outcome.

Original implementation of the system. Operates on `Combatant` sheets + a `CombatState`; resolves
initiative, attack rolls vs AC (with criticals), typed damage (resistance/immunity/vulnerability),
saving throws, condition-driven advantage/disadvantage, death saves, and the turn/action economy.
It renders nothing and holds no async concerns — the game layer drives it, feeds it player input +
LLM stance decisions, and turns its results into events (voiced where a spoken beat is warranted).

Scope note: bonus actions, reactions/opportunity attacks, and concentration have economy hooks here
but are minimal in this pass — the core fight (initiative -> attacks/damage/crits -> saves ->
death saves -> next turn) is complete and RAW-correct.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import conditions as C
from . import mechanics as M
from .dice import Dice


@dataclass
class AttackResult:
    hit: bool
    critical: str        # "" | "hit" (nat 20) | "miss" (nat 1)
    attack_roll: int     # the raw d20
    attack_total: int
    target_ac: int
    damage: int
    damage_type: str
    target_id: str
    target_hp: int
    target_down: bool    # at 0 HP or dead
    target_dead: bool     # truly dead (not merely unconscious)


def _net_advantage(a: int, b: int) -> int:
    """RAW: advantage/disadvantage never stack, and any advantage + any disadvantage cancels to a
    straight roll — regardless of how many sources. Net two -1/0/+1 inputs by PRESENCE."""
    has_adv = a > 0 or b > 0
    has_dis = a < 0 or b < 0
    if has_adv and has_dis:
        return 0
    return 1 if has_adv else -1 if has_dis else 0


class CombatEngine:
    def __init__(self, rng: random.Random | None = None, *, seed: int | None = None,
                 dice: Dice | None = None) -> None:
        self.dice = dice or Dice(rng=rng, seed=seed)

    # ---- setup / turn order --------------------------------------------------------------------
    def roll_initiative(self, combatants) -> list[str]:
        """d20 + DEX mod; ties broken by higher DEX then id (deterministic). Stamps `.initiative`."""
        rolled = []
        for c in combatants:
            dex = c.stats.mod("DEX")
            init = self.dice.d20() + dex
            c.initiative = init
            rolled.append((init, dex, c.id))
        rolled.sort(key=lambda t: (-t[0], -t[1], t[2]))
        return [cid for _, _, cid in rolled]

    def _by_id(self, combatants, cid):
        return next((c for c in combatants if c.id == cid), None)

    def current(self, state, combatants):
        cid = state.current()
        return self._by_id(combatants, cid) if cid else None

    def begin_turn(self, state, combatant) -> None:
        """Reset the action economy for whoever's turn it now is."""
        state.action_used = False
        state.bonus_used = False
        state.movement_left = int(getattr(combatant, "speed", 30) or 30)

    def begin_combat(self, state, combatants) -> None:
        """Start the fight on the TOP of initiative: turn_index=0, round 1, and begin order[0]'s turn.
        Thereafter the game calls `advance_turn()` at the END of each turn. This keeps `state.current()`
        and the cursor consistent — `current()` is whoever is acting now; `advance_turn` ends that turn
        and returns the next combatant. (Call this ONCE at combat start, not `advance_turn`, so the
        top-of-initiative combatant is not skipped.)"""
        state.turn_index = 0
        state.round = 1
        state.reacted = {}
        first = self._by_id(combatants, state.order[0]) if state.order else None
        if first is not None:
            self.begin_turn(state, first)

    def advance_turn(self, state, combatants):
        """Advance to the next combatant still in the fight (dead are skipped; unconscious creatures
        making death saves DO get a turn). Wraps -> new round. Returns the new current combatant, or
        None if none remain. Also calls begin_turn on the new combatant."""
        order = state.order
        n = len(order)
        if n == 0:
            return None
        for _ in range(n):
            state.turn_index += 1
            if state.turn_index >= n:
                state.turn_index = 0
                state.round += 1
                state.reacted = {}
            c = self._by_id(combatants, order[state.turn_index])
            if c is not None and not c.dead:
                self.begin_turn(state, c)
                return c
        return None

    # ---- attacks / damage ----------------------------------------------------------------------
    def _makes_death_saves(self, c) -> bool:
        """PCs (leveled) and minded NPCs (followers/named adversaries) fall unconscious and roll death
        saves at 0 HP; generic stat-block enemies (no level, no mind) simply die."""
        return getattr(c, "level", None) is not None or getattr(c, "mind_slug", None) is not None

    def attack_advantage(self, attacker, target, *, ranged: bool = False) -> int:
        """Net advantage/disadvantage on an attack from the combatants' conditions (RAW)."""
        a = C.effects_of(attacker.conditions)
        t = C.effects_of(target.conditions)
        has_adv = bool(a.get("self_attack_advantage") or t.get("attacked_advantage")
                       or (t.get("melee_attacked_advantage") and not ranged))
        has_dis = bool(a.get("self_attack_disadv") or t.get("attacked_disadvantage")
                       or (t.get("ranged_attacked_disadvantage") and ranged))
        if has_adv and has_dis:
            return 0
        return 1 if has_adv else -1 if has_dis else 0

    def attack(self, attacker, target, *, ranged: bool = False, advantage: int = 0) -> AttackResult:
        """One weapon attack: d20 + ability mod + proficiency vs AC; nat 20 auto-hits and doubles the
        damage DICE (not the flat mod); nat 1 auto-misses. Damage is typed (resist/immune/vuln)."""
        ability = getattr(attacker, "attack_ability", "STR") or "STR"
        weapon = getattr(attacker, "damage_dice", "1d4") or "1d4"
        dtype = (getattr(attacker, "damage_type", "") or "").lower()
        net = _net_advantage(advantage, self.attack_advantage(attacker, target, ranged=ranged))
        d20 = self.dice.d20(net)
        mod = M.ability_mod(attacker, ability)
        bonus = mod + M.proficiency_bonus(attacker)
        total = d20 + bonus
        hit = d20 == 20 or (d20 != 1 and total >= target.ac)
        # A melee hit on a creature that's paralyzed/unconscious (helpless within 5 ft) is a crit too.
        t_eff = C.effects_of(target.conditions)
        is_crit = bool(hit and (d20 == 20 or (not ranged and t_eff.get("melee_crit_within_5"))))
        crit = "miss" if d20 == 1 else ("hit" if is_crit else "")
        dealt = 0
        if hit:
            r = self.dice.roll_detail(weapon)
            raw = r.total
            if is_crit:
                raw += sum(self.dice.roll_detail(weapon).rolls)   # crit: extra dice only, never the flat mod
            raw = max(0, raw + mod)
            dealt = self.apply_damage(target, raw, dtype, was_crit=is_crit)
        return AttackResult(hit=hit, critical=crit, attack_roll=d20, attack_total=total,
                            target_ac=target.ac, damage=dealt, damage_type=dtype, target_id=target.id,
                            target_hp=target.hp, target_down=target.down, target_dead=target.dead)

    def apply_damage(self, target, amount: int, damage_type: str = "", *, was_crit: bool = False) -> int:
        """Apply typed damage after resistance/immunity/vulnerability. Dropping to 0 knocks a PC-like
        unconscious (death saves) or kills a generic creature; damage taken WHILE down adds death-save
        failures; enough overflow damage is instant death. Returns the damage actually dealt."""
        dt = (damage_type or "").lower()
        eff = C.effects_of(target.conditions)
        if dt and dt in {d.lower() for d in target.immunities}:
            amount = 0
        elif dt and dt in {d.lower() for d in target.vulnerabilities}:
            amount *= 2
        elif (dt and dt in {d.lower() for d in target.resistances}) or eff.get("resist_all"):
            amount //= 2                       # per-type resistance OR condition resist-all (petrified)
        amount = max(0, int(amount))

        # a hit on an already-downed PC-like (RAW: damage at 0 HP)
        if target.hp <= 0 and not target.dead and self._makes_death_saves(target):
            if amount <= 0:                    # 0 damage is not "taking damage"
                return 0
            target.stable = False              # taking damage ends stability -> resume death saves
            if amount >= target.max_hp:        # massive damage while down = instant death
                target.dead = True
                return amount
            target.death_save_failures = min(3, target.death_save_failures + (2 if was_crit else 1))
            if target.death_save_failures >= 3:
                target.dead = True
            return amount

        overflow = amount - target.hp
        target.hp = max(0, target.hp - amount)
        if target.hp == 0:
            if self._makes_death_saves(target) and overflow < target.max_hp:  # massive damage = instant death
                self._knock_out(target)
            else:
                target.dead = True
        return amount

    def _knock_out(self, c) -> None:
        if "unconscious" not in c.conditions:
            c.conditions.append("unconscious")
        c.death_save_successes = 0
        c.death_save_failures = 0
        c.stable = False

    def death_save(self, c) -> dict:
        """A downed creature's death saving throw. 10+ = success, <10 = failure, nat 1 = two failures,
        nat 20 = regain 1 HP and wake. 3 successes -> stable; 3 failures -> dead."""
        if c.dead or c.stable or c.hp > 0:
            return {"rolled": False}
        roll = self.dice.d20()
        if roll == 20:
            c.hp = 1
            c.death_save_successes = 0
            c.death_save_failures = 0
            c.stable = False
            if "unconscious" in c.conditions:
                c.conditions.remove("unconscious")
            return {"rolled": True, "roll": 20, "outcome": "revive"}
        if roll == 1:
            c.death_save_failures = min(3, c.death_save_failures + 2)
        elif roll >= 10:
            c.death_save_successes = min(3, c.death_save_successes + 1)
        else:
            c.death_save_failures = min(3, c.death_save_failures + 1)
        outcome = "pending"
        if c.death_save_failures >= 3:
            c.dead = True
            outcome = "dead"
        elif c.death_save_successes >= 3:
            c.stable = True
            outcome = "stable"
        return {"rolled": True, "roll": roll, "outcome": outcome,
                "successes": c.death_save_successes, "failures": c.death_save_failures}

    # ---- saves (mechanics + combat conditions; keeps mechanics.saving_throw condition-agnostic) --
    def saving_throw(self, sheet, ability: str, dc: int, *, advantage: int = 0):
        """A saving throw that honors combat conditions: a paralyzed/petrified/stunned/unconscious
        creature auto-fails STR and DEX saves; a restrained creature rolls DEX saves at disadvantage."""
        eff = C.effects_of(sheet.conditions)
        ab = ability.strip().upper()
        if eff.get("auto_fail_str_dex_saves") and ab in ("STR", "DEX"):
            return M.CheckResult(roll=0, modifier=0, total=0, dc=int(dc), success=False, critical="")
        if ab == "DEX" and eff.get("dex_save_disadvantage"):
            advantage = _net_advantage(advantage, -1)
        return M.saving_throw(self.dice, sheet, ability, dc, advantage=advantage)

    # ---- end-of-fight --------------------------------------------------------------------------
    def factions_standing(self, combatants, faction_of) -> dict:
        """Count still-fighting members per faction (down/dead don't count) — the game decides when a
        fight is over from this. `faction_of(c) -> hashable`."""
        standing: dict = {}
        for c in combatants:
            if c.alive:
                standing[faction_of(c)] = standing.get(faction_of(c), 0) + 1
        return standing
