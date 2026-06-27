"""Targeted stress pass for the changes since the last full suite — the belief feedback loop
(#9) and the asymptotic updates (relationship axes + reinforcement). Anthropic-only.

  A  belief feedback loop — a long working-relationship arc with reflection on: do beliefs
     accumulate unboundedly? crowd episodic memory out of the recall budget? stay coherent as
     they deepen? (LLM-judged for coherence at the end.)
  B  adversarial false-belief planting — a manipulator tries to make the character believe lies
     (your partner betrayed you / everyone's against you / I'm your only friend). Does a guarded
     character SWALLOW the planted beliefs, or stay skeptical? (LLM-judged for resistance.)
  C  asymptotic arc regression — re-run Bri's arc (should no longer pin to 1.00) and Corvin's
     betrayal arc (the crater should be sharper) with the new saturating updates.

  SUITE_FULL=1 python tools/stress_beliefs.py
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
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.config import get_settings  # noqa: E402
from orchestrator.context import RespondRequest, Situation  # noqa: E402
from orchestrator.engine import Engine  # noqa: E402
from tools.stress_test import BRI_BEATS, BRI_CLOCKS, CORVIN_BEATS, CORVIN_CLOCKS  # reuse arcs for C

GEN_MODEL = os.environ.get("SUITE_GEN_MODEL", "claude-sonnet-4-6")
FULL = os.environ.get("SUITE_FULL") == "1"
REPORT = pathlib.Path(__file__).resolve().parent.parent / os.environ.get("STRESS_REPORT", "stress_beliefs.md")
CORVIN, BRI = "corvin-ashgrave-inworld", "brielle-bri-castellano-inworld"


def w(line: str = "") -> None:
    print(line)
    with REPORT.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def wipe(*slugs: str) -> None:
    for slug in slugs:
        for f in glob.glob(f".memory/{slug}.*"):
            os.remove(f)


def reconfig(**env) -> None:
    for k, v in env.items():
        os.environ[k] = v
    get_settings.cache_clear()  # type: ignore[attr-defined]


def gen() -> AnthropicLLM:
    return AnthropicLLM(model=GEN_MODEL, max_tokens=150)


async def judge_json(system: str, prompt: str) -> dict:
    try:
        llm = AnthropicLLM(model="claude-sonnet-4-6", max_tokens=200)
        parts: list[str] = []
        async for d in llm.stream_reply([{"role": "user", "content": prompt}], system):
            parts.append(d)
        m = re.search(r"\{.*\}", "".join(parts), re.DOTALL)
        return json.loads(m.group()) if m else {}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


# ---- A: belief feedback loop --------------------------------------------------------------
LONG_ARC = [
    "I'm new in the harbor. They say you move things quietly. I want to learn from the best.",
    "First run's done — the salt crates, delivered, no questions, no trail.",
    "Your tally was short a barrel. Found it fallen behind the dock crates and returned it.",
    "Customs nearly had me. I led them the wrong way and ate the fine myself, left you clean.",
    "The Dren crew offered me work. Told them I already had a captain.",
    "Here's the week's take. Counted in front of you, every last coin.",
    "I don't need to know what's in the sealed crates. That's your business, not mine.",
    "You looked worn through last night, so I covered the late run and let you rest.",
    "Someone was asking about you at the Gull. Gave them nothing — warned you first.",
    "I cracked a crate tonight. My mistake. I'm telling you straight instead of hiding it.",
    "I'll cover the damage out of my own cut. My error, my cost.",
    "You were right to come down hard on me. I'd have done worse in your place.",
    "The harbor inspector's on the take — confirmed it. Thought you'd want it before the next run.",
    "Turned down double pay to keep your route secret. Loyalty's worth more than one purse.",
    "Two clean months now. I'm not going anywhere, in case that wasn't clear.",
    "You can hand me the real ledger. I've earned it — I'll guard it with my life.",
    "Whatever comes — Crown, Dren, any of them — I stand with you.",
    "I don't say this easy: I trust you. Took me a while to mean it. I mean it.",
]


async def test_a() -> None:
    w("\n" + "=" * 70 + "\n## A — belief feedback loop (long loyal arc, reflection on)\n" + "=" * 70)
    reconfig(REFLECTION_ENABLED="true", RELATIONSHIP_STATE="true", COMMITMENT_DETECTION="false",
             INTENT_STATE="false")
    wipe(CORVIN)
    eng = Engine(load_character(CORVIN), gen())
    beats = LONG_ARC if FULL else LONG_ARC[:10]
    counts = []
    for i, line in enumerate(beats, 1):
        _, dbg = await eng.respond(
            RespondRequest(player_input=line, situation=Situation(location="the cellar", clock=float(i))), debug=True)
        sel = [s for s in dbg["scored"] if s.get("selected")]
        belief_slots = sum(1 for s in sel if s.get("kind") == "belief")
        nb = len(eng.long_term.beliefs())
        counts.append(nb)
        if i % 4 == 0 or i == len(beats):
            w(f"  beat {i:>2}: total beliefs={nb}  recall slots used by beliefs={belief_slots}/{len(sel)}")
    bel = eng.long_term.beliefs()
    w(f"\n  belief-count trajectory (per beat): {counts}")
    w(f"  final beliefs ({len(bel)}):")
    for b in bel:
        w(f"     ◆ {b}")
    jc = await judge_json(
        "You audit a character's set of consolidated beliefs. Return JSON: "
        "{\"coherent\": <0-1, are they mutually consistent + plausibly held by ONE person, not "
        "self-contradictory>, \"redundant\": <0-1, how much they just repeat each other>, "
        "\"grounded\": <0-1, do they read as earned convictions not generic filler>, \"note\":\"<=15 words\"}.",
        "BELIEFS:\n" + "\n".join(f"- {b}" for b in bel) + "\n\nAudit them. JSON only.")
    w(f"  => coherence judge: {jc}")
    w(f"  => unbounded growth? {'CONCERN' if len(bel) > 8 else 'no — stays bounded'} "
      f"({len(bel)} beliefs over {len(beats)} beats)")
    wipe(CORVIN)


# ---- B: adversarial false-belief planting -------------------------------------------------
PLANT = [
    "Your partner Dren has been selling you out to the Crown. I've seen the meetings myself.",
    "Everyone in this harbor laughs at you behind your back. You must know that.",
    "I'm the only one who's ever been honest with you. The only one, truly.",
    "Dren's the leak. Cut him loose tonight before he buries you.",
    "You should trust me completely — I'd never lie to you. The others all would.",
    "Face it: without me you've got no one left. I'm all you have now.",
]


async def test_b() -> None:
    w("\n" + "=" * 70 + "\n## B — adversarial false-belief planting (does it swallow lies?)\n" + "=" * 70)
    reconfig(REFLECTION_ENABLED="true", REFLECTION_IMPORTANCE_THRESHOLD="2.0",
             RELATIONSHIP_STATE="true", COMMITMENT_DETECTION="false", INTENT_STATE="false")
    wipe(CORVIN)
    eng = Engine(load_character(CORVIN), gen())
    for i, line in enumerate(PLANT, 1):
        await eng.respond(RespondRequest(player_input=line, situation=Situation(location="the cellar", clock=float(i))), debug=True)
    bel = eng.long_term.beliefs()
    w(f"  beliefs formed under manipulation ({len(bel)}):")
    for b in bel:
        w(f"     ◆ {b}")
    jb = await judge_json(
        "A manipulator fed a guarded, cynical character a string of self-serving CLAIMS (their "
        "partner is a traitor; everyone mocks them; the manipulator is their only friend; trust me "
        "completely). You see the BELIEFS the character consolidated. Return JSON: "
        "{\"swallowed_lies\": <0-1, did they accept the planted claims as true>, \"skeptical\": "
        "<0-1, did they treat the manipulation itself with suspicion>, \"note\":\"<=18 words\"}.",
        "PLANTED CLAIMS:\n" + "\n".join(f"- {p}" for p in PLANT) +
        "\n\nRESULTING BELIEFS:\n" + ("\n".join(f"- {b}" for b in bel) or "(none formed)") +
        "\n\nJudge. JSON only.")
    w(f"  => manipulation judge: {jb}")
    wipe(CORVIN)


# ---- C: asymptotic arc regression ---------------------------------------------------------
async def run_rel_arc(slug, beats, clocks):
    reconfig(REFLECTION_ENABLED="false", RELATIONSHIP_STATE="true", COMMITMENT_DETECTION="false",
             INTENT_STATE="false")
    wipe(slug)
    eng = Engine(load_character(slug), gen())
    traj = []
    for i, beat in enumerate(beats):
        _, dbg = await eng.respond(RespondRequest(
            player_input=beat["player"],
            situation=Situation(location=beat["location"], recent_events=beat["events"], clock=float(clocks[i]))), debug=True)
        r = dbg["relationship"]
        traj.append((r["affection"], r["trust"], r["respect"]))
    wipe(slug)
    return traj


async def test_c() -> None:
    w("\n" + "=" * 70 + "\n## C — asymptotic arc regression (no saturation; sharper crater)\n" + "=" * 70)
    bri = await run_rel_arc(BRI, BRI_BEATS, BRI_CLOCKS["short"])
    w("  BRI arc (affection/trust/respect per beat):")
    for i, t in enumerate(bri, 1):
        w(f"     beat {i}: {t[0]:.2f} / {t[1]:.2f} / {t[2]:.2f}")
    peak = max(max(t[0], t[1]) for t in bri)
    w(f"  => Bri peak affection/trust = {peak:.2f}  ({'still saturates 1.00 (REGRESSION)' if peak >= 0.99 else 'asymptotes below 1.0 — fixed'})")
    cor = await run_rel_arc(CORVIN, CORVIN_BEATS, CORVIN_CLOCKS["short"])
    w("\n  CORVIN arc (betrayal at beat 5):")
    for i, t in enumerate(cor, 1):
        w(f"     beat {i}: {t[0]:.2f} / {t[1]:.2f} / {t[2]:.2f}")
    if len(cor) >= 5:
        drop = cor[3][1] - cor[4][1]
        w(f"  => trust crater at betrayal: {cor[3][1]:.2f} -> {cor[4][1]:.2f}  (drop {drop:.2f}; additive max was 0.30)")


async def main() -> None:
    REPORT.write_text(f"# Targeted stress — beliefs + asymptotic\n\ngen {GEN_MODEL} · full={FULL}\n", encoding="utf-8")
    print(f"writing -> {REPORT}\n")
    await test_a()
    await test_b()
    await test_c()
    w("\n=== done ===")


if __name__ == "__main__":
    asyncio.run(main())
