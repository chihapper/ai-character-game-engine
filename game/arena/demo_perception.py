"""Demo/validation for Arena steps 1-2: the authoritative world model + first-person perception.

Shows the ferry-inn as a grid presented in named places, each agent's grounded percept, and — the
payoff — an NPC responding through the REAL engine from a DERIVED Situation, so it's aware of the
actual scene and can't invent an alley to "Mother Sael's."

    python -m game.arena.demo_perception
"""
from __future__ import annotations

import asyncio
import glob
import os
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import yaml
from dotenv import load_dotenv

load_dotenv(".env")

from game.arena.perception import perceive, render_player_view, to_situation  # noqa: E402
from game.arena.world import load_world  # noqa: E402
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.config import get_settings  # noqa: E402
from orchestrator.context import RespondRequest, render_situation  # noqa: E402
from orchestrator.engine import Engine  # noqa: E402

MAP = "game/arena/maps/ferry_inn.yaml"
SCENARIO = "game/scenarios/ferry_crossing.yaml"
CORVIN = "corvin-ashgrave-inworld"


async def main() -> None:
    scen = yaml.safe_load(open(SCENARIO, encoding="utf-8"))
    handles = {c["slug"]: c.get("handle", c["slug"]) for c in scen["cast"]}
    world = load_world(MAP)

    print("=== THE ARENA (grid under the hood, named regions on top) ===")
    for eid, e in world.entities.items():
        who = "you (the player)" if e.kind == "player" else handles.get(eid, eid)
        print(f"  {who:34s} at {world.region_of(e.pos):26s} [{e.pos[0]},{e.pos[1]}] — {e.stance}")

    def ref_player(eid):
        return handles.get(eid, eid)

    def ref_npc(eid):
        return "the stranger just in from the storm" if eid == "player" else handles.get(eid, eid)

    print("\n=== THE PLAYER'S FIRST-PERSON VIEW (from the door — named places, no coordinates) ===")
    print(render_player_view(perceive(world, "player", clock=0.0, ref_of=ref_player)))

    print("\n=== CORVIN'S PERCEPT → the Situation his mind reasons from ===")
    sit = to_situation(perceive(world, CORVIN, clock=0.0, ref_of=ref_npc))
    print(render_situation(sit))

    # Payoff: feed the GROUNDED situation into the real engine; Corvin replies from the actual scene.
    s = get_settings()
    s.relationship_state = True
    ns = load_character(CORVIN).memory_namespace
    for f in glob.glob(f".memory/{ns}.*"):
        os.remove(f)
    eng = Engine(load_character(CORVIN), AnthropicLLM(model="claude-haiku-4-5"))
    line = "You've had your eye on that door since I walked in. Expecting the dawn boat?"
    print("\n=== CORVIN RESPONDS from the grounded percept ===")
    print("  PLAYER:", line)
    reply = await eng.respond(RespondRequest(player_input=line, situation=sit))
    print("  CORVIN:", reply[:420])
    for f in glob.glob(f".memory/{ns}.*"):
        os.remove(f)


if __name__ == "__main__":
    asyncio.run(main())
