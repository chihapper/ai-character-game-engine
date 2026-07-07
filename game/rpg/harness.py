"""Headless slice harness — GENERATE + AUTO-PLAYTEST any slice through the real GameSession seam,
with NO renderer and NO LLM calls, so it proves the skeleton runs a slice end-to-end mechanically.

For each slice it:
  1. Builds it via the real `RpgGame.new(slice=...)` and prints a report of the generated world
     (map, player, NPCs + recruit gifts, enemies + attack profiles, objective door, quest, flavor).
  2. Drives a scripted playthrough over `submit_action` only (pathfind → trigger combat → win it →
     obtain the objective key via the authored data wiring → open the objective door).
  3. Round-trips the world through to_json/from_json.
All three must pass with ZERO game-core changes between slices — that is the Phase-A proof.

    .venv/Scripts/python.exe -m game.rpg.harness            # all slices
    .venv/Scripts/python.exe -m game.rpg.harness emberdeep  # one slice
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter, deque

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")

from game.rpg.content import SLICES  # noqa: E402
from game.rpg.dungeon import render_ascii  # noqa: E402
from game.rpg.game import RpgGame  # noqa: E402
from game.rpg.session import PlayerAction  # noqa: E402
from game.rpg.state import GameState, Mode  # noqa: E402

_BLOCKERS = ("enemy", "npc", "follower", "door")


# ---- pathfinding over the static walkable grid (renderer-free) -----------------------------------
def _bfs_toward(wm, src, goal, blocked):
    """First step (dx,dy) toward the REACHABLE cell nearest `goal`, avoiding `blocked` cells (the
    goal itself is always allowed). Robust when the goal is walled off or enemy-occupied: the bot
    still closes the distance (so an encounter that triggers within range still fires)."""
    src, goal = tuple(src), tuple(goal)
    prev = {src: None}
    order = [src]
    q = deque([src])
    while q:
        cx, cy = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (cx + dx, cy + dy)
            if nb in prev or not wm.walkable(*nb):
                continue
            if nb in blocked and nb != goal:
                continue
            prev[nb] = (cx, cy)
            order.append(nb)
            q.append(nb)
    best = min(order, key=lambda c: abs(c[0] - goal[0]) + abs(c[1] - goal[1]))
    if best == src:
        return None
    cur = best
    while prev[cur] != src:
        cur = prev[cur]
    return (cur[0] - src[0], cur[1] - src[1])


def _blocked_cells(game, exclude=None):
    return {tuple(e.pos) for e in game.get_state().entities
            if e.pos and e.kind in _BLOCKERS and tuple(e.pos) != tuple(exclude or (-1, -1))}


async def _walk_to(game, target, *, within=0, max_steps=1200):
    """Drive the player toward `target`; returns when within `within` cells, or when combat triggers
    en route, or False if truly boxed in / makes no progress."""
    target = tuple(target)
    for _ in range(max_steps):
        px, py = game.state.player.pos
        if abs(px - target[0]) + abs(py - target[1]) <= within:
            return True
        step = _bfs_toward(game.state.world_map, (px, py), target, _blocked_cells(game, exclude=target))
        if step is None:
            return abs(px - target[0]) + abs(py - target[1]) <= within
        await game.submit_action(PlayerAction(kind="move", dx=step[0], dy=step[1]))
        if game.state.mode == Mode.combat:
            return True
        if game.state.player.pos == (px, py):                 # bumped, no progress -> stuck
            return abs(px - target[0]) + abs(py - target[1]) <= within
    return False


async def _fight(game, *, max_actions=800):
    """Play the player's turns in the turn-based engine until the fight ends. A SMOKE TEST of the combat
    machinery, not a balance test: the harness makes the player unkillable so the mechanical loop
    (initiative -> the player's turn -> NPC turns auto-resolve -> death saves -> victory -> loot) runs to
    completion regardless of whether a solo level-1 could actually survive 3-4 foes (in the real game
    you'd bring a recruited ally). NPC turns resolve inside `submit_action`; the harness only drives the
    PLAYER's turn: close on the nearest foe with movement, bump-attack when adjacent, then `wait` to end
    the turn. The DEFEAT path is proven separately (see the death soft-lock test)."""
    game.state.player.hp = game.state.player.max_hp = 10**6      # harness affordance: survive to victory
    for _ in range(max_actions):
        if game.state.mode != Mode.combat:
            return True
        cs = game.state.combat
        if cs is None or cs.current() != game.state.player.id:   # not our turn (shouldn't happen) -> nudge
            await game.submit_action(PlayerAction(kind="wait"))
            continue
        living = [en for e in game.state.encounters for en in e.enemies if en.alive]
        if not living:
            await game.submit_action(PlayerAction(kind="wait"))
            continue
        px, py = game.state.player.pos
        tgt = min(living, key=lambda e: abs(e.pos[0] - px) + abs(e.pos[1] - py))
        dist = abs(tgt.pos[0] - px) + abs(tgt.pos[1] - py)
        if dist == 1 and not cs.action_used:                     # adjacent + action free -> bump = attack
            await game.submit_action(PlayerAction(kind="move", dx=tgt.pos[0] - px, dy=tgt.pos[1] - py))
            continue
        if dist > 1 and cs.movement_left >= 5:                    # not adjacent -> spend movement closing in
            step = _bfs_toward(game.state.world_map, (px, py), tgt.pos, _blocked_cells(game, exclude=tgt.pos))
            if step is not None:
                await game.submit_action(PlayerAction(kind="move", dx=step[0], dy=step[1]))
                continue
        await game.submit_action(PlayerAction(kind="wait"))       # attacked / can't reach -> end the turn
    return game.state.mode != Mode.combat


async def _reach_objective(game):
    """Obtain the door's key via the SLICE's authored data (the NPC placement that grants it) — no
    LLM — then walk to the door and open it. Proves the objective is completable mechanically."""
    s = game.state
    door = s.doors[0]
    if door.key_item and not s.has_item(door.key_item):
        giver = next((n for n in s.npcs if n.on_recruit_grant and n.on_recruit_grant.id == door.key_item), None)
        if giver:                                             # simulate the recruit handover (data path)
            s.player.inventory.append(giver.on_recruit_grant.model_copy(deep=True))
    if not await _walk_to(game, door.pos, within=1):
        return False
    px, py = s.player.pos
    await game.submit_action(PlayerAction(kind="move", dx=door.pos[0] - px, dy=door.pos[1] - py))
    return not door.locked


# ---- report + drive one slice --------------------------------------------------------------------
def _report(game) -> str:
    s = game.state
    wm = s.world_map
    hist = Counter(c for row in wm.tiles for c in row)
    npc_lines = []
    for n in s.npcs:
        gift = f" · gives '{n.on_recruit_grant.name}'" if n.on_recruit_grant else ""
        npc_lines.append(f"    - {n.name} ({n.slug}) @ {n.pos}{gift}")
    enemies = [en for e in s.encounters for en in e.enemies]
    ekinds = Counter(en.name for en in enemies)
    prof = enemies[0] if enemies else None
    doors = "; ".join(f"{d.name} @ {d.pos} key={d.key_item or '(none)'} force_dc={d.force_dc} "
                      f"-> quest '{d.opens_quest}'" for d in s.doors)
    p = s.player
    marks = {tuple(p.pos): "@"}
    for n in s.npcs:
        marks[tuple(n.pos)] = n.name[0]
    for en in enemies:
        marks[tuple(en.pos)] = en.name[0].lower()
    for d in s.doors:
        marks[tuple(d.pos)] = "D"
    preview = render_ascii(wm, marks)
    preview = "\n".join("    " + ln for ln in preview.splitlines())
    return "\n".join([
        f"  theme:      {s.flavor.theme}   (map source: {wm.source})",
        f"  map:        {wm.width}x{wm.height}   floor={hist.get('.',0)} wall={hist.get('#',0)} "
        f"stairs={hist.get('>',0)+hist.get('<',0)}",
        f"  player:     HP {p.hp}/{p.max_hp} AC {p.ac}  weapon {p.damage_dice} {p.attack_ability}  @ {p.pos}",
        f"  NPCs:\n" + ("\n".join(npc_lines) or "    (none)"),
        f"  enemies:    {dict(ekinds)}"
        + (f"  profile: {prof.max_hp}hp ac{prof.ac} {prof.damage_dice} {prof.attack_ability}" if prof else ""),
        f"  objective:  {doors}",
        f"  quest:      " + "; ".join(f"{q.title} [{q.state}]" for q in s.quests),
        f"  scene:      {s.flavor.scene_prose[:96]}...",
        "  map preview (@ player · CAPITAL npc · lower enemy · D door):",
        preview,
    ])


def _roundtrip(state: GameState) -> None:
    s2 = GameState.from_json(state.to_json())
    assert s2.flavor.theme == state.flavor.theme, "flavor lost in save/load"
    assert [d.key_item for d in s2.doors] == [d.key_item for d in state.doors], "door keys lost"
    a = next((n.on_recruit_grant.id for n in state.npcs if n.on_recruit_grant), None)
    b = next((n.on_recruit_grant.id for n in s2.npcs if n.on_recruit_grant), None)
    assert a == b, "recruit-gift wiring lost in save/load"
    assert [e.damage_dice for e in [en for enc in s2.encounters for en in enc.enemies]] == \
           [e.damage_dice for e in [en for enc in state.encounters for en in enc.enemies]], "enemy profiles lost"


async def run_slice(name: str, *, seed: int = 1) -> bool:
    print(f"\n=== SLICE: {name} (seed {seed}) ===")
    game = RpgGame.new(slice=name, seed=seed)
    print(_report(game))

    checks: list[tuple[str, bool]] = []
    # 1) save/load round-trip of the new data fields
    try:
        _roundtrip(game.state)
        checks.append(("save/load round-trip", True))
    except AssertionError as e:
        checks.append((f"save/load round-trip ({e})", False))

    # 2) reach + trigger the encounter
    #    Make the player unkillable BEFORE the trigger: the very first NPC turns resolve inside the
    #    triggering submit_action (if an enemy won initiative), so the boost has to precede it.
    game.state.player.hp = game.state.player.max_hp = 10**6
    trig = game.state.encounters[0].trigger_pos
    reached = await _walk_to(game, trig)
    in_combat = game.state.mode == Mode.combat
    checks.append(("walk to encounter -> combat triggers", reached and in_combat))

    # 3) win the fight
    won = await _fight(game)
    living = [en for e in game.state.encounters for en in e.enemies if en.alive]
    checks.append(("combat resolves (enemies down, back to exploration)",
                   won and not living and game.state.mode == Mode.exploration and game.state.player.alive))

    # 4) obtain the key (authored data path) + open the objective door
    opened = await _reach_objective(game)
    door = game.state.doors[0]
    quest_done = any(q.id == door.opens_quest and q.state == "done" for q in game.state.quests)
    checks.append(("objective door opens + quest completes", opened and quest_done))

    print("  playthrough:")
    for label, ok in checks:
        print(f"    [{'PASS' if ok else 'FAIL'}] {label}")
    return all(ok for _, ok in checks)


async def main(names) -> int:
    names = names or list(SLICES)
    results = {n: await run_slice(n) for n in names}
    print("\n" + "=" * 60)
    for n, ok in results.items():
        print(f"  {n:12s} {'PASS' if ok else 'FAIL'}")
    allok = all(results.values())
    print(f"\n{'ALL SLICES PASS — the skeleton runs every slice with zero core edits.' if allok else 'FAILURES ABOVE.'}")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main([a for a in sys.argv[1:] if not a.startswith("-")])))
