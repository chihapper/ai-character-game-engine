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
# Corvin's voice. Prefix picks the Hume provider: "HUME_AI:<uuid|name>" = Voice Library,
# "CUSTOM_VOICE:<uuid>" = a saved custom voice; a bare name → HUME_AI. Swap via CORVIN_HUME_VOICE.
# The owner's two preferred voices are Voice Library voices addressed BY ID (they resolve only as
# HUME_AI, not CUSTOM_VOICE). Default = the first; A/B both with `--sample`.
CORVIN_VOICE = os.environ.get("CORVIN_HUME_VOICE", "HUME_AI:2ae087da-ab61-4455-b095-4e926f0e75a2")
SAMPLE_VOICES = os.environ.get("CRED_SAMPLE_VOICES",
                               "HUME_AI:f49f18fc-4fe9-4e78-9338-0960d44b93f9,"
                               "HUME_AI:2ae087da-ab61-4455-b095-4e926f0e75a2").split(",")
# two short lines that show Corvin's range (warm-but-wary, then cold-betrayed)
SAMPLE_LINES = [
    ("warm", "Nobody hands something back and asks for nothing. So don't tell me you want "
             "nothing — that's not how this works, and we both know it."),
    ("cold", "You walk in here, my run just seized, my crew gone, and you're already talking "
             "about the next job. *flat* How'd you know I'd have anything to move by Friday."),
]

# Replay capture — every beat's REAL data, for the record-then-replay overlay (docs/credibility-
# demo/overlay.html). Written as replay.json (canonical) + replay.js (window assignment so the
# overlay loads over file:// without a server). Basename via CRED_EMIT ("" disables).
EMIT = os.environ.get("CRED_EMIT", "docs/credibility-demo/replay")
REPLAY: dict = {"meta": {"character": "Corvin", "slug": SLUG, "model": MODEL}, "beats": []}


def rel_snap(eng) -> dict:
    r = eng.relationship.get()
    return {"affection": round(r.affection, 3), "trust": round(r.trust, 3),
            "respect": round(r.respect, 3), "mood": r.mood,
            "scar_affection": round(r.scar_affection, 3), "scar_trust": round(r.scar_trust, 3),
            "scar_respect": round(r.scar_respect, 3)}


def scored_rows(dbg) -> list:
    out = []
    for s in (dbg.get("scored") or []):
        out.append({"text": (s.get("text") or "").replace("\n", " ")[:110],
                    "similarity_raw": round(s.get("similarity_raw", 0.0), 3),
                    "importance": round(s.get("importance", 0.0), 3),
                    "recency": round(s.get("recency", 0.0), 3),
                    "base": round(s.get("base", 0.0), 3),
                    "selected": bool(s.get("selected"))})
    return out


def emit(**rec) -> None:
    REPLAY["beats"].append(rec)


def write_replay() -> None:
    if not EMIT:
        return
    import json
    import pathlib
    base = pathlib.Path(EMIT)
    base.parent.mkdir(parents=True, exist_ok=True)
    base.with_suffix(".json").write_text(json.dumps(REPLAY, indent=2, ensure_ascii=False),
                                         encoding="utf-8")
    base.with_suffix(".js").write_text("window.CRED_REPLAY = " + json.dumps(REPLAY, ensure_ascii=False)
                                       + ";", encoding="utf-8")
    print(f"\n   ▣ replay written: {base.with_suffix('.json')}  (+ .js for the overlay)")


# --------------------------------------------------------------------------- printing / 🧠 panel

def _bar(v: float, width: int = 12) -> str:
    n = max(0, min(width, round(v * width)))
    return "█" * n + "·" * (width - n)


def rel_line(eng, tag: str) -> None:
    r = eng.relationship.get()
    print(f"   {tag:<16} affection {r.affection:.2f} [{_bar(r.affection)}]   "
          f"trust {r.trust:.2f} [{_bar(r.trust)}]   respect {r.respect:.2f} [{_bar(r.respect)}]   "
          f"· {r.mood}")


def scar_lines(eng) -> list:
    return [ln.strip().lstrip("- ").strip() for ln in eng.relationship.get().render().splitlines()
            if "scar you carry" in ln.lower()]


def scar_readout(eng) -> None:
    r = eng.relationship.get()
    print("\n   ── SCARS (the engine chose the axis; a scar caps that axis permanently) ──")
    for axis in ("affection", "trust", "respect"):
        s = getattr(r, f"scar_{axis}")
        if s > 0:
            print(f"      {axis:<10} scar {s:.2f}  → ceiling {1 - s:.2f}  (can never fully return)")
    for ln in scar_lines(eng):
        print(f"      prompt injects: {ln}")


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


async def say(eng, name, label, player, *, location=DOCK, clock, recent=None, panel=False,
              phase="build"):
    from orchestrator.context import RespondRequest, Situation
    print(f"\n{'=' * 84}\n▶ {label}   ·   [t={clock} · {location}]")
    print(f'   player: "{player}"')
    sit = Situation(location=location, clock=float(clock), present=[name],
                    recent_events=list(recent or []))
    reply, dbg = await eng.respond(RespondRequest(player_input=player, situation=sit), debug=True)
    if panel:
        brain_panel(dbg)
    show_reply(name, reply, dbg)
    emit(kind="say", phase=phase, label=label, clock=clock, location=location, player=player,
         reply=reply, panel=panel, relationship=rel_snap(eng), scored=scored_rows(dbg),
         beliefs=list(eng.long_term.beliefs()))
    return reply, dbg


async def event(eng, headline, fact, *, player_role, clock, importance=None):
    """A player-attributed world event (the seam ChatGPT has no equivalent for)."""
    print(f"\n   ⚑ EVENT: {headline}")
    sal = await eng.remember(fact, player_role=player_role, t=float(clock), importance=importance)
    who = {"benefited": "player BENEFITED him", "caused": "player CAUSED this"}.get(player_role, player_role)
    print(f"      attributed: {who}   ·   engine salience = {sal:.2f}"
          f"{'  (self-appraised)' if importance is None else '  (pinned)'}")
    rel_line(eng, "  → relationship:")
    emit(kind="event", phase="build", headline=headline, fact=fact, player_role=player_role,
         clock=clock, salience=round(sal or 0.0, 3), pinned=importance is not None,
         relationship=rel_snap(eng))


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
    emit(kind="advance", phase="build", note="THREE WEEKS PASS", clock_from=3, clock_to=24,
         detail="Trivia fades from recall; the debt stays vivid.")
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
    emit(kind="scar", phase="build", relationship=rel_snap(eng), scar_lines=scar_lines(eng))

    # consolidated belief (reflection turns the exchanges into a durable conviction)
    await eng.flush_reflection()
    beliefs = eng.long_term.beliefs()
    print("\n   ── CONSOLIDATED BELIEFS (reflection, not scripted) ──")
    for b in beliefs:
        print(f"      • {b}")
    if not beliefs:
        print("      (none yet — reflection threshold not reached this run)")
    emit(kind="beliefs", phase="build", beliefs=list(beliefs))

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
    emit(kind="restart", phase="restart", relationship=rel_snap(eng), scar_lines=scar_lines(eng),
         beliefs=list(eng.long_term.beliefs()))

    await say(eng, name, "After the restart — same player returns, asks something innocent", clock=40,
              phase="restart", panel=True,
              player="It's me. Been thinking about that morning I brought your coffee. "
                     "We're still good, you and I — right?")
    print("   ↑ He is still cold, the scar intact, the betrayal recalled — after the process died and "
          "restarted.\n     This is not a context window.")


async def sample_voices():
    """A/B two Corvin lines (warm + cold) across several voice ids so the owner can pick by ear.
    Writes docs/credibility-demo/audio/samples/<n>_<shortid>_<tone>.wav. Cheap (TTS only)."""
    import pathlib
    import wave
    from orchestrator.config import AUDIO_SAMPLE_RATE
    from orchestrator.main import make_tts
    out = pathlib.Path(EMIT).parent / "audio" / "samples"
    out.mkdir(parents=True, exist_ok=True)
    print(f"   ▣ sampling {len(SAMPLE_VOICES)} voice(s) × {len(SAMPLE_LINES)} lines")
    for n, vid in enumerate(SAMPLE_VOICES, 1):
        vid = vid.strip()
        short = vid.split(":")[-1][:8]   # strip any provider prefix; keep the ref's first 8 chars
        tts = make_tts("hume")   # fresh instance per voice → no cross-voice continuity bleed
        for tone, line in SAMPLE_LINES:
            pcm = b""
            async for chunk in tts.stream_speech(line, vid):
                pcm += chunk
            wp = out / f"{n}_{short}_{tone}.wav"
            with wave.open(str(wp), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(AUDIO_SAMPLE_RATE)
                w.writeframes(pcm)
            print(f"      voice {n} ({short}…) {tone:>4}  {len(pcm)//2/AUDIO_SAMPLE_RATE:4.1f}s  ->  {wp.relative_to(pathlib.Path(EMIT).parent)}")
    print("   ✔ samples written to audio/samples/ — listen, then set CORVIN_HUME_VOICE to the winner.")


async def bake_voice():
    """Pre-bake Hume audio for every spoken line in the EXISTING replay.json, decoupled from the
    (billed) LLM arc — so re-voicing never re-runs the arc. Writes audio/beat_<i>.wav and stamps an
    "audio" path onto each say beat, then rewrites replay.json + replay.js. One HumeTTS instance
    across the arc → prosody continues turn-to-turn (Corvin's through-line), reset at the betrayal
    so the cratered mood doesn't inherit the warmth. Needs HUME_API_KEY. Run after a build."""
    import json
    import pathlib
    import wave
    from orchestrator.config import AUDIO_SAMPLE_RATE
    from orchestrator.main import make_tts
    base = pathlib.Path(EMIT)
    data = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
    audio_dir = base.parent / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    tts = make_tts("hume")
    data["meta"]["voice"] = CORVIN_VOICE
    print(f"   ▣ baking Corvin's voice: '{CORVIN_VOICE}' (Hume Octave)")
    for i, b in enumerate(data["beats"]):
        if b.get("kind") != "say" or not b.get("reply"):
            continue
        # reset the prosodic carry once, at the betrayal reply, so the cold turn doesn't inherit warmth
        if b.get("clock") == 25 and b.get("phase") == "build":
            tts.reset_continuation()
        pcm = b""
        async for chunk in tts.stream_speech(b["reply"], CORVIN_VOICE):
            pcm += chunk
        wav_path = audio_dir / f"beat_{i}.wav"
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(AUDIO_SAMPLE_RATE)
            w.writeframes(pcm)
        b["audio"] = f"audio/beat_{i}.wav"
        print(f"      beat {i:>2}  {len(pcm)//2/AUDIO_SAMPLE_RATE:5.1f}s  ->  {b['audio']}")
    base.with_suffix(".json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    base.with_suffix(".js").write_text("window.CRED_REPLAY = " + json.dumps(data, ensure_ascii=False) + ";",
                                       encoding="utf-8")
    print("   ✔ voice baked + replay updated — reload the overlay to hear it.")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-only", action="store_true", help="live the arc, persist to disk, exit")
    ap.add_argument("--reload-only", action="store_true", help="fresh process: load from disk, prove memory")
    ap.add_argument("--voice", action="store_true", help="bake Hume audio for the existing replay.json (no LLM)")
    ap.add_argument("--sample", action="store_true", help="A/B the SAMPLE_VOICES on two lines (no LLM)")
    args = ap.parse_args()

    if args.sample:
        await sample_voices()
    elif args.voice:
        await bake_voice()
    elif args.reload_only:
        await prove_persistence(None)
    elif args.build_only:
        await build_arc()
        print("\n   ✔ arc complete — Corvin persisted to .memory/. "
              "Now run:  python -m tools.credibility_demo --reload-only")
    else:
        eng = await build_arc()
        await prove_persistence(eng)
        write_replay()   # canonical replay for the overlay (build + restart beats)


if __name__ == "__main__":
    asyncio.run(main())
