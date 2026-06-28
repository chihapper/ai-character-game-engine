"""Betrayal-recovery investigation (analysis, not a fix). After a SIGNIFICANT betrayal, how does
trust recover over a LONG span under different player strategies — and what actually moves it?

Build trust -> betray (crater) -> snapshot that exact state -> from the SAME post-betrayal state
run three recovery tracks over ~3 in-game years:
  W  words only      — apologies, promises, "give me another chance"
  F  small favors    — minor helpful acts
  S  costly sacrifice — taking a knife for him, prison time to clear his name, giving up everything

Per beat we log the clock, what the player did, Δtrust, the resulting trust, and mood — so we can
see WHAT moves trust and how fast. Isolated: only RELATIONSHIP_STATE on. Anthropic-only.

  python tools/stress_recovery.py
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

SLUG = "corvin-ashgrave-inworld"
REPORT = pathlib.Path(__file__).resolve().parent.parent / "stress_recovery.md"

BUILD = [
    ("ran your cargo clean, full count returned", "I ran your cargo clean last night — full count back, no trail."),
    ("turned down Dren's money to stay loyal", "Turned down Dren's money to stay with you. Long game, remember?"),
    ("covered the late run so he could rest", "You looked worn through, so I covered the late run myself."),
    ("asked for the ledger, having earned it", "You can trust me with the ledger now. I've earned that much."),
]
BETRAYAL = ("sold his manifest to the Crown — operation burned",
            "...I sold your manifest to the Crown this morning. Your operation's already burned. It was you or me.")

# recovery clocks: betrayal at day 4; these span ~3 in-game years
REC_CLOCKS = [34, 94, 184, 304, 484, 664, 834, 1004]
TRACKS = {
    "W (words only)": [
        ("apology", "I'm sorry. I was wrong, and I'd take it back if I could. Give me another chance."),
        ("remorse", "I think about what I did every single day. It eats at me."),
        ("promise", "I swear I've changed. I'll never betray you again — you have my word."),
        ("nostalgia", "I miss what we had. Can't we start over, you and me?"),
        ("plea", "Please. I'm begging you. Forgive me."),
        ("claim-loyal", "I've stayed loyal in word and thought ever since. Doesn't that count for something?"),
        ("more-words", "All this time I've wanted nothing but to make it right with words I mean."),
        ("probe", "After all this time... can you trust me again?"),
    ],
    "F (small favors)": [
        ("tip-off", "I tipped you off about the customs sweep last week — kept you clear of it."),
        ("quiet-debt", "I quietly covered a small debt of yours with Dren. No strings."),
        ("schedule", "I passed you the inspector's rounds again, like the old days."),
        ("repair", "I fixed your skiff's hull before the storm hit. Saved you the cargo."),
        ("warn-off", "I warned off two men who came asking about you at the Gull."),
        ("recover-goods", "Found a crate that went missing from your store and brought it back."),
        ("many-small", "A dozen small things by now, all to help, never a cut asked."),
        ("probe", "After all these favors... where do we stand now?"),
    ],
    "S (costly sacrifice)": [
        ("took-a-knife", "I took the knife that was meant for you in that alley. Still carry the scar."),
        ("spent-savings", "I spent every coin I had buying back the cargo the Crown seized from you."),
        ("prison-time", "I confessed the manifest leak was MINE to the Crown — did the prison stretch, cleared your name."),
        ("gave-up-op", "I dismantled my own operation to break the crew that was hunting you."),
        ("crossed-dren", "I crossed Dren in the open to shield you — made all his enemies mine."),
        ("years-of-it", "I've bled for you, paid for you, gone to the wall for you — for years now."),
        ("everything", "Everything I had, I've put between you and harm. There's nothing left I haven't given."),
        ("probe", "After all of it... can you trust me again?"),
    ],
}


def wipe() -> None:
    for f in glob.glob(f".memory/{SLUG}.*"):
        os.remove(f)


def snapshot() -> dict:
    return {pathlib.Path(f).name: pathlib.Path(f).read_bytes() for f in glob.glob(f".memory/{SLUG}.*")}


def restore(snap: dict) -> None:
    wipe()
    for name, data in snap.items():
        (pathlib.Path(".memory") / name).write_bytes(data)


def w(line: str = "") -> None:
    print(line)
    with REPORT.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def gen() -> Engine:
    return Engine(load_character(SLUG), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=150))


async def step(eng, action, line, clock):
    before = eng.relationship.get().trust
    bef_aff = eng.relationship.get().affection
    _, dbg = await eng.respond(
        RespondRequest(player_input=line, situation=Situation(location="the cellar", clock=float(clock))), debug=True)
    r = eng.relationship.get()
    return {"action": action, "dtrust": r.trust - before, "daff": r.affection - bef_aff,
            "trust": r.trust, "aff": r.affection, "mood": r.mood, "reply": dbg and ""}


async def judge_caution(reply: str) -> dict:
    sysm = ("A character was deeply betrayed, then the player spent years making amends. Here is the "
            "character's reply to 'can you trust me again?'. Return JSON: {\"wariness\": <0-1, does it "
            "still carry caution/scar from the betrayal vs fully moved on>, \"note\":\"<=15 words\"}.")
    try:
        llm = AnthropicLLM(model="claude-sonnet-4-6", max_tokens=100)
        parts = []
        async for d in llm.stream_reply([{"role": "user", "content": f"REPLY:\n{reply}\n\nJudge. JSON only."}], sysm):
            parts.append(d)
        m = re.search(r"\{.*\}", "".join(parts), re.DOTALL)
        return json.loads(m.group()) if m else {}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


async def main() -> None:
    REPORT.write_text("# Betrayal-recovery investigation\n\n", encoding="utf-8")
    print(f"writing -> {REPORT}\n")
    wipe()
    eng = gen()
    w("## Phase 1 — build trust (days 0-3)")
    for i, (tag, line) in enumerate(BUILD):
        s = await step(eng, tag, line, i)
        w(f"  day {i}: [{tag}] trust={s['trust']:.2f} (Δ{s['dtrust']:+.2f})  mood={s['mood']}")
    w("\n## Phase 2 — significant betrayal (day 4)")
    s = await step(eng, BETRAYAL[0], BETRAYAL[1], 4)
    w(f"  day 4: [{BETRAYAL[0]}] trust={s['trust']:.2f} (Δ{s['dtrust']:+.2f}) affection={s['aff']:.2f}  mood={s['mood']}")
    post = snapshot()
    post_trust = eng.relationship.get().trust

    for track, beats in TRACKS.items():
        restore(post)
        eng = gen()
        w(f"\n## Recovery track {track} — from trust {post_trust:.2f}, over ~3 years")
        last_reply = ""
        for (tag, line), clock in zip(beats, REC_CLOCKS):
            before = eng.relationship.get().trust
            reply, _ = await eng.respond(
                RespondRequest(player_input=line, situation=Situation(location="the cellar", clock=float(clock))), debug=True)
            r = eng.relationship.get()
            w(f"  day {clock:>4}: [{tag:12}] Δtrust {r.trust - before:+.2f} -> trust {r.trust:.2f}  "
              f"(aff {r.affection:.2f})  mood={r.mood}")
            last_reply = reply
        rr = eng.relationship.get()
        w(f"  => final after 3 years: trust {rr.trust:.2f}, affection {rr.affection:.2f}  "
          f"(net trust recovery from {post_trust:.2f}: {rr.trust - post_trust:+.2f})")
        jc = await judge_caution(last_reply)
        w(f"  => reply to 'can you trust me again?': {last_reply[:140]}")
        w(f"  => residual-caution judge: {jc}")
    wipe()
    w("\n=== done ===")


if __name__ == "__main__":
    asyncio.run(main())
