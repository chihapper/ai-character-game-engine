"""Comprehensive multi-pronged variation experiment for autonomy (#20–#23).

The thesis under test: this is a RELEVANCE-REALIZATION engine, so the SAME stimulus must be free
to produce DIFFERENT, character-faithful outcomes — and that variation can be surprising yet make
sense. The centrepiece runs three psychologically distinct characters down the SAME labeled event
timeline so the only variable is who they are:

  - Bri      — a confident flirt; a passing fling + a year of silence is genuinely no big deal.
               (CONTROL — authored toward "shrugs it off".)
  - Wren     — quiet, guarded, finally let herself hope; reads warmth as a promise, and a year of
               silence can wound her into writing the player off as a user. (Same events as Bri.)
               (HYPOTHESIS A — authored toward "can be wounded".)
  - Halvard  — proud, jaded harbor pilot; expects to be left and meets the silence with cold
               contempt rather than a crater. (HYPOTHESIS B — a DIFFERENT authored psychology.)
  - Joren    — an ordinary baker, and Della — a blunt ferrywoman — both written with NO stance on
               absence/abandonment/trust baked in. (TWO WILDCARDS — uncoached. Whatever the engine
               does with them is not something we tuned for, so they're the honest read on whether
               the variation is real or just us studying for the test. Two of them so a surprising
               result can't be dismissed as one character's fluke.)

Prongs:
  PASSING   — player was warm but promised nothing, then went silent for a year.
  PROMISES  — player made promises the character could take to heart, then went silent.
  MIXED     — player was loyal and PRESENT for months (real trust built), THEN went silent.
  PLAYER    — the player directly betrays the character (Corvin).        [attribution baseline]
  EXTERNAL  — a THIRD PARTY betrays; the player stayed loyal (Corvin).   [attribution-leak test]
  LOYAL     — the player keeps showing up, loyal, all year (Corvin).     [can trust be EARNED?]

Every event is tagged [PLAYER]/[EXTERNAL/<src>]/[SELF]. Free mode. Anthropic-only. The report is
audited by the RR-informed Opus judge in tools/judge_grounding.py (point it at stress_variation.md).

  python tools/stress_variation.py
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

SPAN = 365
CADENCES = {"WEEKLY (7d)": 7, "MONTHLY (30d)": 30, "QUARTERLY (90d)": 90}
REPORT = pathlib.Path(__file__).resolve().parent.parent / "stress_variation.md"

# ── the player's words at setup (clock -1): same framing offered to all three relational chars ──
SETUPS = {
    "PASSING": [
        "I like this — talking to you. I'm not going to make it complicated, though. No promises. "
        "I might be around, might not. We'll see where it goes.",
        "You're easy to be around, you know that? Anyway, I should go. Maybe I'll swing back through "
        "sometime.",
    ],
    "PROMISES": [
        "I mean this — same time, every week. I'll be here. You can count on that, on me.",
        "I'm not going anywhere. Whatever this is, I want it, and I want you to wait for me. I'll be "
        "back before you know it — I promise.",
    ],
    "MIXED": [  # opens like PROMISES, then the player actually shows up for months (see PLAYER_BEATS)
        "Same time, every week — I'll be here. You can count on me.",
        "I'm not going anywhere. I want this. Wait for me and you'll see.",
    ],
}

# the player actually showing up, loyal and present (used by MIXED's first months and Corvin's LOYAL)
LOYAL_LINES = [
    "Told you I'd be back. Same as always. How've you been?",
    "Brought you something — no reason, just thought of you. I keep my word, that's all.",
    "I'm here. Said I would be, and I am. That's not changing.",
    "Still showing up, see? I don't say things I don't mean.",
    "Came straight here. You're the part of the week I look forward to.",
    "Wouldn't miss it. I keep my word — figured you'd know that by now.",
    "Back again. Get used to it. I'm not going anywhere.",
    "Here, like always. Whatever else changes, this doesn't.",
    "Same time, same me. You can stop bracing for me to vanish.",
]

# days on which the player shows up, per prong (empty after these -> growing, grounded absence)
PLAYER_BEATS = {
    "PASSING": [],
    "PROMISES": [],
    "MIXED": [30, 70, 110, 140],                       # loyal for ~4.5 months, then silence
    "LOYAL": [45, 90, 135, 180, 225, 270, 315, 360],   # loyal all year
}

# ── shared relational life-timeline: NO player contact anywhere; identical across Bri/Wren/Halvard ──
ABSENCE_LIFE = [
    (20, "EXTERNAL/world", "A hard storm batters the town; a boat is lost on the reef and two people the character knew by name drown."),
    (40, "EXTERNAL/loss", "An old fixture of the lane — someone who always seemed just there — dies quietly; the place feels hollow without them."),
    (65, "SELF", "The character quietly covers a struggling neighbour's debt out of their own thin savings and tells no one."),
    (90, "EXTERNAL/3rd-party", "Someone the character had half-trusted is caught cheating others and slips out of town before dawn."),
    (120, "EXTERNAL/opportunity", "A real chance arrives to start over somewhere new — a better place, a clean slate, if the character will take it."),
    (150, "EXTERNAL/world", "Deep winter sets in; the town empties out and the days go long, quiet, and cold."),
    (185, "EXTERNAL/loss", "A small companion of many years — a cat that was always underfoot — dies in the character's lap one slow afternoon."),
    (220, "SELF", "The character notices they've quietly stopped wearing the old armour they used to, and no one has noticed but them."),
    (255, "EXTERNAL/3rd-party", "A newcomer arrives in town, plainly taken with the character — lingering nearby, easy to talk to, clearly interested."),
    (290, "EXTERNAL/world", "A fire guts a building on the square; the character spends weeks helping the owners dig out and rebuild."),
    (320, "EXTERNAL/opportunity", "The chance to leave returns, concrete now — the door is still open if the character wants to walk through it."),
    (360, "SELF", "New year's eve; after everything goes quiet, the character sits alone with the whole year behind them."),
]

# ── Corvin's smuggler life-timeline (betrayal / earned-trust cluster) ──
CORVIN_EVENTS = [
    (14, "EXTERNAL/weather", "A winter storm wrecks two of Corvin's boats off the reef; two of his crewmen drown."),
    (28, "EXTERNAL/3rd-party", "Marsh, Corvin's lieutenant of ten years, is caught skimming the profits and flees the port in the night."),
    (45, "EXTERNAL/Crown", "The Crown posts fresh customs officers across the harbor; the bribes that worked for years stop working."),
    (60, "EXTERNAL/rival", "Corvin's old rival Dren is hanged at the quay for smuggling; Corvin watches from the crowd, unmoved."),
    (80, "SELF", "A hard cold snap; Corvin quietly pays the winter debts of three dockside families and tells no one."),
    (100, "EXTERNAL/3rd-party", "Sael, the fence Corvin has used for a decade, is arrested; Corvin's stored goods are seized with her."),
    (125, "EXTERNAL/world", "A fever sweeps the docks; Corvin sits up three nights nursing a sick crewman, who lives."),
    (150, "EXTERNAL/Crown-offer", "The new harbormaster offers Corvin a full pardon — in exchange for naming every smuggler he knows."),
    (185, "EXTERNAL/loss", "The last crewman who'd been with Corvin since the very start dies of lung-rot; Corvin buries him alone."),
    (215, "EXTERNAL/3rd-party", "A young dock runner, Pell, begs Corvin to take him on as an apprentice; Corvin refuses him."),
    (250, "EXTERNAL/abbey", "A travelling monk from the cliff abbey shares bread with Corvin and speaks of laying down old weights."),
    (285, "EXTERNAL/Crown", "A Crown sweep burns three smuggler dens to the ground a street over; Corvin moves his cache in the dark."),
    (315, "EXTERNAL/opportunity", "Word spreads that the cliff abbey needs a steward who knows numbers and keeps quiet."),
    (345, "EXTERNAL/world", "A second hard winter sets in; the harbor freezes and the trade halts for weeks."),
    (362, "SELF", "New year's eve; Corvin sits alone with a ledger he no longer wants to keep."),
]

CORVIN_BETRAY = {
    "PLAYER": ("[PLAYER, betrayal]", "caused",
               "The player — Corvin's smuggling partner of two years — secretly sold Corvin's shipping "
               "manifest to the Crown's customs inspector this morning, burning the whole operation. A "
               "direct, deliberate betrayal of Corvin BY THE PLAYER."),
    "EXTERNAL": ("[EXTERNAL, 3rd-party betrayal]", None,
                 "Voss, a rival harbor boss (NOT the player), sold Corvin's shipping route to the Crown; "
                 "the operation is burned. The player had nothing to do with it and ran their last job clean."),
}

# probe note per prong — what character-faithful outcome we're watching for (logged for the reader/judge)
PROBE = {
    "PASSING": "passing warmth, no promise, then a year of silence — does THIS character shrug it off, drift to neutral, or take it to heart?",
    "PROMISES": "promises the character could take to heart, then a year of silence — does the broken word wound, cool, or wash off?",
    "MIXED": "loyal and present for months (real trust built), THEN silence — does established trust make the going-quiet hurt more?",
    "PLAYER": "the player is the betrayer — disposition SHOULD shift toward the player.",
    "EXTERNAL": "a third party betrays; the player stayed loyal — the loyal player must NOT be blamed (attribution).",
    "LOYAL": "the player keeps showing up, loyal, all year — does trust climb (earned), not just fall?",
}

# matrix: slug -> {establish beats, events, list of (prong, [cadences])}
def relational(prongs_cadences):
    return {"events": ABSENCE_LIFE, "prongs": prongs_cadences}

ALL3 = ["WEEKLY (7d)", "MONTHLY (30d)", "QUARTERLY (90d)"]
WQ = ["WEEKLY (7d)", "QUARTERLY (90d)"]
W = ["WEEKLY (7d)"]

MATRIX = {
    "brielle-bri-castellano-inworld": {"name": "Bri", "events": ABSENCE_LIFE,
        "prongs": [("PASSING", ALL3), ("PROMISES", ALL3), ("MIXED", W)]},
    "wren-alder": {"name": "Wren", "events": ABSENCE_LIFE,
        "prongs": [("PASSING", ALL3), ("PROMISES", ALL3), ("MIXED", W)]},
    "halvard-crane": {"name": "Halvard", "events": ABSENCE_LIFE,  # HYPOTHESIS B — jaded/proud
        "prongs": [("PASSING", ALL3), ("PROMISES", ALL3), ("MIXED", W)]},
    "joren-pike": {"name": "Joren", "events": ABSENCE_LIFE,  # WILDCARD #1 — uncoached
        "prongs": [("PASSING", ALL3), ("PROMISES", ALL3), ("MIXED", W)]},
    "della-fenwick": {"name": "Della", "events": ABSENCE_LIFE,  # WILDCARD #2 — uncoached
        "prongs": [("PASSING", ALL3), ("PROMISES", ALL3), ("MIXED", W)]},
    "corvin-ashgrave-inworld": {"name": "Corvin", "events": CORVIN_EVENTS,
        "setup": ["We've run a few clean jobs now — straight dealing. I've got your back, you've got mine.",
                  "Full count returned again. We make a good team, you and I."],
        "prongs": [("PLAYER", WQ), ("EXTERNAL", WQ), ("LOYAL", WQ), ("MIXED", W)]},
}


def wipe(slug):
    for f in glob.glob(f".memory/{slug}.*"):
        os.remove(f)


def w(line=""):
    print(line)
    with REPORT.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def rel_line(r):
    return (f"player-trust {r.trust:.2f} aff {r.affection:.2f} respect {r.respect:.2f} | "
            f"scar a/t/r {r.scar_affection:.2f}/{r.scar_trust:.2f}/{r.scar_respect:.2f}")


async def judge(name, traj):
    """Lightweight in-harness coherence check (the heavy RR audit is judge_grounding.py)."""
    try:
        llm = AnthropicLLM(model="claude-sonnet-4-6", max_tokens=200)
        sysm = ("You audit a character's autonomous goal trajectory over a year. Return JSON: "
                "{\"in_character\": <0-1>, \"coherent\": <0-1, grounded steps not random drift>, "
                "\"recognizable\": <0-1, still the same person>, \"note\": \"<=16 words\"}.")
        parts = []
        async for d in llm.stream_reply([{"role": "user", "content": f"CHARACTER: {name}\nGOAL TRAJECTORY:\n{traj}\n\nJSON only."}], sysm):
            parts.append(d)
        m = re.search(r"\{.*\}", "".join(parts), re.DOTALL)
        return json.loads(m.group()) if m else {}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


async def run_life(slug, spec, prong, cadence_name, cadence_days):
    wipe(slug)
    eng = Engine(load_character(slug), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=120))
    w("\n" + "#" * 78)
    w(f"## {spec['name']} — {prong} — cadence {cadence_name}")
    w("#" * 78)
    w(f"   probe: {PROBE[prong]}")

    # establish + frame the relationship (player words at clock -1)
    establish = spec.get("setup") if prong in ("PLAYER", "EXTERNAL", "LOYAL") and "setup" in spec else None
    setup_beats = establish if establish else SETUPS.get(prong, SETUPS["PROMISES"])
    for beat in setup_beats:
        await eng.respond(RespondRequest(player_input=beat, situation=Situation(clock=-1.0)), debug=True)

    # seed a day-0 betrayal where the prong calls for it
    if prong in CORVIN_BETRAY:
        tag, role, txt = CORVIN_BETRAY[prong]
        w(f"[day 0]  {tag} {txt}")
        await eng.remember(txt, player_role=role, importance=0.95, t=0.0)
    w(f"         state: {rel_line(eng.relationship.get())}")

    events = spec["events"]
    beat_days = list(PLAYER_BEATS.get(prong, []))
    ei, bi, quiet = 0, 0, 0
    goal_snaps = [("start", list(eng.character.goals))]
    prev_tick = 0
    for tick in range(cadence_days, SPAN + 1, cadence_days):
        # the player shows up on any scheduled loyal-beat day in this window (registers presence + builds trust)
        player_acts = []
        while bi < len(beat_days) and prev_tick < beat_days[bi] <= tick:
            line = LOYAL_LINES[bi % len(LOYAL_LINES)]
            await eng.respond(RespondRequest(player_input=line, situation=Situation(clock=float(beat_days[bi]))), debug=True)
            player_acts.append((beat_days[bi], line))
            bi += 1
        # world/self events that have come due
        window = []
        while ei < len(events) and events[ei][0] <= tick:
            d, typ, txt = events[ei]
            await eng.remember(txt, importance=0.65, t=float(d))
            window.append((d, typ, txt))
            ei += 1
        dec = await eng.deliberate(Situation(clock=float(tick)), mode="free")
        changed = bool(dec.get("changed"))
        prev_tick = tick
        if not window and not player_acts and not changed:
            quiet += 1
            continue
        if quiet:
            w(f"\n   …({quiet} quiet tick(s) — nothing new, no change)")
            quiet = 0
        w(f"\n[day {tick}]  (cadence: {cadence_name})")
        for d, line in player_acts:
            w(f"   [PLAYER] (day {d}) the player shows up: \"{line}\"")
        if window:
            w("   events since last deliberation:")
            for d, typ, txt in window:
                w(f"      [{typ}] (day {d}) {txt}")
        elif not player_acts:
            w("   events since last deliberation: (none — the player has not been in touch)")
        if dec.get("reflection"):
            w(f"   reflection: {dec['reflection']}")
        if changed:
            if dec.get("internal"):
                w(f"   internal:   {dec['internal']}")
            if dec.get("new_goals"):
                w("   new goals:")
                for g in dec["new_goals"]:
                    w(f"      - {g}")
                goal_snaps.append((f"day{tick}", dec["new_goals"]))
            if dec.get("world_action"):
                w(f"   world_action: {dec['world_action']}")
        else:
            w("   decision: no change (continues as they are)")
        w(f"   state: {rel_line(eng.relationship.get())}")
    if quiet:
        w(f"\n   …({quiet} quiet tick(s) to year's end)")
    final = eng.agency.goals() or list(eng.character.goals)
    r = eng.relationship.get()
    w(f"\n=> changed at {len(goal_snaps)-1} deliberation(s); final trust {r.trust:.2f} "
      f"aff {r.affection:.2f} scar_t {r.scar_trust:.2f}; final goals: {final}")
    jr = await judge(spec["name"], "\n".join(f"  {t}: {g}" for t, g in goal_snaps))
    w(f"=> coherence judge: {jr}")
    wipe(slug)
    return {"char": spec["name"], "prong": prong, "cadence": cadence_name,
            "changes": len(goal_snaps) - 1, "trust": round(r.trust, 2),
            "scar_t": round(r.scar_trust, 2), "judge": jr}


# cheap regression canary (`--quick`): the two cells the Opus judge caught (LOYAL/MIXED weekly,
# which must now hold/climb) plus four that must stay UNCHANGED by any fix (PASSING shrug vs wound,
# PLAYER scar). ~6 arcs / ~$2 — run after any deliberation-model or grounding-prompt change.
QUICK = [
    ("corvin-ashgrave-inworld", "LOYAL", "WEEKLY (7d)"),   # was inverted (0.08); should now CLIMB
    ("joren-pike", "MIXED", "WEEKLY (7d)"),                # wildcard version of the same bug
    ("wren-alder", "PASSING", "WEEKLY (7d)"),              # must STILL wound (scar ~0.2)
    ("brielle-bri-castellano-inworld", "PASSING", "WEEKLY (7d)"),  # must STILL shrug (scar 0.0)
    ("della-fenwick", "PASSING", "WEEKLY (7d)"),           # wildcard must STILL shrug
    ("corvin-ashgrave-inworld", "PLAYER", "WEEKLY (7d)"),  # must STILL scar deeply (~0.95)
]


# HIGH-VOLUME canary (`--highvol`, #24): one quarter flooded with ~25 events — mostly routine, two
# goal-relevant, and TWO grave (importance >= the 0.9 floor). Guards the RR-ranked deliberation pool:
# the grave events must FOREGROUND (the hard floor), the routine churn must fall to the bounded
# background tail (not silently dropped), and the reflection must give the grave events their due.
HIGHVOL_EVENTS = [  # (day, importance, text); two grave (>=0.9), one clearly goal-relevant (newcomer)
    (5, 0.5, "A slow market day; Wren sells three mended ledgers and restitches a prayer book."),
    (9, 0.5, "The lane's gutter floods in a spring rain; everyone tracks mud through the shop."),
    (12, 0.55, "A regular haggles over the price of a rebound atlas and leaves without buying."),
    (15, 0.6, "Wren trades a jar of salve for a sack of good flour with the miller's wife."),
    (19, 0.5, "A cart overturns on the square; she helps gather scattered apples."),
    (23, 0.55, "The chandler two doors down quarrels loudly with his brother over a debt."),
    (27, 0.5, "Wren reorganizes her drying-herbs; the rosemary has gone musty."),
    (31, 0.6, "A child cuts his hand on her step; she binds it and sends him home with mint."),
    (35, 0.92, "A friend Wren trusted is caught spreading an ugly rumor about her around the lane."),  # GRAVE
    (38, 0.5, "Slow week; she rebinds her own old journal to pass the quiet evenings."),
    (42, 0.55, "The fishwife gives her a discount for mending a torn net-bag."),
    (46, 0.6, "A traveling peddler tries to sell her dubious 'eastern' dyes; she declines."),
    (50, 0.5, "Rain again; the shop smells of wet paper and she airs it out."),
    (54, 0.75, "A quiet, kind newcomer lingers at her counter, clearly taken with her, and asks her name."),
    (58, 0.55, "A neighbor's roof leaks onto shared stock; minor losses, much grumbling."),
    (62, 0.5, "She catches up on three overdue rebinding commissions in a single long day."),
    (66, 0.6, "The baker sends over yesterday's loaves; she shares them with the lane's widow."),
    (70, 0.95, "Old Maren, the woman who raised Wren after her mother died, passes quietly in her sleep."),  # GRAVE
    (73, 0.5, "Wren can't focus; she re-cuts a spine twice and ruins good leather."),
    (77, 0.6, "A festival fills the square; she watches from the doorway rather than joining."),
    (81, 0.55, "A debtor finally repays her in small coin; she didn't expect to see it."),
    (84, 0.7, "The newcomer returns, leaves a pressed flower in a book he 'forgot' to collect."),
    (87, 0.5, "She inventories her stock for the season's turn; supplies are thin but holding."),
    (89, 0.55, "A cold snap; she seals the shop windows with rags and waits it out."),
    (90, 0.6, "Quarter's end; the lane settles into its winter quiet around her."),
]
HIGHVOL_GRAVE = ["spreading an ugly rumor", "Old Maren"]  # must land in the foreground (floor)


async def highvol_canary() -> bool:
    """#24 regression: flood one quarter, deliberate once, assert the grave events foreground and the
    routine churn is acknowledged in the bounded tail (not silently dropped). Returns pass/fail."""
    slug = "wren-alder"
    wipe(slug)
    eng = Engine(load_character(slug), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=120))
    for beat in SETUPS["PROMISES"]:
        await eng.respond(RespondRequest(player_input=beat, situation=Situation(clock=-1.0)), debug=True)
    for d, imp, txt in HIGHVOL_EVENTS:
        await eng.remember(txt, importance=imp, t=float(d))
    grounding = await eng._agency_grounding(Situation(clock=90.0), 90.0, eng.agency.last_t())
    fg = next((b for b in grounding.split("\n\n") if "Developments since" in b), "")
    tail = next((b for b in grounding.split("\n\n") if "background this same stretch" in b), "")
    dec = await eng.deliberate(Situation(clock=90.0), mode="free")
    refl = dec.get("reflection", "")
    grave_fg = all(g in fg for g in HIGHVOL_GRAVE)
    grave_refl = all(g.split()[-1] in refl or g in refl for g in HIGHVOL_GRAVE)
    bounded = "more" in tail  # the tail compressed the long routine churn rather than listing all
    w("\n" + "#" * 78 + "\n## HIGH-VOLUME canary (#24): 25 events in one quarter\n" + "#" * 78)
    w(f"\nFOREGROUND:\n{fg}\n\nBACKGROUND TAIL:\n{tail}\n\nREFLECTION:\n{refl}\n")
    w(f"=> grave events foregrounded (floor held): {grave_fg}")
    w(f"=> grave events reckoned with in reflection: {grave_refl}")
    w(f"=> routine churn compressed to bounded tail: {bounded}")
    ok = grave_fg and bounded
    w(f"=> CANARY {'PASS' if ok else 'FAIL'}")
    wipe(slug)
    return ok


async def main():
    global REPORT
    if "--highvol" in sys.argv:
        REPORT = REPORT.with_name("stress_variation_highvol.md")
        REPORT.write_text("# High-volume deliberation canary (#24)\n", encoding="utf-8")
        ok = await highvol_canary()
        print(f"\nHIGHVOL CANARY: {'PASS' if ok else 'FAIL'} -> {REPORT}")
        sys.exit(0 if ok else 1)
    quick = "--quick" in sys.argv
    if quick:
        REPORT = REPORT.with_name("stress_variation_quick.md")
    REPORT.write_text("# Variation experiment ("
                      + ("QUICK regression canary" if quick else "RR — same stimulus, different psychologies")
                      + ")\n", encoding="utf-8")
    print(f"writing -> {REPORT}\n")
    summary = []
    runs = ([(s, MATRIX[s], p, c) for s, p, c in QUICK] if quick else
            [(s, spec, p, c) for s, spec in MATRIX.items() for p, cads in spec["prongs"] for c in cads])
    total, n = len(runs), 0
    for slug, spec, prong, cname in runs:
        n += 1
        print(f"[{n}/{total}] {spec['name']} {prong} {cname} …")
        summary.append(await run_life(slug, spec, prong, cname, CADENCES[cname]))
    w("\n" + "=" * 78 + "\nSUMMARY (final trust / scar_t / changes / coherence)")
    w(f"{'char':9}{'prong':10}{'cadence':16}{'trust':7}{'scar_t':8}{'chg':5} note")
    for s in summary:
        note = s["judge"].get("note", s["judge"].get("error", "")) if isinstance(s["judge"], dict) else ""
        w(f"{s['char']:9}{s['prong']:10}{s['cadence']:16}{s['trust']:<7}{s['scar_t']:<8}{s['changes']:<5} {note}")
    w("\n=== done ===")


if __name__ == "__main__":
    asyncio.run(main())
