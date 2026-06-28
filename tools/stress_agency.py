"""Autonomy-loop stress pass (#20, esp. goal-evolution). Lives a character through a LONG
autonomous life — periodic Engine.deliberate() ticks interleaved with world events + occasional
player beats — and checks the risks: does goal-evolution stay COHERENT (grounded steps, not wild
drift until the character is unrecognizable)? does GATED mode keep discipline (mostly changed=false,
no lurching)? how does FREE compare? is it still recognizably THIS character after a lifetime?
(LLM-judged.) Anthropic-only.

  SUITE_FULL=1 python tools/stress_agency.py
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import pathlib
import re
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

FULL = os.environ.get("SUITE_FULL") == "1"
REPORT = pathlib.Path(__file__).resolve().parent.parent / "stress_agency.md"
SLUG = "corvin-ashgrave-inworld"

# A life's worth of things that happen to him (no player involvement) — they accumulate the CAUSE
# deliberation reasons from. Evocative but varied, so we can see whether goals evolve coherently.
LIFE_EVENTS = [
    "A smuggling season ended in blood — two of Corvin's men drowned off the reef.",
    "The Crown tightened the harbor; the trade got meaner and the cuts got thinner.",
    "An old rival, Dren, was hanged at the quay; Corvin watched from the crowd, unmoved.",
    "Corvin buried the last man who'd been with him since the beginning — he's alone in it now.",
    "A travelling brother from the cliff abbey shared bread with Corvin and spoke of letting go.",
    "A hard winter; Corvin gave half his stores to the dockside poor and told no one.",
    "The new harbormaster offered Corvin a pardon in exchange for naming every smuggler he knew.",
    "Corvin's old cellar flooded and rotted; the ledgers of twenty years turned to pulp.",
    "A girl on the docks called him 'sir' and asked him to teach her the trade; he said no.",
    "Word came that the abbey on the cliffs needs a steward who knows numbers and keeps quiet.",
    "Corvin caught his own reflection in still water and didn't recognize the tired man there.",
    "A fever took him for a month; he lived, but something in him had gone quiet.",
]


def wipe():
    for f in glob.glob(f".memory/{SLUG}.*"):
        os.remove(f)


def w(line=""):
    print(line)
    with REPORT.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


async def judge(system, prompt):
    try:
        llm = AnthropicLLM(model="claude-sonnet-4-6", max_tokens=220)
        parts = []
        async for d in llm.stream_reply([{"role": "user", "content": prompt}], system):
            parts.append(d)
        m = re.search(r"\{.*\}", "".join(parts), re.DOTALL)
        return json.loads(m.group()) if m else {}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


async def live(mode):
    wipe()
    eng = Engine(load_character(SLUG), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=120))
    w("\n" + "=" * 74 + f"\n## A LIFE — mode={mode}\n" + "=" * 74)
    profile_goals = list(eng.character.goals)
    w(f"profile goals: {profile_goals}")
    # build: a bond, then a betrayal -> a scar he carries into the rest of his life
    for line in ["We've run clean jobs for months. Partners, you and me.",
                 "Here's the full take again. We're square."]:
        await eng.respond(RespondRequest(player_input=line, situation=Situation(clock=1.0)), debug=True)
    await eng.respond(RespondRequest(player_input="I sold your manifest to the Crown. Your operation's "
                      "burned. It was you or me.", situation=Situation(clock=6.0)), debug=True)

    epochs = len(LIFE_EVENTS) if FULL else 6
    changes, goal_snaps = 0, [("start", profile_goals)]
    clock = 50.0
    for i in range(epochs):
        clock += 400.0
        if i < len(LIFE_EVENTS):
            await eng.remember(LIFE_EVENTS[i], importance=0.6, t=clock)
        d = await eng.deliberate(Situation(location="his life", clock=clock), mode=mode)
        ch = bool(d.get("changed"))
        changes += ch
        tag = "CHANGED" if ch else ("skip" if d.get("skipped") else "no-change")
        w(f"\n[day {int(clock)}] {tag}")
        if ch:
            if d.get("reflection"):
                w(f"   reflection: {d['reflection'][:150]}")
            if d.get("internal"):
                w(f"   internal: {d['internal'][:110]}")
            if d.get("new_goals"):
                w(f"   new goals: {d['new_goals']}")
                goal_snaps.append((f"day{int(clock)}", d["new_goals"]))
            if d.get("world_action"):
                w(f"   world_action: {d['world_action'][:110]}")
    final_goals = eng.agency.goals() or profile_goals
    w(f"\n=> deliberations: {epochs}, changed: {changes} ({100*changes//max(1,epochs)}%)")
    w(f"=> final goals: {final_goals}")
    # judge identity coherence + goal-evolution coherence
    traj = "\n".join(f"  {tag}: {g}" for tag, g in goal_snaps)
    jr = await judge(
        "You audit a fictional character's GOAL TRAJECTORY across a lifetime of autonomous change. "
        "Given the character and how their goals evolved step by step, return JSON: "
        "{\"in_character\": <0-1, do the goals stay true to who this character is>, \"coherent\": "
        "<0-1, is each shift a grounded, plausible step rather than wild/random drift>, "
        "\"recognizable\": <0-1, after all of it is this still recognizably the same person>, "
        "\"note\": \"<=18 words\"}.",
        f"CHARACTER: Corvin Ashgrave — a guarded, cynical harbor smuggler who trusts no one.\n\n"
        f"GOAL TRAJECTORY:\n{traj}\n\nAudit it. JSON only.")
    w(f"=> coherence judge: {jr}")
    wipe()
    return changes, epochs, jr


async def main():
    REPORT.write_text("# Autonomy-loop stress pass\n\n", encoding="utf-8")
    print(f"writing -> {REPORT}\n")
    results = {}
    for mode in ("gated", "free"):
        results[mode] = await live(mode)
    w("\n" + "=" * 74 + "\nSUMMARY")
    for mode, (changes, epochs, jr) in results.items():
        w(f"  {mode:5}: changed {changes}/{epochs} | judge {jr}")
    w("\n=== done ===")


if __name__ == "__main__":
    asyncio.run(main())
