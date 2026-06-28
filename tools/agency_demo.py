"""Autonomous agency demo (#20): the GAME calls Engine.deliberate() between scenes — the player not
present — and a weary, scarred Corvin decides, ON HIS OWN, what he does or becomes from everything
that's accumulated. Shows: a real turning point under gated mode (only with cause), the inner change
applied (forgiveness / evolved goals / intent), the new direction showing up in later behavior, and
the cheap structural skip when nothing has happened. Anthropic-only.

  python tools/agency_demo.py
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ["RELATIONSHIP_STATE"] = "true"
os.environ["RELATIONSHIP_TIME_DECAY"] = "true"
os.environ["REFLECTION_ENABLED"] = "true"
os.environ["REFLECTION_IMPORTANCE_THRESHOLD"] = "2.0"
os.environ["INTENT_STATE"] = "false"
os.environ["COMMITMENT_DETECTION"] = "false"
os.environ["CONTRADICTION_DETECTION"] = "false"
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.context import RespondRequest, Situation  # noqa: E402
from orchestrator.engine import Engine  # noqa: E402

SLUG = "corvin-ashgrave-inworld"


def wipe():
    for f in glob.glob(f".memory/{SLUG}.*"):
        os.remove(f)


def scars(r):
    return f"scar a/t/r {r.scar_affection:.2f}/{r.scar_trust:.2f}/{r.scar_respect:.2f} (trust {r.trust:.2f})"


async def main():
    wipe()
    eng = Engine(load_character(SLUG), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=130))

    # 1) a bond, then the player betrays him -> a scar
    for line in ["We've run clean jobs for months. Partners, you and me.",
                 "Turned down Dren's coin to stay with you. Long game.",
                 "Here's the full take again. We're square."]:
        await eng.respond(RespondRequest(player_input=line, situation=Situation(clock=1.0)), debug=True)
    await eng.respond(RespondRequest(player_input="I sold your manifest to the Crown. Your operation's "
                      "burned. It was you or me.", situation=Situation(clock=6.0)), debug=True)
    print(f"after betrayal: {scars(eng.relationship.get())}")
    print(f"profile goals : {eng.character.goals}")

    # 2) years of his own grinding life accumulate (plain world memories, player not involved)
    for fact, t in [("Another smuggling season ended in blood — two of Corvin's men drowned off the reef.", 200),
                    ("The Crown tightened the harbor; the trade got meaner and the cuts got thinner.", 450),
                    ("Corvin buried the last man who'd been with him since the start; he's alone in it now.", 800),
                    ("A travelling brother from the cliff abbey shared bread with Corvin and spoke of letting go.", 1100)]:
        await eng.remember(fact, importance=0.7, t=float(t))

    # 3) the GAME calls deliberate() — the player is NOT here. Does he change, on his own?
    print("\n=== deliberate(mode='gated') at year ~3 ===")
    decision = await eng.deliberate(Situation(location="the cliff abbey road", clock=1200.0), mode="gated")
    print(json.dumps({k: decision.get(k) for k in ("changed", "reflection", "internal", "new_intent",
                                                    "new_goals", "world_action")}, indent=2)[:900])
    print(f"\napplied -> {scars(eng.relationship.get())}")
    print(f"evolved goals: {eng.agency.goals()}")

    # 4) re-deliberate immediately with NOTHING new -> cheap structural skip (no LLM call)
    again = await eng.deliberate(Situation(clock=1201.0), mode="gated")
    print(f"\nre-deliberate (nothing happened since): changed={again.get('changed')} skipped={again.get('skipped')}")

    # 5) the new direction shows up in later behavior (player returns long after)
    reply, _ = await eng.respond(RespondRequest(player_input="...It's been years, Corvin. It's me.",
                                 situation=Situation(clock=1300.0)), debug=True)
    print(f"\nplayer returns -> Corvin: {reply[:200]}")
    wipe()


if __name__ == "__main__":
    asyncio.run(main())
