# Credibility Demo — spec + build plan (Step 1 of the open-release roadmap)

Branch: `credibility-demo` (off clean `main`, the post engine/voice-uplift base).

## The goal (consolidated 2026-07-08)
Prove the engine **changes** characters — permanently and coherently, from *attributed* experience
— in a way the standard architecture **structurally cannot**. The differentiator is NOT memory
(plenty of products remember); it's that a standard memory system accumulates *facts* while its
persona stays static, where this character is *altered* by what you did. Most systems remember
*that* you betrayed them; this one is *changed* by it.

**Framing: categorical, not comparative.** Do not claim "mine remembers/changes better" — that's a
quality judgment on a setup we control, and it invites "you rigged it." Instead demonstrate
capabilities the standard architecture cannot have at all. Three:
1. **Attributed change.** Same betrayal, same stored fact — this character's trust collapses, a
   permanent scar forms, a belief consolidates; a static-persona memory system still treats you
   like a friend.
2. **Relationship-conditioned recall (centerpiece).** After the betrayal, an ambiguous question
   surfaces the memory of the lie — because the character now distrusts you (its live stance folds
   into the retrieval query) AND because the betrayal was encoded as high-salience. A cosine RAG
   ranks by textual similarity to the query alone; it's blind to salience and to feeling.
3. **Principled, inspectable relevance.** The 🧠 panel shows *why* a memory won — importance/recency
   beating raw similarity, near-duplicates suppressed, the trivial faded, the pivotal vivid.

The supporting proof (not the headline): **persistence across a restart** — the change is durable
state on disk (`.memory/<slug>.jsonl`), not a context trick.

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

### Milestone 2 — visual overlay (DONE) + voice (next)

**Visual overlay — `docs/credibility-demo/overlay.html`** (record-then-replay). The driver emits
`replay.json` + `replay.js` (via `write_replay()`); the overlay is a self-contained single-screen
cinematic replayer: dialogue on the left, animated relationship + **scar-ceiling** meters, the 🧠
memory-relevance table (highlights *importance beats similarity*, dims diversity-suppressed
near-dups), the consolidated beliefs, and a framed full-screen **RESTART** takeover. Controls:
Space play/pause · ← → step · **C** cinematic (hides chrome).

```
# 1) generate the data (the recording run — uses claude-opus-4-8 by default):
python -m tools.credibility_demo
# 2) serve + open (fetch of replay.js needs http://, not file://):
python -m http.server 8778 --directory docs/credibility-demo
#    → open http://localhost:8778/overlay.html in a real browser, fullscreen, RECORD AT 1080p.
```
Layout is tuned for **1920×1080** (fits with room to spare); 720p is tight (beliefs card clips).
`replay.json`/`replay.js` are committed so the overlay opens straight from the repo without a
billed run; regenerate them to refresh the arc.

**Voice — Hume "Grizzled New Yorker" (DONE).** `--voice` reads `replay.json` and pre-bakes each
spoken line to `audio/beat_<i>.wav` (decoupled from the LLM arc — no re-run), stamping an `audio`
path on each say beat. One `HumeTTS` instance across the arc carries Corvin's prosodic through-line
turn to turn, reset at the betrayal so the cold turn doesn't inherit the warmth. The overlay plays
the clip on each beat (mute = M / button) and, in autoplay, advances when Corvin finishes speaking.

```
python -m tools.credibility_demo --voice        # bake audio for the current replay.json
```
Voice is a Hume Voice Library name; swap via `CORVIN_HUME_VOICE` (e.g. "Pirate Captain",
"Sad Old British Man" — any name from `GET /v0/tts/voices?provider=HUME_AI`). The `audio/` dir is
gitignored (large, regenerable); rerun `--voice` after regenerating the arc.

### The live, unscripted segment (`--live`) — the anti-"cooked books" beat
After the scripted arc, the scarred mind sits in `.memory/`. `--live` opens an interactive,
VOICED console session against that same mind, through the SAME Engine + capability flags the arc
used (deliberately NOT the legacy web pipeline, which doesn't inject relationship state). Ad-lib
novel questions on camera — Corvin answers scarred, in voice 2, and nobody wrote his answers.
The mind is auto-snapshotted first; reset a take with `--restore pre-live`.

```
python -m tools.credibility_demo --live           # voiced (winsound); --mute for text-only
python -m tools.credibility_demo --restore pre-live   # reset between takes
python -m tools.credibility_demo --snapshot <tag>      # manual save points
```
Recommended video structure: scripted replay (~2 min) → live ad-lib (~30–45 s) → "clone it,
run it, audit it" (`tools/credibility_audit.py`).

### Milestone 3 — the side-by-side: a transparent RAG baseline (DONE)
**Baseline = an open, faithful ~1-file RAG** (`tools/rag_baseline.py`) — the standard character-
memory pattern: embed every exchange, retrieve **top-k by cosine similarity**, keep a rolling LLM
summary, on the **same base LLM, same static persona, and same embedder** as the engine. No
importance/salience, no relationship state, no relationship-conditioned recall, no principled
forgetting. It's competent, not crippled — the honest opponent. (Superseded the earlier
raw-Opus-empty-context baseline: that only proved "it forgot on restart," a comparative/weak claim.
The RAG *remembers the betrayal too* — which sets up the far stronger categorical claim: it
remembers and still can't change or recall-by-feeling.)

`--baseline` replays the SAME arc (events stored, exchanges accumulated) through the RAG and stamps
`beat.baseline` (its reply) + `beat.baseline_retrieval` (what cosine surfaced) onto the money-shot
and centerpiece beats. The overlay renders engine-vs-RAG there.

```
python -m tools.credibility_demo             # 1) arc on opus, arena_query ON (both sides same model)
python -m tools.credibility_demo --baseline  # 2) run the RAG baseline over the same arc
python -m tools.credibility_demo --voice      # 3) bake voice 2 (engine replies)
```

**Due-diligence (2026-07-08, source-verified):** the most sophisticated comparable system we could
find with real relationship state is a **community mod for one specific game (Skyrim) — not an
engine-agnostic runtime**. We reviewed it at source level: its memory retrieval is affect-blind
cosine+recency+participants with NO importance term; its relationship layer is a separate async
LLM delta-judge on ONE clamped scalar (±100) with a one-way type lock and a sticky worst-deed
note — no decay, no per-axis scar, and none of it ever touches retrieval. Our second baseline
(`TrackerRagCharacter`) reproduces that pattern faithfully. **The engine-agnostic systems that do
ship are plain RAG**, with RAG's inherent shortcomings (affect-blind retrieval, no salience, no
durable change); a landscape survey (Character.AI, Inworld, Convai, NVIDIA ACE, Replika, Kindroid,
Nomi, SillyTavern [source], AI Dungeon) found NO shipping system documenting
relationship-conditioned recall.

**The three headline claims (all structural / held across baseline versions):**
1. **Relationship-conditioned recall** — no shipping system folds the character's live feeling
   into retrieval; ours does (arena_query), on top of first-class salience.
2. **The bounded scar — one scalar can't hold a wound.** Even the sophisticated tracker pattern
   keeps ONE affinity number: a deep bond arithmetically cushions the betrayal, so after selling
   out his crew the tracker can still read **Warm (+18) toward its own betrayer** — a positive
   relationship with the man who sold his crew, which is itself the indictment (and how wrong it
   reads depends entirely on the character). After costly amends the number simply climbs back
   (+15 Warm): *the note remembers; the number forgives.* Ours: the wound is per-axis, bounded,
   permanent — affection recovers (0.26→0.40) while trust stays capped at the scar ceiling
   (0.15). *The scar IS the ceiling.* Shown as a trust-trajectory graph at the recovery beat.
3. **Principled & inspectable** — the 🧠 panel shows the machinery live (importance vs raw
   similarity, near-dup suppression, the scar's geometry) vs an opaque LLM-judged delta blob.

**Verified (opus vs opus, same persona/embedder):**
- **Money shot** — "after everything, are we still square?" → Engine: *"You've got the gall to ask
  me that… Vane… we're not square."* (trust 0.08, scarred). RAG: *"Aye. We're square, friend.
  You're the only man I don't count my fingers after."* Both have the betrayal in memory; only one
  is changed by it.
- **Centerpiece** — an operational ask ("store a crate till Thursday, got a berth?") textually far
  from the betrayal. Engine: *"…not one word about the run that went down in flames… did you sell
  my routes?"* — so changed it can't even do business. RAG: *"Aye, back slip past the salt sheds,
  nobody logs what sits there but me"* — cheerfully offers to hide the cargo. The panel shows the
  engine ranking bond/betrayal/aftermath by **importance 0.92–0.97** (+ distrust folded into the
  query via `arena_query`); the RAG's cosine top-k is all operational chatter, zero betrayal.
- **Restart** (supporting) — engine reloads from `.memory/`, scar intact, still changed.
