# Credibility Demo — spec + build plan (Step 1 of the open-release roadmap)

Branch: `credibility-demo` (off clean `main`, the post engine/voice-uplift base).

## The goal
Prove, undeniably and on camera, that this is a **persistent thinking system**, not a
chatbot acting a part — by staging the three things ChatGPT fundamentally *cannot* do:
1. **Persistence across a restart** (the mind lives on disk, not in a context window).
2. **Selective, decaying, inspectable memory** (the 🧠 panel shows *why* a memory won —
   importance beating similarity, a near-duplicate suppressed, the trivial faded while the
   significant stayed vivid).
3. **Durable state that conditions behavior** (trust that dropped and won't come back fast;
   an AI-chosen permanent scar; recall that tilts guarded).

The demo's whole job is to defeat "it's just ChatGPT told to act that way." So we stage that
exact objection — and win.

## What we are NOT building
No dungeon, no sprites, no models, no combat, no level design. Just the **sandbox + the 🧠
debug panel + the Hume voice + a scripted sequence of events + a server restart**.

## The scenario — Corvin: trust, then betrayal, then a restart
A scripted arc driven through the engine's game API, with the clock advancing so consequences
accrue over *time*:

1. **Establish rapport.** A few positive/neutral events and exchanges → Corvin warms
   (panel: affection/trust ▲).
2. **Build a real bond.** One important beneficial, *attributed* event — the player does
   something costly for him (`remember(..., player_role="benefited", importance=high)`);
   trust climbs; perhaps a commitment forms (`commit`).
3. **Advance the clock "weeks."** Show cadence-aware absence and decay: trivial exchanges have
   faded from recall, the significant moment is still vivid.
4. **The betrayal.** A significant attributed event against him → trust collapses (lost fast),
   a **permanent scar forms on an axis the engine chooses**, a belief consolidates
   ("I can't rely on them").
5. **Show conditioned recall.** Ask him something ordinary → the panel shows the betrayal
   memory surfacing (importance/relationship beating raw similarity), and his **voiced** reply
   is guarded and changed.

## The killer beat — the restart
**Kill the server. Restart it. Return as the same player.** Corvin is still cold, the scar
intact, the memory persistent — because the mind persisted to disk. Say it on camera:
*"This is not a context window. I turned it off and back on. He still remembers, and he's still
hurt."*

## The side-by-side — staging the ChatGPT objection
Run the same arc against **raw ChatGPT** (a long chat instructed to be Corvin). After ~100 turns
and a "restart" (fresh chat / cleared context), ChatGPT has forgotten or gone inconsistent; the
engine remembers, scar intact, reasoning on screen. Put them side by side. **The objection is
the demo.**

## What to capture
Screen-record the sandbox through the arc: the conversation, the 🧠 panel (relationship axes
moving, the scar forming, memory scoring/selection live), the Hume-voiced replies, the clock
advance, the restart, and the ChatGPT comparison. Target a tight **2–3 minute edited cut** (plus
a longer raw version for the repo).

## Build
- A **scenario-driver script** that fires the ordered events through the game API —
  `remember` / `commit` / `deliberate` / `respond`, advancing the clock — with debug on so the
  panel exposes the machinery.
- A **reproducible scripted arc** (a small runner + an events file) so it can be re-recorded
  cleanly and replayed from the repo.
- All capabilities ON (they already default on).
- Then record the sandbox + panel + voice, do the restart live, and capture the ChatGPT run
  separately.

## Definition of done
A 2–3 minute video where a skeptic watches Corvin warm, bond, be betrayed, scar, and stay
changed **through a server restart** — with the panel proving it's rule-based state, not vibes —
next to a ChatGPT run that forgets. If someone says "that's just ChatGPT" after watching, the
demo failed; if they say "wait, it *remembered* after a restart," it worked.

---

## Build plan against the actual engine

### Milestone 1 — headless scripted arc (DONE)
`tools/credibility_demo.py` drives the whole arc through the real engine and prints the 🧠
panel + a disk-reload persistence proof. No game art, no voice yet.

```
python -m tools.credibility_demo                 # full arc + in-process cold reload
python -m tools.credibility_demo --build-only     # live the arc, persist, exit
python -m tools.credibility_demo --reload-only     # NEW process: prove he still remembers
```
Model via `CRED_MODEL` (default `claude-opus-4-8`; validated on `claude-sonnet-4-6`).

**What it exercises (all engine, front-end-agnostic):**
- Corvin = `orchestrator/characters/corvin-ashgrave-inworld.yaml`; caps all ON via
  `tools._harness` (`relationship_state`, `relationship_time_decay`, `reflection_enabled`,
  `intent_state`, `salience_scoring`).
- **Attributed events** — `eng.remember(fact, player_role="benefited"|"caused", t=clock, importance=?)`.
  The bond is left to **self-appraise** (salience ~0.97) to show the scorer; the betrayal is
  **pinned** high (0.95) so the raw betrayal memory surfaces in recall (the "secret sale" wording
  otherwise self-scores ~0.15).
- **Clock/decay** — the driver owns the clock; jumping `clock 3 → 24` fires `_age_relationship`
  decay + cadence-aware absence on the next call.
- **Scar** — read off `eng.relationship.get().scar_{affection,trust,respect}` + `.render()`; the
  engine chose the axes (trust deepest).
- **Belief** — `eng.flush_reflection()` then `eng.long_term.beliefs()`.
- **🧠 panel** — `reply, dbg = await eng.respond(req, debug=True)`; `dbg["scored"]` carries per-
  memory `similarity_raw / importance / recency / base / selected`, printed to show importance
  beating raw similarity and diversity-suppressed near-duplicates.
- **Restart proof** — tear down the engine, `LongTermMemory.invalidate(ns)`, construct a fresh
  `Engine` → relationship, scars, and beliefs reload verbatim from `.memory/<slug>.*`. Split
  across two processes (`--build-only` then `--reload-only`) for the on-camera restart.

**Validated result:** trust 0.50→0.74 (bond) → 0.10 (betrayal); engine scarred trust 0.90 /
affection 0.70 / respect 0.60; three beliefs consolidated; the betrayal memory surfaces on
importance in conditioned recall; every value identical after the disk reload.

### Milestone 2 — voice + visual (NEXT)
- **Hume voice** on Corvin's replies: `make_tts("hume").stream_speech(reply, "<hume-voice-id>")`.
  Corvin's sheet is Inworld-configured, so supply a Hume voice id (or add a `hume_voice_id` to the
  sheet for the demo).
- **Visual 🧠 panel** for recording: either drive the existing web sandbox (`MEMORY_DEBUG=true`
  emits the `memories` WS payload consumed by `web/app.js`) or render the `dbg["scored"]` table as
  an on-screen overlay. Decide based on what films cleanest.

### Milestone 3 — the ChatGPT side-by-side
Run the same arc as a long raw-ChatGPT chat (instructed to be Corvin), then a "restart" (fresh
chat); capture it forgetting/going inconsistent. Edit to a 2–3 min cut next to our run.
