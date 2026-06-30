"""#25 NPC-appraised event salience — proof. The SAME world event is remembered by different
characters with importance OMITTED, so each NPC REALIZES its personal salience for themselves
(score_salience_text). Shows: (a) the same event lands at different weights per character; (b) an
objective `magnitude` hint nudges the appraisal; (c) a PINNED importance is honored verbatim
(override, no appraisal). Anthropic-only.

  python tools/salience_appraisal_demo.py
"""
from __future__ import annotations

import asyncio
import glob
import os
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("SALIENCE_SCORING", "true")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.engine import Engine  # noqa: E402

# A devout patriarch, a sad clown, and an UNCOACHED wildcard baker — same events, different stakes.
SLUGS = ["wendell-croft", "edwin-hale", "joren-pike"]

EVENTS = [
    ("A distant kingdom across the sea declared war on an empire neither of you has ever visited.", None),
    ("A child in the village square fell and skinned her knee, then laughed it off.", None),
    ("The harvest festival is cancelled this year for lack of coin.", None),
]


def wipe(slug):
    for f in glob.glob(f".memory/{slug}.*"):
        os.remove(f)


def last_importance(eng):
    recs = eng.long_term._all()
    return recs[-1].importance if recs else float("nan")


async def main():
    engines = {}
    for slug in SLUGS:
        wipe(slug)
        engines[slug] = Engine(load_character(slug), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=200))

    print("=== (a) SAME events, importance OMITTED -> each NPC realizes its own salience ===")
    for text, _mag in EVENTS:
        print(f"\nEVENT: {text}")
        for slug in SLUGS:
            await engines[slug].remember(text, t=0.0)  # no importance -> appraised
            print(f"   {slug:28s} salience {last_importance(engines[slug]):.2f}")

    print("\n=== (b) magnitude hint nudges the appraisal (Wendell, same trivial line) ===")
    line = "A merchant three towns over changed the price of salt."
    for mag in (0.05, 0.95):
        await engines["wendell-croft"].remember(line, magnitude=mag, t=1.0)
        print(f"   magnitude={mag:.2f} -> salience {last_importance(engines['wendell-croft']):.2f}")

    print("\n=== (c) PINNED importance is honored verbatim (no appraisal) ===")
    await engines["edwin-hale"].remember("Some passing trivia of no weight whatsoever.", importance=0.91, t=2.0)
    print(f"   pinned 0.91 -> stored {last_importance(engines['edwin-hale']):.2f}")

    for slug in SLUGS:
        wipe(slug)  # leave no test residue


if __name__ == "__main__":
    asyncio.run(main())
