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
    print("\n" + ("ALL GENERATORS PASS every invariant — no map can ship uncompletable."
                  if ok else "INVARIANT FAILURES ABOVE."))
    return 0 if ok else 1


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 200
    sys.exit(main(n))
