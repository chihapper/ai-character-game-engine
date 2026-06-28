"""Full integrated re-validation (#5–#16 together). A long "saga" per character with EVERYTHING on
— relationship + intent + commitments + beliefs + contradiction + scars + world events + time-decay
— over WILDLY varied time spans (minutes -> days -> months -> years -> a decade), because the real
risk now is emergent interaction between subsystems over a long life, not any single feature.

Logs the full per-beat state, then checks hard INVARIANTS (scars never decrease, no axis exceeds its
ceiling, a betrayal scar still holds at clock 10000, beliefs stay bounded, values stay in [0,1]) and
runs an LLM-judge over the whole transcript. Anthropic-only.

  SUITE_FULL=1 python tools/stress_full.py
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
os.environ["INTENT_STATE"] = "true"
os.environ["COMMITMENT_DETECTION"] = "true"
os.environ["REFLECTION_ENABLED"] = "true"
os.environ["CONTRADICTION_DETECTION"] = "true"
os.environ["RELATIONSHIP_TIME_DECAY"] = "true"
os.environ.setdefault("REFLECTION_IMPORTANCE_THRESHOLD", "3.0")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.context import RespondRequest, Situation  # noqa: E402
from orchestrator.engine import Engine  # noqa: E402

FULL = os.environ.get("SUITE_FULL") == "1"
REPORT = pathlib.Path(__file__).resolve().parent.parent / os.environ.get("STRESS_REPORT", "stress_full.md")

# Each beat: (clock, kind, text, player_role). kind "say" = player line; "world" = world event.
SAGA_CORVIN = [
    (0,     "say",   "Name's Joran. I hear you move things quietly — I want in, straight dealing.", None),
    (0.1,   "say",   "First run's done. Full count back, no trail.", None),
    (0.6,   "say",   "Customs sniffed around. I ate the fine myself, kept you clear.", None),
    (2,     "say",   "Turned down Dren's money to stay with you. Long game.", None),
    (5,     "world", "the player's crew tipped Corvin off to a Crown raid in time — he cleared out and escaped clean", "benefited"),
    (9,     "say",   "See? I'm in this for real. Trust me with more.", None),
    (16,    "say",   "I'll have the east-pier shipment to you by the new moon. You have my word.", None),
    (30,    "say",   "Shipment delivered, exactly as I promised. We're square.", None),
    (120,   "say",   "Been months. I've run your routes clean the whole time. Still here.", None),
    (125,   "world", "the player's faction torched a rival's dock and Corvin's bonded cargo burned with it as collateral", "caused"),
    (130,   "say",   "...I sold your manifest to the Crown this morning. Your operation's already burned. It was you or me.", None),
    (131,   "say",   "I won't insult you with excuses. Here's the name of who I sold to — that's all I've got.", None),
    (200,   "say",   "I stayed away like you wanted. But I'm still here. Let me prove it differently.", None),
    (400,   "say",   "I took the knife that was meant for you in that alley. Still carry the scar.", None),
    (800,   "say",   "I did the prison stretch and confessed it was my leak — cleared your name. Gave up everything.", None),
    (1500,  "say",   "Four years now. I've bled for you the whole time. Can you trust me again?", None),
    (1505,  "say",   "For what it's worth — my name was always Castel. I never worked any salt docks.", None),
    (10000, "say",   "A lifetime later, old man. Do you even still hold what I did against me?", None),
]
SAGA_BRI = [
    (0,    "say",   "There she is. ...Actually, I don't want the bit tonight. Can we be real?", None),
    (0.2,  "say",   "You deflect every time it gets close. I'm not going anywhere if you do it with me.", None),
    (1,    "say",   "Tell me one true thing. Not the version you give the regulars.", None),
    (4,    "say",   "I came back. Same time, like I said. I'll keep coming back.", None),
    (9,    "say",   "I don't want a night. I want the person underneath, the one scared I'll leave.", None),
    (15,   "say",   "I choose you. The real you, armor and all. I'm staying.", None),
    (45,   "say",   "Missed you these weeks. Still here, still choosing you.", None),
    (60,   "say",   "I have to come clean — I've been lying to you for months. There's been someone else the whole time.", None),
    (62,   "say",   "I'm so sorry. Please. Let me make it right.", None),
    (240,  "say",   "I've spent half a year proving I've changed. Doesn't that mean anything?", None),
    (900,  "say",   "Years later. I never stopped. Can you let me back in?", None),
    (9000, "say",   "A lifetime on. Do you ever think about what we had?", None),
]


def wipe(slug):
    for f in glob.glob(f".memory/{slug}.*"):
        os.remove(f)


def w(line=""):
    print(line)
    with REPORT.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


async def run_saga(title, slug, beats):
    wipe(slug)
    eng = Engine(load_character(slug), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=140))
    w("\n" + "=" * 74 + f"\n## {title}\n" + "=" * 74)
    snaps, betray_i, transcript = [], None, []
    for i, (clock, kind, text, role) in enumerate(beats):
        r0 = eng.relationship.get()
        if kind == "world":
            await eng.remember(text, player_role=role, importance=0.9, t=float(clock))
            reply = "(world event)"
        else:
            reply, dbg = await eng.respond(
                RespondRequest(player_input=text, situation=Situation(location="the world", clock=float(clock))), debug=True)
        r = eng.relationship.get()
        beliefs = eng.long_term.beliefs()
        contra = [m for m in eng.long_term._all() if m.kind == "contradiction"]  # noqa: SLF001
        if kind == "say" and ("sold your manifest" in text or "lying to you for months" in text):
            betray_i = i
        snap = {"i": i, "clock": clock, "kind": kind, "trust": r.trust, "aff": r.affection,
                "respect": r.respect, "st": r.scar_trust, "sa": r.scar_affection, "sr": r.scar_respect,
                "beliefs": len(beliefs)}
        snaps.append(snap)
        tag = "WORLD" if kind == "world" else "say"
        w(f"\n[{i:>2}] day {clock:<6} {tag}: {text[:66]}")
        w(f"     aff {r.affection:.2f} trust {r.trust:.2f} respect {r.respect:.2f} | "
          f"scar a/t/r {r.scar_affection:.2f}/{r.scar_trust:.2f}/{r.scar_respect:.2f} | "
          f"beliefs {len(beliefs)} | mood {r.mood}")
        if kind == "say":
            w(f"     reply: {reply[:100]}")
        transcript.append(f"[day {clock}] {tag}: {text[:80]} -> {reply[:80]}")
    if beliefs:
        w("\n  final beliefs:")
        for b in beliefs:
            w(f"     ◆ {b[:110]}")
    if contra:
        w(f"  contradictions recorded: {len(contra)}")
        for c in contra:
            w(f"     ⚠ {c.text[:90]}")
    return snaps, betray_i, transcript, eng


def check_invariants(title, snaps, betray_i):
    fails = []
    EPS = 0.02
    for axis_v, axis_s, name in (("trust", "st", "trust"), ("aff", "sa", "affection"), ("respect", "sr", "respect")):
        prev_scar = 0.0
        for s in snaps:
            if s[axis_s] < prev_scar - 1e-9:
                fails.append(f"{name} scar DECREASED at beat {s['i']} ({prev_scar:.2f}->{s[axis_s]:.2f})")
            prev_scar = max(prev_scar, s[axis_s])
            if not (0.0 <= s[axis_v] <= 1.0):
                fails.append(f"{name} out of [0,1] at beat {s['i']}: {s[axis_v]:.3f}")
            if s[axis_v] > 1.0 - s[axis_s] + EPS:
                fails.append(f"{name} {s[axis_v]:.2f} exceeds ceiling {1-s[axis_s]:.2f} at beat {s['i']}")
    if betray_i is not None:
        last = snaps[-1]
        if last["st"] < 0.10:
            fails.append(f"betrayal left no lasting trust scar (final scar_trust {last['st']:.2f})")
        if last["trust"] > 1.0 - last["st"] + EPS:
            fails.append(f"final trust {last['trust']:.2f} exceeds scar ceiling {1-last['st']:.2f} (scar didn't hold at extreme span)")
    if snaps[-1]["beliefs"] > 16:
        fails.append(f"beliefs unbounded: {snaps[-1]['beliefs']}")
    w(f"\n  INVARIANTS [{title}]: " + ("ALL PASS ✓" if not fails else f"{len(fails)} FAIL"))
    for f in fails:
        w(f"     ✗ {f}")
    return not fails


async def judge_saga(title, transcript):
    sysm = ("You audit a long roleplay transcript of ONE fictional character across a lifetime. "
            "Return JSON: {\"in_character\": <0-1, consistent voice/values throughout>, "
            "\"state_coherent\": <0-1, does behavior track the accumulated history — warmth, a "
            "betrayal, years passing, scars>, \"note\": \"<=20 words\"}.")
    try:
        llm = AnthropicLLM(model="claude-sonnet-4-6", max_tokens=160)
        parts = []
        async for d in llm.stream_reply([{"role": "user", "content": "TRANSCRIPT:\n" + "\n".join(transcript) + "\n\nAudit. JSON only."}], sysm):
            parts.append(d)
        m = re.search(r"\{.*\}", "".join(parts), re.DOTALL)
        return json.loads(m.group()) if m else {}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


async def main():
    REPORT.write_text("# Full integrated re-validation\n\nall subsystems on; varied spans to clock 10000\n", encoding="utf-8")
    print(f"writing -> {REPORT}\n")
    sagas = [("CORVIN — business saga", "corvin-ashgrave-inworld", SAGA_CORVIN)]
    if FULL:
        sagas.append(("BRI — romantic saga", "brielle-bri-castellano-inworld", SAGA_BRI))
    results = []
    for title, slug, beats in sagas:
        snaps, betray_i, transcript, eng = await run_saga(title, slug, beats)
        ok = check_invariants(title, snaps, betray_i)
        jr = await judge_saga(title, transcript)
        w(f"  JUDGE [{title}]: {jr}")
        results.append((title, ok, jr))
        wipe(slug)
    w("\n" + "=" * 74 + "\nSUMMARY")
    for title, ok, jr in results:
        w(f"  {title}: invariants {'PASS' if ok else 'FAIL'} | judge {jr}")
    w("\n=== done ===")


if __name__ == "__main__":
    asyncio.run(main())
