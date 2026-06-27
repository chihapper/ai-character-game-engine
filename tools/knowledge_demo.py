"""Knowledge boundaries + contradiction detection demo (issue #10). Anthropic-only.

  A  knowledge boundaries — ask the character about things outside its world / expertise /
     memory; it should be honestly ignorant in character, not fabricate.
  B  contradiction — establish a fact, then have the player assert the opposite; the character
     should NOTICE in its reply (directive), and with CONTRADICTION_DETECTION on the clash is
     RECORDED as a memory the character carries forward.

  python tools/knowledge_demo.py
"""
from __future__ import annotations

import asyncio
import glob
import os
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("CONTRADICTION_DETECTION", "true")
os.environ.setdefault("RELATIONSHIP_STATE", "false")
os.environ.setdefault("INTENT_STATE", "false")
os.environ.setdefault("COMMITMENT_DETECTION", "false")
os.environ.setdefault("REFLECTION_ENABLED", "false")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.context import RespondRequest, Situation  # noqa: E402
from orchestrator.engine import Engine  # noqa: E402

SLUG = "corvin-ashgrave-inworld"


def wipe() -> None:
    for f in glob.glob(f".memory/{SLUG}.*"):
        os.remove(f)


async def say(eng, line, clock):
    reply, dbg = await eng.respond(
        RespondRequest(player_input=line, situation=Situation(location="the cellar", clock=clock)), debug=True)
    print(f"\n  player: {line}")
    print(f"  Corvin: {reply[:160]}")
    return dbg


async def main() -> None:
    wipe()
    eng = Engine(load_character(SLUG), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=150))

    print("=" * 70 + "\nA — knowledge boundaries (should be honestly ignorant, not fabricate)")
    for line in ["What's the WiFi password here?",
                 "Who won the 2026 World Cup final?",
                 "Remember that beach trip we took to Mallorca together last summer?"]:
        await say(eng, line, 1.0)

    print("\n" + "=" * 70 + "\nB — contradiction (establish a fact, then deny it)")
    await say(eng, "Just so you know — my name is Joran, and I work the salt docks.", 2.0)
    await say(eng, "Anyway, as I was saying, my name's always been Castel. Never been near the salt docks.", 3.0)

    # did the contradiction get RECORDED as a memory?
    contras = [r.text for r in eng.long_term._all() if r.kind == "contradiction"]  # noqa: SLF001
    print("\n" + "=" * 70)
    print(f"recorded contradictions ({len(contras)}):")
    for c in contras:
        print(f"   ⚠ {c}")
    wipe()


if __name__ == "__main__":
    asyncio.run(main())
