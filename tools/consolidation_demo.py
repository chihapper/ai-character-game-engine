"""Reflection / consolidation demo (issue #9): drive a character through consistent experience
and watch a BELIEF crystallize from the raw exchanges, then confirm it resurfaces through normal
recall and colours a later turn. Anthropic-only; never touches Inworld.

    python tools/consolidation_demo.py
"""
from __future__ import annotations

import asyncio
import glob
import os
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("REFLECTION_ENABLED", "true")
os.environ.setdefault("REFLECTION_IMPORTANCE_THRESHOLD", "2.0")  # trigger within a few beats
os.environ.setdefault("RELATIONSHIP_STATE", "false")  # isolate the belief mechanism
os.environ.setdefault("COMMITMENT_DETECTION", "false")
os.environ.setdefault("INTENT_STATE", "false")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.context import RespondRequest, Situation  # noqa: E402
from orchestrator.engine import Engine  # noqa: E402

SLUG = "corvin-ashgrave-inworld"
BEATS = [
    "I ran the cargo clean last night. No names, no trail, full count handed back.",
    "Customs came sniffing this morning. I gave them nothing — took the heat myself, left you out of it.",
    "I could've sold your route to the Dorn crew for double. Turned them down flat.",
    "Here's your manifest back, sealed. Didn't read a word of it, didn't have to.",
    "Whatever the next job is, I'm your man. No questions, no cut off the top.",
]
PROBE = "So. After all that — where do we stand, you and me?"


def wipe() -> None:
    for f in glob.glob(f".memory/{SLUG}.*"):
        os.remove(f)


async def main() -> None:
    wipe()
    eng = Engine(load_character(SLUG), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=140))
    seen = 0
    for i, line in enumerate(BEATS, 1):
        _, dbg = await eng.respond(
            RespondRequest(player_input=line, situation=Situation(location="Corvin's cellar", clock=float(i))),
            debug=True)
        beliefs = eng.long_term.beliefs()
        new = beliefs[seen:]
        seen = len(beliefs)
        print(f"\nbeat {i}: \"{line[:60]}...\"")
        if new:
            print("   *** belief(s) consolidated:")
            for b in new:
                print(f"      ◆ {b}")
        else:
            print("   (no belief yet — accumulating)")

    print("\n" + "=" * 70)
    print(f"all beliefs Corvin now holds ({len(eng.long_term.beliefs())}):")
    for b in eng.long_term.beliefs():
        print(f"   ◆ {b}")

    # Does the belief resurface through normal recall on a later, related turn?
    _, dbg = await eng.respond(
        RespondRequest(player_input=PROBE, situation=Situation(location="Corvin's cellar", clock=99.0)),
        debug=True)
    print(f"\nprobe (day 99): \"{PROBE}\"")
    print("recalled (★ = belief surfaces if consolidation fed back into recall):")
    for s in dbg["scored"]:
        if s.get("selected"):
            tag = "◆BELIEF" if s.get("kind") == "belief" else "  mem  "
            print(f"   {tag} str={s['recency']:.2f} imp={s['importance']:.2f} :: {s['text'][:70]}")
    wipe()


if __name__ == "__main__":
    asyncio.run(main())
