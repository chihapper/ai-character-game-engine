"""#12 demo: world events shift disposition (A) + feelings drift over time (B). Anthropic-only.

  A  push a player-attributable world event -> the AI shifts disposition (deltas + possible scar):
     the player's faction burns Corvin's warehouse (caused) vs the player's crew clears his debt
     (benefited).
  B  per-character persistence (warm vs cold) + the three decay rules over a 1-year gap: warmth
     fades, a transient hurt heals, a betrayal scar holds.

  python tools/world_time_demo.py
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
os.environ["RELATIONSHIP_TIME_DECAY"] = "true"
os.environ["INTENT_STATE"] = "false"
os.environ["COMMITMENT_DETECTION"] = "false"
os.environ["REFLECTION_ENABLED"] = "false"
os.environ["CONTRADICTION_DETECTION"] = "false"
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.config import get_settings  # noqa: E402
from orchestrator.context import RespondRequest, Situation  # noqa: E402
from orchestrator.engine import Engine  # noqa: E402
from orchestrator.salience import assess_persistence  # noqa: E402

CORVIN, BRI = "corvin-ashgrave-inworld", "brielle-bri-castellano-inworld"


def wipe(slug):
    for f in glob.glob(f".memory/{slug}.*"):
        os.remove(f)


def eng(slug):
    return Engine(load_character(slug), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=130))


def rel_str(r):
    return f"aff {r.affection:.2f} trust {r.trust:.2f} respect {r.respect:.2f}"


def scar_str(r):
    return f"scars aff {r.scar_affection:.2f} trust {r.scar_trust:.2f} respect {r.scar_respect:.2f}"


async def world_events():
    print("=" * 72 + "\nA — world events shift disposition (AI-judged, character-aware)\n" + "=" * 72)
    cases = [
        ("the player's faction (the Dawnguard) burned Corvin's harbor warehouse to the ground, "
         "destroying his whole stock", "caused"),
        ("the player's crew quietly bought off Corvin's debt to Dren, clearing what he owed", "benefited"),
    ]
    for fact, role in cases:
        wipe(CORVIN)
        e = eng(CORVIN)
        for line in ["We've done a few jobs now. Straight dealing, you and me.",
                     "Ran your cargo clean again. We're square."]:
            await e.respond(RespondRequest(player_input=line, situation=Situation(clock=1.0)), debug=True)
        b = e.relationship.get()
        print(f"\n  event ({role}): {fact[:70]}...")
        print(f"    before: {rel_str(b)}")
        await e.remember(fact, player_role=role, importance=0.9, t=2.0)
        a = e.relationship.get()
        print(f"    AFTER : {rel_str(a)}   mood={a.mood}")
        print(f"            {scar_str(a)}")
        wipe(CORVIN)


async def persistence_and_decay():
    print("\n" + "=" * 72 + "\nB — per-character persistence + decay over a 1-year gap\n" + "=" * 72)
    s = get_settings()
    for slug in (CORVIN, BRI):
        c = load_character(slug)
        hl = await assess_persistence(c)
        print(f"  persistence(\"{c.name}\") = {hl:.0f} days  (global default {s.relationship_decay_half_life:.0f})")

    print("\n  -- decay rules over ~1 year of no contact --")
    # warm bond neglected (high affection, deep bond) -> fades, slowly if persistent
    wipe(BRI)
    e = eng(BRI)
    for line in ["I don't want the bit tonight — let's be real.", "I came back, like I said I would.",
                 "I choose the real you. I'm staying."]:
        await e.respond(RespondRequest(player_input=line, situation=Situation(clock=1.0)), debug=True)
    e.relationship.get().persistence_half_life = await assess_persistence(load_character(BRI))
    before = e.relationship.get().affection
    e._age_relationship(366.0)  # one year later  # noqa: SLF001
    print(f"  warm bond (Bri):     affection {before:.2f} -> {e.relationship.get().affection:.2f} after a year "
          f"(fades toward baseline, slowed by persistence + bond depth)")
    wipe(BRI)

    # transient hurt (low trust, NO scar) -> heals up; betrayal (scarred) -> holds
    wipe(CORVIN)
    e = eng(CORVIN)
    from orchestrator.memory.relationship import RelationshipState
    e.relationship._state = RelationshipState(trust=0.22, affection=0.4, respect=0.45, turns=3,  # noqa: SLF001
                                              last_t=1.0, persistence_half_life=200.0)
    before = e.relationship.get().trust
    e._age_relationship(366.0)  # noqa: SLF001
    print(f"  transient fight:     trust {before:.2f} -> {e.relationship.get().trust:.2f} after a year (cools off, heals up)")
    e.relationship._state = RelationshipState(trust=0.22, affection=0.4, respect=0.45, turns=3,  # noqa: SLF001
                                              last_t=1.0, persistence_half_life=200.0, scar_trust=0.6)
    before = e.relationship.get().trust
    e._age_relationship(366.0)  # noqa: SLF001
    print(f"  betrayal (scarred):  trust {before:.2f} -> {e.relationship.get().trust:.2f} after a year "
          f"(scar HOLDS — time doesn't heal it)")
    wipe(CORVIN)


async def main():
    await world_events()
    await persistence_and_decay()


if __name__ == "__main__":
    asyncio.run(main())
