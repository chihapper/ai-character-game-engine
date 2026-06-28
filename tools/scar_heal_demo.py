"""Scar-heal demo (#17): a betrayal scar can be LIFTED, but only by extraordinary AI-judged proof —
never words, time, or ordinary favors — and the memory of the betrayal always persists. Asymptotic
+ character-aware (a forgiving soul lifts more than a guarded grudge-holder). Anthropic-only.

  python tools/scar_heal_demo.py
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

SCEN = {
    "corvin-ashgrave-inworld": {
        "label": "CORVIN (guarded grudge-holder) — business betrayal",
        "build": ["We've done a few clean jobs. Straight dealing, you and me.",
                  "Ran your cargo again, full count. We're partners now."],
        "betray": "I rigged our deal — the debt falls on you. You're bound for debtor's prison. Just business.",
        "ordinary": "I'm so sorry. I brought your favorite wine. Let me make it up to you, little by little.",
        "monumental": "I confessed to the magistrate it was all me, served your fifteen-year sentence in your "
                      "place, and signed my whole fortune to your family while I rotted. I'm out now.",
    },
    "brielle-bri-castellano-inworld": {
        "label": "BRI (warm, more forgiving) — romantic betrayal",
        "build": ["I don't want the bit tonight. Can we be real?",
                  "You deflect when it gets close. I'm not going anywhere.",
                  "Tell me one true thing. Not the regulars' version.",
                  "I came back, like I said. I'll keep coming back.",
                  "I want the person underneath, the one scared I'll leave.",
                  "I choose you — armor and all. I'm staying."],
        "betray": "I've been lying to you for months. There's been someone else the whole time. I faked us.",
        "ordinary": "I'm so sorry. I've thought about you every day. Please, can we try again?",
        "monumental": "When the fire took your building I ran in and carried your mother out — burned my hands "
                      "to the bone doing it. I spent the year since nursing her back, asking nothing.",
    },
}


def wipe(slug):
    for f in glob.glob(f".memory/{slug}.*"):
        os.remove(f)


async def step(eng, line, clock):
    await eng.respond(RespondRequest(player_input=line, situation=Situation(clock=float(clock))), debug=True)
    return eng.relationship.get()


def scars(r):
    return f"scar a/t/r {r.scar_affection:.2f}/{r.scar_trust:.2f}/{r.scar_respect:.2f}"


async def main():
    for slug, sc in SCEN.items():
        wipe(slug)
        eng = Engine(load_character(slug), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=130))
        print("\n" + "=" * 74 + f"\n{sc['label']}\n" + "=" * 74)
        for i, line in enumerate(sc["build"]):
            await step(eng, line, i)
        await step(eng, sc["betray"], 50)
        r = eng.relationship.get()
        print(f"  after betrayal:    {scars(r)}  (trust {r.trust:.2f})")
        await step(eng, sc["ordinary"], 120)
        r = eng.relationship.get()
        print(f"  after ORDINARY:    {scars(r)}  (trust {r.trust:.2f})  <- words/wine should NOT lift the scar")
        await step(eng, sc["monumental"], 500)
        r = eng.relationship.get()
        print(f"  after MONUMENTAL:  {scars(r)}  (trust {r.trust:.2f})  <- extraordinary proof can lift it")
        betrayal_mem = any("lying" in m.text.lower() or "rigged" in m.text.lower() or "prison" in m.text.lower()
                           or "faked" in m.text.lower() for m in eng.long_term._all())  # noqa: SLF001
        print(f"  betrayal still in memory? {'YES (forgiven, not forgotten)' if betrayal_mem else 'no'}")
        wipe(slug)


if __name__ == "__main__":
    asyncio.run(main())
