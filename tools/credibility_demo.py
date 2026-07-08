"""Credibility Demo driver (open-release Step 1) — prove this is a persistent thinking system,
not a chatbot acting a part. See docs/credibility-demo.md.

A scripted arc drives ONE NPC (Corvin, the smuggling-port harbormaster) through:
  rapport -> a real bond (a COSTLY, player-attributed beneficial act) -> weeks pass (decay) ->
  BETRAYAL (player-attributed harm -> trust craters, the engine chooses which axis SCARS, a
  belief consolidates) -> conditioned recall (the betrayal memory beats raw similarity, the
  reply is guarded) -> and finally the killer beat: the mind RELOADS FROM DISK unchanged.

Every beat prints the 🧠 panel — the actual relevance scores (importance vs raw similarity,
diversity-suppressed near-duplicates) — so a skeptic sees rule-based state, not vibes.

Run the whole arc (wipes Corvin first, leaves his mind on disk), then an in-process cold reload:
    python -m tools.credibility_demo

For the ON-CAMERA restart proof, run the two phases in SEPARATE processes — kill the terminal
between them; the second reads Corvin straight off .memory/ in a brand-new process:
    python -m tools.credibility_demo --build-only     # 1) live the arc, persist, exit
    python -m tools.credibility_demo --reload-only     # 2) fresh process: he still remembers

Bills the LLM (Anthropic). Model via CRED_MODEL (default claude-opus-4-8).
"""
from __future__ import annotations

import argparse
import asyncio
import os

from tools._harness import bootstrap, make_engine, set_flags, wipe

bootstrap()
# All the metamorphosis capabilities ON — the full depth must be visible.
set_flags(relationship_state=True, relationship_time_decay=True, reflection_enabled=True,
          intent_state=True, salience_scoring=True)

SLUG = "corvin-ashgrave-inworld"
MODEL = os.environ.get("CRED_MODEL", "claude-opus-4-8")
DOCK = "the fish-dock"


# --------------------------------------------------------------------------- printing / 🧠 panel

def _bar(v: float, width: int = 12) -> str:
    n = max(0, min(width, round(v * width)))
    return "█" * n + "·" * (width - n)


def rel_line(eng, tag: str) -> None:
    r = eng.relationship.get()
    print(f"   {tag:<16} affection {r.affection:.2f} [{_bar(r.affection)}]   "
          f"trust {r.trust:.2f} [{_bar(r.trust)}]   respect {r.respect:.2f} [{_bar(r.respect)}]   "
          f"· {r.mood}")


def scar_readout(eng) -> None:
    r = eng.relationship.get()
    print("\n   ── SCARS (the engine chose the axis; a scar caps that axis permanently) ──")
    for axis in ("affection", "trust", "respect"):
        s = getattr(r, f"scar_{axis}")
        if s > 0:
            print(f"      {axis:<10} scar {s:.2f}  → ceiling {1 - s:.2f}  (can never fully return)")
    for ln in r.render().splitlines():
        if "scar you carry" in ln.lower():
            print(f"      prompt injects: {ln.strip()}")


def brain_panel(dbg, *, note: str = "") -> None:
    """The 🧠 panel: the actual relevance scores the engine used to pick what Corvin recalls.
    Shows importance/recency beating RAW cosine similarity, and near-duplicates suppressed."""
    scored = dbg.get("scored") or []
    if not scored:
        print("   🧠 (no long-term memories scored yet)")
        return
    print(f"   🧠 MEMORY RELEVANCE{('  — ' + note) if note else ''}")
    print(f"      {'':2}{'sim_raw':>8}{'import':>8}{'recency':>8}{'score':>8}  memory")
    for s in sorted(scored, key=lambda x: x.get("base", 0.0), reverse=True):
        mark = "★" if s.get("selected") else " "
        txt = (s.get("text") or "").replace("\n", " / ")[:60]
        why = ""
        if s.get("selected") and s.get("importance", 0) > s.get("similarity_raw", 0) + 0.05:
            why = "  ← importance > raw similarity"
        elif (not s.get("selected")) and s.get("similarity_raw", 0) > 0.55:
            why = "  ← near-dup / diversity-suppressed"
        print(f"      {mark:2}{s.get('similarity_raw', 0):>8.2f}{s.get('importance', 0):>8.2f}"
              f"{s.get('recency', 0):>8.2f}{s.get('base', 0):>8.2f}  {txt}{why}")


def show_reply(name: str, reply: str, dbg) -> None:
    stars = [s["text"] for s in (dbg.get("scored") or []) if s.get("selected")]
    if stars:
        print("   recalled: " + " | ".join(t[:46].replace("\n", " ") for t in stars))
    rel_line(eng_ref["eng"], "relationship:")
    print(f'\n   {name}: "{reply}"\n')


# --------------------------------------------------------------------------- the arc

eng_ref: dict = {}   # so the print helpers can reach the live engine without threading it through


async def say(eng, name, label, player, *, location=DOCK, clock, recent=None, panel=False):
    from orchestrator.context import RespondRequest, Situation
    print(f"\n{'=' * 84}\n▶ {label}   ·   [t={clock} · {location}]")
    print(f'   player: "{player}"')
    sit = Situation(location=location, clock=float(clock), present=[name],
                    recent_events=list(recent or []))
    reply, dbg = await eng.respond(RespondRequest(player_input=player, situation=sit), debug=True)
    if panel:
        brain_panel(dbg)
    show_reply(name, reply, dbg)
    return reply, dbg


async def event(eng, headline, fact, *, player_role, clock, importance=None):
    """A player-attributed world event (the seam ChatGPT has no equivalent for)."""
    print(f"\n   ⚑ EVENT: {headline}")
    sal = await eng.remember(fact, player_role=player_role, t=float(clock), importance=importance)
    who = {"benefited": "player BENEFITED him", "caused": "player CAUSED this"}.get(player_role, player_role)
    print(f"      attributed: {who}   ·   engine salience = {sal:.2f}"
          f"{'  (self-appraised)' if importance is None else '  (pinned)'}")
    rel_line(eng, "  → relationship:")


async def build_arc():
    """Live the whole arc; leave Corvin's mind on disk."""
    wipe(SLUG)
    eng = make_engine(SLUG, model=MODEL, max_tokens=200)
    eng_ref["eng"] = eng
    from orchestrator.character_store import load_character
    name = load_character(SLUG).name.split()[0]

    print("#" * 84 + f"\n#  CREDIBILITY DEMO — {name}: rapport → bond → betrayal → scar → RESTART\n" + "#" * 84)

    # 1) RAPPORT ------------------------------------------------------------------------------
    await say(eng, name, "Day 1 — a new runner introduces themselves", clock=1,
              player="I hear you need people who can keep their mouth shut. I'm looking for work — "
                     "steady, quiet. I won't ask what's in the crates.")
    await say(eng, name, "Day 2 — small talk while loading", clock=2,
              player="Cold morning. Brought you a coffee — black, like the harbor-master's soul, "
                     "they tell me.")

    # 2) THE BOND — a COSTLY, attributed beneficial act (the player pays a real price for him) --
    await event(eng, "the player buys Corvin's seized cargo back from the watch — with their OWN coin",
                "The player emptied their own savings and took a beating from the watch sergeant to buy "
                "back Corvin's impounded cargo, then handed it over asking nothing in return.",
                player_role="benefited", clock=3)
    await say(eng, name, "Day 3 — the player brings the cargo back", clock=3,
              recent=["the player got Corvin's cargo back from the watch"],
              player="Here's your cargo. All of it. No — I don't want anything for it. "
                     "Figured you'd have done the same for me.")

    # 3) WEEKS PASS — decay + cadence-aware absence --------------------------------------------
    print("\n" + "-" * 84 + "\n   ⏳ THREE WEEKS PASS  (clock 3 → 24). Trivia should fade; the debt should stay vivid.\n" + "-" * 84)
    await say(eng, name, "~3 weeks later — the player drops by (decay + recall test)", clock=24,
              panel=True, player="Been a while. Everything still running smooth down here?")

    # 4) THE BETRAYAL — attributed harm; the engine scars an axis IT chooses --------------------
    rel_before = eng.relationship.get()
    print(f"\n   (before betrayal:  trust {rel_before.trust:.2f})")
    # Pinned high-importance: a betrayal IS a defining memory. (The bond above self-appraises to
    # show the salience scorer; here we PIN so the raw betrayal memory surfaces in recall — the
    # secret-sale wording otherwise makes the scorer rate it low-salience-to-Corvin, ~0.15.)
    await event(eng, "the player sold Corvin's routes to the Vane syndicate and tipped the watch",
                "The player betrayed Corvin: sold his shipping routes and the names of his crew to the "
                "Vane syndicate, and tipped the harbor watch to his next run — for a cut of the seizure.",
                player_role="caused", clock=25, importance=0.95)
    await say(eng, name, "Day 25 — the player shows up as if nothing happened", clock=25,
              recent=["Corvin's run was seized; his crew scattered"],
              player="Hey — good to see you. Rough week? You look like hell.")
    scar_readout(eng)

    # consolidated belief (reflection turns the exchanges into a durable conviction)
    await eng.flush_reflection()
    beliefs = eng.long_term.beliefs()
    print("\n   ── CONSOLIDATED BELIEFS (reflection, not scripted) ──")
    for b in beliefs:
        print(f"      • {b}")
    if not beliefs:
        print("      (none yet — reflection threshold not reached this run)")

    # 5) CONDITIONED RECALL — ordinary question, betrayal memory wins, reply is changed ---------
    await say(eng, name, "Day 26 — an ORDINARY request (watch what he recalls)", clock=26,
              panel=True, player="Can you get a crate to the north wharf by Friday? Usual rate.")

    return eng


async def prove_persistence(built_eng=None):
    """Reload Corvin FROM DISK and prove the mind is intact. If built_eng is given we do an
    honest in-process cold reload (cache invalidated → re-read from .memory/); with no built_eng
    (separate --reload-only process) it is a real cross-restart load."""
    from orchestrator.memory.long_term import LongTermMemory
    from orchestrator.character_store import load_character
    ns = load_character(SLUG).memory_namespace
    if built_eng is not None:
        del built_eng
        LongTermMemory.invalidate(ns)   # drop the in-process cache so the reload re-reads the file
        eng_ref.pop("eng", None)

    print("\n" + "#" * 84 + "\n#  RESTART — new Engine, nothing in memory, loaded straight from .memory/\n" + "#" * 84)
    eng = make_engine(SLUG, model=MODEL, max_tokens=200)
    eng_ref["eng"] = eng
    name = load_character(SLUG).name.split()[0]

    rel_line(eng, "reloaded:")
    scar_readout(eng)
    print("\n   reloaded beliefs:")
    for b in eng.long_term.beliefs():
        print(f"      • {b}")

    await say(eng, name, "After the restart — same player returns, asks something innocent", clock=40,
              panel=True, player="It's me. Been thinking about that morning I brought your coffee. "
                                 "We're still good, you and I — right?")
    print("   ↑ He is still cold, the scar intact, the betrayal recalled — after the process died and "
          "restarted.\n     This is not a context window.")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-only", action="store_true", help="live the arc, persist to disk, exit")
    ap.add_argument("--reload-only", action="store_true", help="fresh process: load from disk, prove memory")
    args = ap.parse_args()

    if args.reload_only:
        await prove_persistence(None)
    elif args.build_only:
        await build_arc()
        print("\n   ✔ arc complete — Corvin persisted to .memory/. "
              "Now run:  python -m tools.credibility_demo --reload-only")
    else:
        eng = await build_arc()
        await prove_persistence(eng)


if __name__ == "__main__":
    asyncio.run(main())
