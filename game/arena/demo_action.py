"""Demo/validation for Arena step 3: the AGNOSTIC action seam closing the loop.

Corvin, from his grounded percept, chooses ONE action from what the inn AFFORDS — and can't invent an
alley to "Mother Sael's," because it isn't offered. The world changes; re-perception reflects it.

    python -m game.arena.demo_action
"""
from __future__ import annotations

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
CORVIN = "corvin-ashgrave-inworld"


async def main() -> None:
    scen = yaml.safe_load(open(SCENARIO, encoding="utf-8"))
    handles = {c["slug"]: c.get("handle", c["slug"]) for c in scen["cast"]}
    world = load_world(MAP)

    def ref_npc(eid):
        return "the stranger just in from the storm" if eid == "player" else handles.get(eid, eid)

    p = perceive(world, CORVIN, clock=0.0, ref_of=ref_npc)
    sit_text = render_situation(to_situation(p))
    acts = available(world, CORVIN, ref_of=ref_npc)

    print("=== WHAT THE INN AFFORDS CORVIN (the bounded option set) ===")
    for a in acts:
        print(f"  [{a.type:6s}] {a.label}")
    print("\n  (note: 'go to Mother Sael's' / 'down the alley' are NOT here — the world doesn't afford them)")

    print("\n=== CORVIN CHOOSES (the engine picks ONLY from the above) ===")
    choice = await choose_action(load_character(CORVIN), sit_text, [a.label for a in acts])
    print("  action:", choice["action"])
    print("  reason:", choice["reason"])

    before = (world.region_of(world.entities[CORVIN].pos), world.entities[CORVIN].stance)
    conseq = execute(world, CORVIN, choice["action"], acts) if choice["action"] else "holds"
    after = (world.region_of(world.entities[CORVIN].pos), world.entities[CORVIN].stance)
    print("\n=== THE WORLD CHANGES; RE-PERCEPTION REFLECTS IT ===")
    print(f"  consequence: he {conseq}")
    print(f"  before: at {before[0]} — {before[1]}")
    print(f"  after:  at {after[0]} — {after[1]}")


if __name__ == "__main__":
    asyncio.run(main())
