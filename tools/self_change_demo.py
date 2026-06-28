"""Self-driven change demo (#19): a game with autonomous NPC lives pushes a CHARACTER-INTERNAL
event via remember(fact, actor="self") — the player does NOTHING — and the engine enacts the inner
change: a genuine transformation warms disposition and can HEAL a betrayal scar (forgiveness the
character reaches on their own), while a passing mood changes nothing. Anthropic-only.

  python tools/self_change_demo.py
"""
from __future__ import annotations

import asyncio
import glob
import os
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ["RELATIONSHIP_STATE"] = "true"
os.environ["INTENT_STATE"] = "false"
os.environ["COMMITMENT_DETECTION"] = "false"
os.environ["REFLECTION_ENABLED"] = "false"
os.environ["CONTRADICTION_DETECTION"] = "false"
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.context import RespondRequest, Situation  # noqa: E402
from orchestrator.engine import Engine  # noqa: E402
from orchestrator.memory.relationship import RelationshipState  # noqa: E402

SLUG = "corvin-ashgrave-inworld"


def wipe():
    for f in glob.glob(f".memory/{SLUG}.*"):
        os.remove(f)


def show(tag, r):
    print(f"  {tag:30} trust {r.trust:.2f} aff {r.affection:.2f} respect {r.respect:.2f} | "
          f"scar a/t/r {r.scar_affection:.2f}/{r.scar_trust:.2f}/{r.scar_respect:.2f}")


def eng():
    return Engine(load_character(SLUG), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=120))


async def main():
    wipe()
    e = eng()
    for line in ["We've run a few clean jobs. Partners, you and me.", "Full count back again. We're square."]:
        await e.respond(RespondRequest(player_input=line, situation=Situation(clock=1.0)), debug=True)
    await e.respond(RespondRequest(player_input="I sold your manifest to the Crown. Your operation's "
                    "burned. It was you or me.", situation=Situation(clock=5.0)), debug=True)
    print("== Corvin is betrayed (player's last act), then the PLAYER DOES NOTHING further ==")
    show("after betrayal", e.relationship.get())

    # The GAME (simulating Corvin's autonomous life) pushes his own transformation — actor="self":
    await e.remember(
        "In the long years since, Corvin left the trade entirely, took monastic vows at the cliff "
        "abbey, and through years of quiet reflection finally made peace and let go of the grudge "
        "against the one who betrayed him.", actor="self", importance=0.9, t=3000.0)
    show("after his OWN transformation", e.relationship.get())
    print("   -> scar HEALED + warmed, with the player having done nothing (forgiveness on his own).")

    print("\n== control: a trivial self-event must change nothing ==")
    e2 = eng()
    e2.relationship._state = RelationshipState(affection=0.25, trust=0.20, respect=0.40, turns=4,  # noqa: SLF001
                                               scar_affection=0.40, scar_trust=0.60, scar_respect=0.20, last_t=10.0)
    show("scarred baseline", e2.relationship.get())
    await e2.remember("Corvin had a slightly better week at the docks and felt a touch cheerier.",
                      actor="self", importance=0.5, t=400.0)
    show("after a passing mood", e2.relationship.get())
    print("   -> unchanged: a whim heals nothing (threshold + AI gating hold for the self-path too).")
    wipe()


if __name__ == "__main__":
    asyncio.run(main())
