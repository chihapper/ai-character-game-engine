"""Cadence + event-attribution experiment for autonomy (#20). A FIXED, explicit, labeled event
timeline over one in-game year, run at three deliberation cadences (how often the game asks the
character to deliberate) — WEEKLY (7d), MONTHLY (30d), QUARTERLY (90d) — for two characters
(Corvin, Bri) and two betrayal variants:
  - PLAYER:   the player (the NPC's partner) is the betrayer  -> shifts disposition TOWARD the player.
  - EXTERNAL: a THIRD PARTY betrays the NPC; the player stayed loyal -> shapes worldview, NOT
              player-disposition directly. Tests whether external events colour the NPC fairly.

Every event is tagged [PLAYER] / [EXTERNAL/<source>] / [SELF] so the causality is explicit. Free
mode (the default). Anthropic-only.

  python tools/stress_cadence.py
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
REPORT = pathlib.Path(__file__).resolve().parent.parent / "stress_cadence.md"

CHARS = {
    "corvin-ashgrave-inworld": {
        "name": "Corvin",
        "setup": ["We've run a few clean jobs now — straight dealing. I've got your back, you've got mine.",
                  "Full count returned again. We make a good team, you and I."],
        "betray_player": "The player — Corvin's smuggling partner of two years — secretly sold Corvin's "
                         "shipping manifest to the Crown's customs inspector this morning, burning the whole "
                         "operation. A direct, deliberate betrayal of Corvin BY THE PLAYER.",
        "betray_external": "Voss, a rival harbor boss (NOT the player), sold Corvin's shipping route to the "
                           "Crown; the operation is burned. The player had nothing to do with it and ran their "
                           "last job clean.",
        "events": [
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
        ],
    },
    "brielle-bri-castellano-inworld": {
        "name": "Bri",
        "setup": ["I don't want to run the usual bit with you. I actually like talking to you — for real.",
                  "You keep showing up, same time, like you said. I'm starting to count on that."],
        "betray_player": "The player — Bri's partner, who she'd let past her guard for the first time in years — "
                         "was revealed to have been lying to her for months and seeing someone else the whole "
                         "time. A direct betrayal of Bri BY THE PLAYER.",
        "betray_external": "Bri's sister Mara (NOT the player) was revealed to have slept with Bri's ex and spread "
                           "cruel rumors about her around the docks. The player had nothing to do with it and has "
                           "been steady and kind to her.",
        "events": [
            (14, "EXTERNAL/loss", "Old Tom, a regular Bri adored, dies; his usual stool sits empty and the tavern feels hollow."),
            (28, "EXTERNAL/rival", "A flashy new bar opens across the square and pulls half of Bri's regulars away."),
            (45, "SELF", "Bri quietly covers a struggling coworker's rent out of her own tips and tells no one."),
            (60, "EXTERNAL/world", "A kitchen fire guts the tavern's back room; Bri spends weeks helping rebuild it."),
            (80, "EXTERNAL/3rd-party", "Bri's sister Mara turns up drunk, makes a scene at the bar, and vanishes again before dawn."),
            (100, "EXTERNAL/loss", "Bri's landlord sells the building; she may lose the little flat above the bar she's had for years."),
            (125, "SELF", "For the first time in memory, Bri turns down a charming regular's advances without a second thought."),
            (150, "EXTERNAL/opportunity", "A wealthy patron offers to set Bri up in a place of her own across town, her name on the door."),
            (185, "EXTERNAL/world", "Deep winter; the docks empty out and the tavern goes quiet and cold for weeks."),
            (215, "EXTERNAL/3rd-party", "A new barmaid, fresh in town, looks at Bri the way Bri once looked at the old veterans."),
            (250, "EXTERNAL/loss", "Bri's cat of twelve years dies in her lap by the stove one slow afternoon."),
            (285, "SELF", "Bri notices she's stopped doing 'the bit' — the constant performance — and no one's noticed but her."),
            (315, "EXTERNAL/world", "The flashy rival bar burns down; some of Bri's regulars drift back, sheepish."),
            (345, "EXTERNAL/opportunity", "The patron's offer still stands: her own place, her own name, if she'll leave the old tavern."),
            (362, "SELF", "New year's eve; after close, Bri pours herself a drink and sits alone with the quiet."),
        ],
    },
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
    try:
        llm = AnthropicLLM(model="claude-sonnet-4-6", max_tokens=200)
        parts = []
        sysm = ("You audit a character's autonomous goal trajectory over a year. Return JSON: "
                "{\"in_character\": <0-1>, \"coherent\": <0-1, grounded steps not random drift>, "
                "\"recognizable\": <0-1, still the same person>, \"note\": \"<=16 words\"}.")
        async for d in llm.stream_reply([{"role": "user", "content": f"CHARACTER: {name}\nGOAL TRAJECTORY:\n{traj}\n\nJSON only."}], sysm):
            parts.append(d)
        m = re.search(r"\{.*\}", "".join(parts), re.DOTALL)
        return json.loads(m.group()) if m else {}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


async def run_life(slug, spec, variant, cadence_name, cadence_days):
    wipe(slug)
    eng = Engine(load_character(slug), AnthropicLLM(model="claude-sonnet-4-6", max_tokens=120))
    w("\n" + "#" * 78)
    w(f"## {spec['name']} — {variant} betrayal — cadence {cadence_name}")
    w("#" * 78)
    # establish the partnership
    for beat in spec["setup"]:
        await eng.respond(RespondRequest(player_input=beat, situation=Situation(clock=-1.0)), debug=True)
    # the betrayal at day 0
    if variant == "PLAYER":
        w(f"[day 0]  [PLAYER, betrayal] {spec['betray_player']}")
        await eng.remember(spec["betray_player"], player_role="caused", importance=0.95, t=0.0)
    else:
        w(f"[day 0]  [EXTERNAL, 3rd-party betrayal] {spec['betray_external']}")
        await eng.remember(spec["betray_external"], importance=0.95, t=0.0)
    w(f"         state: {rel_line(eng.relationship.get())}")

    events = spec["events"]
    ei, quiet = 0, 0
    goal_snaps = [("start", list(eng.character.goals))]
    for tick in range(cadence_days, SPAN + 1, cadence_days):
        window = []
        while ei < len(events) and events[ei][0] <= tick:
            d, typ, txt = events[ei]
            await eng.remember(txt, importance=0.65, t=float(d))
            window.append((d, typ, txt))
            ei += 1
        dec = await eng.deliberate(Situation(clock=float(tick)), mode="free")
        changed = bool(dec.get("changed"))
        if not window and not changed:
            quiet += 1
            continue
        if quiet:
            w(f"\n   …({quiet} quiet tick(s) — nothing new, no change)")
            quiet = 0
        w(f"\n[day {tick}]  (cadence: {cadence_name})")
        if window:
            w("   events since last deliberation:")
            for d, typ, txt in window:
                w(f"      [{typ}] (day {d}) {txt}")
        else:
            w("   events since last deliberation: (none)")
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
    w(f"\n=> changed at {len(goal_snaps)-1} of the deliberations; final goals: {final}")
    jr = await judge(spec["name"], "\n".join(f"  {t}: {g}" for t, g in goal_snaps))
    w(f"=> judge: {jr}")
    wipe(slug)
    return len(goal_snaps) - 1, jr


async def main():
    REPORT.write_text("# Cadence + event-attribution experiment (1-year dense window, free mode)\n", encoding="utf-8")
    print(f"writing -> {REPORT}\n")
    summary = []
    for slug, spec in CHARS.items():
        for variant in ("PLAYER", "EXTERNAL"):
            for cname, cdays in CADENCES.items():
                changes, jr = await run_life(slug, spec, variant, cname, cdays)
                summary.append((spec["name"], variant, cname, changes, jr))
    w("\n" + "=" * 78 + "\nSUMMARY (changes / coherence judge)")
    for name, variant, cname, changes, jr in summary:
        w(f"  {name:7} {variant:9} {cname:15} changed={changes:2}  judge={jr}")
    w("\n=== done ===")


if __name__ == "__main__":
    asyncio.run(main())
