"""Look at the built arena WITHOUT player embodiment — the world model made visible.

    python -m game.arena.inspect            # instant: render the map + world summary (no LLM)
    python -m game.arena.inspect --step 2   # watch: each NPC perceives -> acts for N ticks (LLM)

The map is a top-down grid: UPPERCASE = a person, lowercase = which named region a cell belongs to.
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import yaml
from dotenv import load_dotenv

load_dotenv(".env")

from game.arena.actions import available, execute  # noqa: E402
from game.arena.perception import perceive, to_situation  # noqa: E402
from game.arena.world import load_world  # noqa: E402
from orchestrator.agency import choose_action  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.context import render_situation  # noqa: E402

MAP = "game/arena/maps/ferry_inn.yaml"
SCENARIO = "game/scenarios/ferry_crossing.yaml"

GLYPH = {"player": "@", "della-fenwick": "D", "corvin-ashgrave-inworld": "C",
         "edwin-hale": "E", "brielle-bri-castellano": "B"}
REGION_LETTER = {"the hearth": "h", "the bar": "b", "the middle of the taproom": "m",
                 "the door": "d", "a corner table": "t", "the window": "w"}


def ascii_map(world) -> str:
    at = {e.pos: GLYPH.get(eid, "?") for eid, e in world.entities.items()}
    rows = []
    for y in range(world.h):
        row = [at.get((x, y)) or REGION_LETTER.get(world.region_of((x, y)), "·") for x in range(world.w)]
        rows.append("  " + " ".join(row))
    return "\n".join(rows)


def render(world, handles) -> None:
    print(ascii_map(world))
    print("\n  people:")
    for eid, e in world.entities.items():
        who = "you (player)" if e.kind == "player" else handles.get(eid, eid)
        print(f"    {GLYPH.get(eid,'?')}  {who} — {world.region_of(e.pos)} — {e.stance}")
    print("\n  places: " + ", ".join(f"{v}={k}" for k, v in REGION_LETTER.items()))
    fx = [f.name for f in world.fixtures.values() if f.present]
    if fx:
        print("  fixtures present: " + ", ".join(fx))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=0, help="watch each NPC act for N ticks (LLM calls)")
    args = ap.parse_args()

    scen = yaml.safe_load(open(SCENARIO, encoding="utf-8"))
    handles = {c["slug"]: c.get("handle", c["slug"]) for c in scen["cast"]}
    world = load_world(MAP)

    def ref(eid):
        return "the stranger just in from the storm" if eid == "player" else handles.get(eid, eid)

    print("=== THE FERRY-INN ARENA ===")
    render(world, handles)

    npcs = [eid for eid, e in world.entities.items() if e.kind == "npc"]
    for t in range(args.step):
        print(f"\n=== TICK {t+1}: each of them takes a beat (no player present) ===")
        for slug in npcs:
            p = perceive(world, slug, clock=float(t), ref_of=ref)
            acts = available(world, slug, ref_of=ref)
            choice = await choose_action(load_character(slug), render_situation(to_situation(p)),
                                         [a.label for a in acts])
            if choice["action"]:
                execute(world, slug, choice["action"], acts)
                print(f"  {handles.get(slug, slug)}: {choice['action']}  —  \"{choice['reason']}\"")
            else:
                print(f"  {handles.get(slug, slug)}: holds")
        print()
        render(world, handles)


if __name__ == "__main__":
    asyncio.run(main())
