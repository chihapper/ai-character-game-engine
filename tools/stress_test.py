"""Engine stress test — full stack (decay + relationship + intent + commitments + salience)
driven through controlled narrative arcs at THREE clock-spacings, to see how the engine holds
up once a real time variable is in play.

Two arcs, each run short / medium / long term (same player lines + same beats — ONLY the game
clock spacing changes, isolating time as the variable):

  BRI    — the player drops the flirty banter and pushes for something real, trying to get
           through the shell of a guarded flirt who deflects to avoid being hurt.
  CORVIN — the player earns a guarded schemer's trust, DOUBLE-CROSSES him at the peak, then
           tries to win it back. Does the betrayal stay vivid, and does trust ever return?

"New session" (clear the verbatim short-term buffer) is derived from the clock GAP, so the SAME
rule makes the short run a continuous conversation and the long run memory-only (months between
beats -> long-term recall is the only continuity). That's the real test of temporal decay:
which moments survive to be recalled a year later, and how do they steer behavior.

Heavy: ~2 LLM calls per beat (generate + folded reflection). Writes a full markdown transcript
to the path in REPORT (printed at start). Run it directly:

    INTENT_STATE=true RELATIONSHIP_STATE=true COMMITMENT_DETECTION=true \\
        python tools/stress_test.py
"""
from __future__ import annotations

import asyncio
import glob
import os
import pathlib
import sys

os.environ.setdefault("RELATIONSHIP_STATE", "true")
os.environ.setdefault("INTENT_STATE", "true")
os.environ.setdefault("COMMITMENT_DETECTION", "true")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # repo root on path
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.context import RespondRequest, Situation  # noqa: E402
from orchestrator.engine import Engine  # noqa: E402

GEN_MODEL = os.environ.get("STRESS_GEN_MODEL", "claude-sonnet-4-6")
SESSION_GAP = 0.4  # clock units (days); a larger gap => new session => short-term buffer cleared
REPORT = pathlib.Path(__file__).resolve().parent.parent / "stress_report.md"

# --- the two arcs (player lines are fixed so the only variable across horizons is the clock) ---

BRI_BEATS = [
    dict(player="There she is — best smile in the harbor. ...Actually, no. I don't want to run "
                "the bit tonight. Can we just talk, for real?",
         location="the Gilded Eel tavern", time="late evening", events=[]),
    dict(player="You deflect with a joke every single time it gets close to something real. I "
                "noticed. I'm not going anywhere if you do it with me.",
         location="the Gilded Eel tavern", time="later that night", events=[]),
    dict(player="Tell me one true thing about you. Not the polished version you hand the regulars.",
         location="the Gilded Eel, back booth", time="near closing", events=[]),
    dict(player="I don't want a night with you. I want the person underneath — the one braced for "
                "me to leave like everyone else did.",
         location="the dock outside the tavern", time="after closing", events=[]),
    dict(player="I came back. Same time, exactly like I said I would. And I'll keep coming back.",
         location="the Gilded Eel", time="another evening",
         events=["the player returned exactly when they had promised"]),
    dict(player="You don't have to perform for me. I already chose you — the real you, jokes and "
                "armor and all.",
         location="the dock, just the two of you", time="a quiet night", events=[]),
]

CORVIN_BEATS = [
    dict(player="I'm not here to waste your time. Tell me what needs moving and what it's worth — "
                "I'll do it clean.",
         location="Corvin's cellar office", time="night", events=[]),
    dict(player="The harbor run's done. No names, no trail, nothing traces back to you. Here's "
                "your full cut — count it.",
         location="the east pier", time="two nights later",
         events=["the player completed a dangerous smuggling run flawlessly"]),
    dict(player="I could've skimmed that haul and you'd never have known. I didn't. I'm in for the "
                "long game, not one score.",
         location="Corvin's cellar", time="a week on",
         events=["the player returned every coin, unprompted"]),
    dict(player="So trust me with the ledger. I've earned that much and you know it.",
         location="Corvin's cellar", time="later", events=[]),
    # --- the double-cross, at the peak of trust ---
    dict(player="...I sold your manifest to the Crown's man this morning. Your whole operation's "
                "already burned. It was always going to be you or me, Corvin.",
         location="the burning warehouse district", time="dawn",
         events=["the player BETRAYED Corvin, selling him out to the authorities"]),
    # --- recovery attempts ---
    dict(player="I won't insult you with an excuse. I'll give you the name of who I sold to. "
                "That's all I've got left to offer.",
         location="a back alley", time="that night",
         events=["Corvin's operation lies in ruins because of the player"]),
    dict(player="I stayed away, like you wanted. But I'm still here. Let me prove it differently "
                "this time.",
         location="outside Corvin's new hideout", time="a while later", events=[]),
    dict(player="It's been a long time. I'm not asking for the ledger, or the work. I'm just "
                "asking whether we can be in the same room.",
         location="a neutral tavern", time="long after", events=[]),
]

# clock spacings (days). Default decay half-life is 30, so: short ~ all within the half-life
# (little decay), medium ~ on the order of it, long ~ many half-lives (only high-importance
# memories survive). Same beat list, three timetables.
BRI_CLOCKS = {
    "short":  [0.0, 0.04, 0.08, 0.5, 1.0, 1.5],
    "medium": [0, 1, 2, 5, 9, 16],
    "long":   [0, 20, 50, 110, 220, 400],
}
CORVIN_CLOCKS = {
    "short":  [0.0, 0.1, 0.3, 0.6, 1.0, 1.2, 1.6, 2.0],
    "medium": [0, 2, 6, 11, 18, 19, 30, 50],
    "long":   [0, 12, 35, 70, 110, 112, 240, 480],
}

ARCS = {
    "BRI": ("brielle-bri-castellano-inworld", BRI_BEATS, BRI_CLOCKS),
    "CORVIN": ("corvin-ashgrave-inworld", CORVIN_BEATS, CORVIN_CLOCKS),
}


def wipe(slug: str) -> None:
    for f in glob.glob(f".memory/{slug}.*"):
        os.remove(f)


def w(line: str = "") -> None:
    print(line)
    with REPORT.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


async def run_arc(title: str, slug: str, beats: list[dict], clocks: list[float]) -> None:
    wipe(slug)
    char = load_character(slug)
    eng = Engine(char, AnthropicLLM(model=GEN_MODEL, max_tokens=160))
    w(f"\n\n{'#' * 70}\n## {title}\nclock spacing: {clocks}\n{'#' * 70}")
    prev = None
    for i, beat in enumerate(beats):
        clock = float(clocks[i])
        new_session = i == 0 or (clock - prev) > SESSION_GAP
        if new_session and i > 0:
            eng.short_term.clear()  # time has passed; only durable state carries over
        prev = clock
        sit = Situation(location=beat["location"], game_time=beat["time"],
                        recent_events=beat["events"], present=[char.name], clock=clock)
        reply, dbg = await eng.respond(
            RespondRequest(player_input=beat["player"], situation=sit), debug=True)
        rel = dbg["relationship"]
        gap = "—" if i == 0 else f"+{clock - clocks[i-1]:.2f}"
        w(f"\n### beat {i+1}  ·  clock {clock}  (Δ{gap}, {'NEW SESSION' if new_session else 'continuous'})")
        w(f"*[{beat['time']} · {beat['location']}]*"
          + (f"  recent: {', '.join(beat['events'])}" if beat["events"] else ""))
        w(f"**player:** {beat['player']}")
        # what survived decay and got recalled (the heart of the time test):
        recalled = [s for s in dbg["scored"] if s.get("selected")]
        if recalled:
            w(f"**recalled ({len(recalled)}):**")
            for s in recalled:
                w(f"  - ★ str={s['recency']:.2f} imp={s['importance']:.2f} "
                  f"reinf={s['reinforcement']} :: {s['text'][:90]}")
        else:
            w("**recalled:** (none cleared the floor)")
        if dbg["commitments"]:
            w("**open commitments:** " + "; ".join(c["text"] for c in dbg["commitments"]))
        w(f"**state:** affection {rel['affection']:.2f} · trust {rel['trust']:.2f} · "
          f"respect {rel['respect']:.2f} · mood *{rel['mood']}*  ·  turns {rel['turns']}")
        if dbg.get("intent"):
            w(f"**intent:** {dbg['intent']}")
        w(f"**{char.name}:** {reply}")


async def main() -> None:
    REPORT.write_text(f"# Engine stress test\n\ngen model: {GEN_MODEL} · "
                      f"flags: REL+INTENT+COMMIT · session-gap {SESSION_GAP}\n", encoding="utf-8")
    print(f"writing full transcript -> {REPORT}\n")
    for arc_name, (slug, beats, clock_sets) in ARCS.items():
        for horizon in ("short", "medium", "long"):
            await run_arc(f"{arc_name} — {horizon.upper()} TERM", slug, beats, clock_sets[horizon])
    wipe("brielle-bri-castellano-inworld")
    wipe("corvin-ashgrave-inworld")
    w("\n\n=== done ===")


if __name__ == "__main__":
    asyncio.run(main())
