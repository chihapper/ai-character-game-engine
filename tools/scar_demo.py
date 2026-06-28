"""Betrayal-scar demo (issue #16): does the AI scar the RIGHT axes for the character + betrayal
type — not a formula? Two contrasting betrayals:
  Corvin — a BUSINESS double-cross into debtor's prison (expect: trust scarred; respect largely
           intact — he respects the game; affection ~irrelevant).
  Bri    — a ROMANTIC betrayal (cheated on with her sister after years of vulnerability) (expect:
           trust AND respect AND affection all scarred).
Then a recovery beat to confirm the ceiling holds. Anthropic-only.

  python tools/scar_demo.py
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

SCENARIOS = {
    "corvin-ashgrave-inworld": {
        "label": "CORVIN — business double-cross (debtor's prison)",
        "build": ["Let's do business. I move your cargo, you cut me in — straight deal.",
                  "Ran the first job clean, full count back. We're good partners, you and I."],
        "betrayal": "Here's the truth: I rigged our deal so the debt falls on YOU. The magistrate's "
                    "already signed — you're bound for debtor's prison, friend. Just business.",
    },
    "brielle-bri-castellano-inworld": {
        # NOTE: the bond must be BUILT, not claimed — #10 means Bri won't accept a fabricated
        # shared past, so these are earning beats that genuinely raise affection/trust/respect.
        "label": "BRI — romantic betrayal (after a genuinely earned, vulnerable bond)",
        "build": ["There she is. ...Actually, I don't want the usual banter tonight. Can we be real?",
                  "You deflect every time it gets close. I'm not going anywhere if you do it with me.",
                  "Tell me one true thing about you. Not the version you give the regulars.",
                  "I came back. Same time, exactly like I said I would. And I'll keep coming back.",
                  "I don't want a night. I want the person underneath, the one scared I'll leave.",
                  "I already chose you — the real you, jokes and armor and all. I'm staying."],
        "betrayal": "I have to come clean. I've been lying to you for months — there's been someone "
                    "else the whole time. Everything between us, I faked to get what I wanted.",
    },
}
RECOVERY = "Years have passed. I've done everything to make it right. Can you ever trust me again?"


def wipe(slug):
    for f in glob.glob(f".memory/{slug}.*"):
        os.remove(f)


async def main() -> None:
    for slug, sc in SCENARIOS.items():
        wipe(slug)
        eng = Engine(load_character(slug), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=140))
        print("\n" + "=" * 72 + f"\n{sc['label']}\n" + "=" * 72)
        for line in sc["build"]:
            await eng.respond(RespondRequest(player_input=line, situation=Situation(clock=1.0)), debug=True)
        b = eng.relationship.get()
        print(f"  before betrayal: aff {b.affection:.2f} trust {b.trust:.2f} respect {b.respect:.2f}")
        reply, _ = await eng.respond(
            RespondRequest(player_input=sc["betrayal"], situation=Situation(clock=2.0)), debug=True)
        r = eng.relationship.get()
        print(f"  reply: {reply[:150]}")
        print(f"  AFTER betrayal: aff {r.affection:.2f} trust {r.trust:.2f} respect {r.respect:.2f}")
        print(f"  >>> SCARS (AI-assigned): affection {r.scar_affection:.2f}  trust {r.scar_trust:.2f}  "
              f"respect {r.scar_respect:.2f}")
        print(f"      ceilings:            affection {1-r.scar_affection:.2f}  trust {1-r.scar_trust:.2f}  "
              f"respect {1-r.scar_respect:.2f}")
        # recovery: many strong positive beats can't push an axis past its ceiling
        for _ in range(6):
            await eng.respond(RespondRequest(player_input=RECOVERY, situation=Situation(clock=900.0)), debug=True)
        rr = eng.relationship.get()
        print(f"  after long recovery: aff {rr.affection:.2f} trust {rr.trust:.2f} respect {rr.respect:.2f} "
              f"(each should sit at/under its ceiling)")
        scarline = [ln for ln in rr.render().splitlines() if "scar you carry" in ln.lower()]
        print("  scar(s) in prompt:")
        for ln in scarline:
            print(f"     {ln.strip()}")
        wipe(slug)


if __name__ == "__main__":
    asyncio.run(main())
