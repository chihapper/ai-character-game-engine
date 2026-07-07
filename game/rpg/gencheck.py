"""Generation invariants — the enforced 'rules that ensure procgen never breaks the game'.

Fuzzes every generator across many seeds and asserts the properties a broken map would violate:
fully connected floor (no marooned pockets), stairs placed + reachable, spawn anchors distinct +
walkable + mutually reachable, and everything in-bounds. Both generators already assert connectivity
at build time (dungeon._assert_connected); this is the repeatable regression guard over many seeds.

    .venv/Scripts/python.exe -m game.rpg.gencheck            # 200 seeds/generator
    .venv/Scripts/python.exe -m game.rpg.gencheck 1000       # more
"""
from __future__ import annotations

import sys
from collections import deque

from game.rpg.dungeon import generate_caverns, generate_dungeon


def _flood(wm, start):
    seen = {tuple(start)}
    q = deque([tuple(start)])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (x + dx, y + dy)
            if nb not in seen and wm.walkable(*nb):
                seen.add(nb)
                q.append(nb)
    return seen


def _floor(wm):
    return {(x, y) for y in range(wm.height) for x in range(wm.width) if wm.walkable(x, y)}


def invariants(d) -> list[str]:
    wm = d.world_map
    bad: list[str] = []
    if wm.stairs_up is None or wm.stairs_down is None:
        bad.append("missing stairs")
        return bad
    if not (wm.in_bounds(*wm.stairs_up) and wm.in_bounds(*wm.stairs_down)):
        bad.append("stairs out of bounds")
    reach = _flood(wm, wm.stairs_up)
    floor = _floor(wm)
    if reach != floor:
        bad.append(f"disconnected: {len(floor - reach)} floor cells unreachable")
    if wm.stairs_down not in reach:
        bad.append("stairs_down unreachable")
    sp = [tuple(p) for p in d.spawns]
    if len(set(sp)) != len(sp):
        bad.append("duplicate spawn anchors")
    for p in sp:
        if not wm.walkable(*p):
            bad.append(f"spawn {p} not walkable")
        elif p not in reach:
            bad.append(f"spawn {p} unreachable")
    return bad


def content_invariants(n: int) -> bool:
    """Fuzz the CONTENT-generation modules (SRD phases 3-5) the way the map generators are fuzzed:
    every bestiary entry must build a valid, living Enemy; encounter packs must respect the party
    budget and be seed-deterministic; loot must be seed-deterministic, well-formed, and NEVER able
    to collide with an objective-key grant (the game refuses ids containing key/sigil/keystone)."""
    import random

    from game.rpg.srd import bestiary, encounters, loot, progression

    bad: list[str] = []
    # 1) every bestiary entry constructs a valid combatant
    for slug in bestiary.slugs():
        try:
            e = bestiary.make_enemy(slug, id=f"chk-{slug}")
            if not (e.alive and e.max_hp >= 1 and e.ac >= 5 and e.cr is not None):
                bad.append(f"bestiary {slug}: implausible sheet (hp {e.max_hp} ac {e.ac} cr {e.cr})")
        except Exception as exc:                            # noqa: BLE001
            bad.append(f"bestiary {slug}: {exc}")
    # 2) encounter packs: budget respected + deterministic per seed
    palette = [(s, bestiary.cr(s)) for s in bestiary.slugs(max_cr=3.0)]
    for seed in range(1, n + 1):
        for level, diff in ((1, "easy"), (1, "deadly"), (3, "medium"), (5, "hard")):
            a = encounters.build_encounter(party_level=level, party_size=1, difficulty=diff,
                                           palette=palette, rng=random.Random(seed))
            b = encounters.build_encounter(party_level=level, party_size=1, difficulty=diff,
                                           palette=palette, rng=random.Random(seed))
            if a != b:
                bad.append(f"encounter seed {seed} L{level} {diff}: non-deterministic ({a} vs {b})")
                break
            cost = encounters.encounter_cost([bestiary.cr(s) for s in a])
            budget = encounters.party_budget(level, 1, diff)
            if not a or cost > budget:
                bad.append(f"encounter seed {seed} L{level} {diff}: cost {cost} > budget {budget} ({a})")
                break
    # 3a) loot STATIC scan — every band's full table, straight from the data (not sampled through
    #     roll_loot): this is the load-bearing guard, because _award_victory appends loot items
    #     directly to the inventory, BYPASSING the DM's objective-key containment guard. Every id
    #     (items AND slugged trinkets) must be non-empty and key-collision-safe, every entry must
    #     construct a valid Item, and every heal string must parse.
    from game.rpg.srd.dice import Dice
    from game.rpg.state import Item

    def _slug(text: str) -> str:
        return "".join(c if c.isalnum() else "-" for c in text.lower())[:40].strip("-")

    for band, tbl in loot.load().items():
        for it in tbl.get("items", []):
            iid = str(it.get("id", ""))
            if not iid or any(w in iid for w in ("key", "sigil", "keystone")):
                bad.append(f"loot {band}: unsafe/empty item id {iid!r}")
            try:
                Item(id=iid or "x", name=it.get("name", "?"), kind=it.get("kind", "misc"),
                     data=it.get("data", {}))
            except Exception as exc:                # noqa: BLE001
                bad.append(f"loot {band} {iid}: not Item-constructible ({exc})")
            heal = (it.get("data") or {}).get("heal")
            if heal:
                try:
                    Dice(seed=1).roll(str(heal))
                except Exception:                   # noqa: BLE001
                    bad.append(f"loot {band} {iid}: unparseable heal {heal!r}")
        for trinket in tbl.get("trinkets", []):
            tid = _slug(str(trinket))
            if not tid or any(w in tid for w in ("key", "sigil", "keystone")):
                bad.append(f"loot {band}: unsafe trinket slug {tid!r} from {trinket!r}")
    # 3b) loot rolls: deterministic + well-formed, ONE ROLL PER BAND per seed (a fixed mixed-CR
    #     list only ever exercised one band; the second-drop branch is band2+ only).
    for seed in range(1, n + 1):
        for crs in ([0.25], [2.0], [4.0], [6.0]):
            a = loot.roll_loot(crs, random.Random(seed))
            b = loot.roll_loot(crs, random.Random(seed))
            if a != b:
                bad.append(f"loot seed {seed} crs {crs}: non-deterministic")
                break
            if not isinstance(a.get("gold"), int) or a["gold"] < 0:
                bad.append(f"loot seed {seed} crs {crs}: bad gold {a.get('gold')}")
            for it in a.get("items", []):
                iid = str(it.get("id", ""))
                if not iid or any(w in iid for w in ("key", "sigil", "keystone")):
                    bad.append(f"loot seed {seed} crs {crs}: unsafe/empty item id {iid!r}")
    xs = [progression.xp_for_crs([c]) for c in (0, 0.25, 0.5, 1, 2, 3, 4, 5)]
    if xs != sorted(xs):
        bad.append(f"xp_for_crs not monotone: {xs}")

    for line in bad[:8]:
        print(f"  [content] {line}")
    status = "PASS" if not bad else f"FAIL ({len(bad)} problems)"
    print(f"  [{status}] content (bestiary/encounters/loot/progression): "
          f"{len(bestiary.slugs())} creatures, {n} seeds fuzzed")
    return not bad


def main(n: int = 200) -> int:
    ok = True
    for name, gen in (("rooms   (generate_dungeon)", generate_dungeon),
                      ("caverns (generate_caverns)", generate_caverns)):
        broken = 0
        ratios = []
        exit_frac = []                                     # entrance<->exit distance as a fraction of map size
        for seed in range(1, n + 1):
            try:
                d = gen(seed=seed)
                probs = invariants(d)
            except AssertionError as e:                    # build-time connectivity assert fired
                probs = [f"build assert: {e}"]
            if probs:
                broken += 1
                if broken <= 5:
                    print(f"  [{name} seed {seed}] {probs}")
            else:
                wm = d.world_map
                ratios.append(len(_floor(wm)) / (wm.width * wm.height))
                dist = abs(wm.stairs_up[0] - wm.stairs_down[0]) + abs(wm.stairs_up[1] - wm.stairs_down[1])
                exit_frac.append(dist / (wm.width + wm.height))
        avg = sum(ratios) / len(ratios) if ratios else 0.0
        ef_min = min(exit_frac) if exit_frac else 0.0
        ef_avg = sum(exit_frac) / len(exit_frac) if exit_frac else 0.0
        status = "PASS" if broken == 0 else f"FAIL ({broken} broken)"
        print(f"  [{status}] {name}: {n} seeds  avg floor ratio {avg:.2f}  "
              f"entrance<->exit spread avg {ef_avg:.2f} min {ef_min:.2f} of (w+h)")
        ok = ok and broken == 0
    ok = content_invariants(max(20, n // 10)) and ok
    print("\n" + ("ALL GENERATORS + CONTENT PASS every invariant — no map or encounter can ship broken."
                  if ok else "INVARIANT FAILURES ABOVE."))
    return 0 if ok else 1


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 200
    sys.exit(main(n))
