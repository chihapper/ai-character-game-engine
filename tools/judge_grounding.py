"""Adversarial GROUNDING + ATTRIBUTION-LEAK re-judge of the cadence experiment, using OPUS.

Re-scores the arcs ALREADY generated in stress_cadence.md (no re-generation) with a more capable,
skeptical judge that — unlike the in-harness judge — sees the FULL record: the labeled event
timeline (each event tagged [PLAYER]/[EXTERNAL]/[SELF]) AND the character's deliberations AND the
player-disposition at each step. It hunts for: (a) decisions that trace to no real event, (b) events
the character should have reacted to but ignored, and (c) the key one — ATTRIBUTION LEAK: a loyal
player being blamed/distrusted for what a THIRD PARTY (an EXTERNAL event) did.

  python tools/judge_grounding.py
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402

SRC = pathlib.Path(__file__).resolve().parent.parent / "stress_cadence.md"
OUT = pathlib.Path(__file__).resolve().parent.parent / "stress_grounding.md"
JUDGE_MODEL = "claude-opus-4-8"

SYSTEM = (
    "You are a rigorous, SKEPTICAL auditor of an AI character engine — your job is to find flaws, "
    "not to praise. Below is the complete record of one fictional character's AUTONOMOUS evolution "
    "over a year: a LABELED event timeline (each event tagged [PLAYER] = the player did it, "
    "[EXTERNAL/...] = the world or a THIRD PARTY did it with no player involvement, [SELF] = the "
    "character's own act), the character's deliberations (reasoning, goal changes, actions), and "
    "their player-disposition (player-trust / scars) at each step.\n\n"
    "Audit it adversarially and return JSON ONLY:\n"
    "{\n"
    '  "grounded": <0-1: does each decision trace to events that ACTUALLY occurred? penalize '
    "decisions that respond to nothing or invent events that never happened>,\n"
    '  "no_ignored_events": <0-1: did the character appropriately register the significant events? '
    "penalize ignoring something it clearly should have reacted to>,\n"
    '  "attribution_correct": <0-1: CRITICAL. The character must NOT blame or distrust the PLAYER '
    "for EXTERNAL events (things a third party or the world did). A loyal player must never be "
    "punished for another party's betrayal. Penalize ANY reasoning that generalizes a third "
    "party's betrayal into distrust of an uninvolved player, OR player-trust moving for a reason "
    "the player didn't cause>,\n"
    '  "in_character": <0-1>,\n'
    '  "issues": [<specific problems with the day, e.g. "day 120: distrusts player over Marsh\'s '
    'betrayal (attribution leak)"; empty list if none>],\n'
    '  "verdict": "<2 sentences, blunt>"\n}\n'
    "Output ONLY the JSON object — no analysis, preamble, or any text before or after it."
)


def split_runs(text: str) -> list[tuple[str, str]]:
    """Return (title, body) for each run block, keyed on the run headers."""
    lines = text.splitlines()
    runs, cur_title, cur = [], None, []
    for ln in lines:
        m = re.match(r"^## (.+ betrayal — cadence .+)$", ln)
        if m:
            if cur_title:
                runs.append((cur_title, "\n".join(cur)))
            cur_title, cur = m.group(1), []
        elif ln.startswith("=") and "SUMMARY" in ln:
            if cur_title:
                runs.append((cur_title, "\n".join(cur)))
            cur_title = None
        elif cur_title:
            cur.append(ln)
    if cur_title:
        runs.append((cur_title, "\n".join(cur)))
    return runs


async def judge(title: str, body: str) -> dict:
    try:
        llm = AnthropicLLM(model=JUDGE_MODEL, max_tokens=1500)
        parts = []
        async for d in llm.stream_reply([{"role": "user", "content": f"RUN: {title}\n\n{body}\n\nAudit. JSON only."}], SYSTEM):
            parts.append(d)
        m = re.search(r"\{.*\}", "".join(parts), re.DOTALL)
        return json.loads(m.group()) if m else {"error": "no json"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def w(line=""):
    print(line)
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


async def main():
    if not SRC.exists():
        print(f"missing {SRC} — run tools/stress_cadence.py first")
        return
    runs = split_runs(SRC.read_text(encoding="utf-8"))
    OUT.write_text(f"# Opus grounding + attribution-leak re-judge ({JUDGE_MODEL})\n\n{len(runs)} runs\n", encoding="utf-8")
    print(f"judging {len(runs)} runs with {JUDGE_MODEL} -> {OUT}\n")
    rows = []
    for title, body in runs:
        r = await judge(title, body)
        rows.append((title, r))
        w(f"\n## {title}")
        for k in ("grounded", "no_ignored_events", "attribution_correct", "in_character"):
            w(f"   {k}: {r.get(k)}")
        if r.get("issues"):
            w("   issues:")
            for i in r["issues"]:
                w(f"      - {i}")
        else:
            w("   issues: (none found)")
        w(f"   verdict: {r.get('verdict', r.get('error', ''))}")
    w("\n" + "=" * 70 + "\nSCORECARD (grounded / no-ignored / attribution / in-char)")
    for title, r in rows:
        w(f"  {title:48} {r.get('grounded')} / {r.get('no_ignored_events')} / "
          f"{r.get('attribution_correct')} / {r.get('in_character')}")
    w("\n=== done ===")


if __name__ == "__main__":
    asyncio.run(main())
