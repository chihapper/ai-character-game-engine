# Architecture & seams

> Design doc for the **game-director direction**. Status: design (target state),
> not yet fully built. Tracks issues
> [#1 — memory & retrieval](https://github.com/chihapper/ai-character-game-engine/issues/1)
> and [#2 — generalize the engine](https://github.com/chihapper/ai-character-game-engine/issues/2).
> **DONE** marks a seam the current code already implements; **TARGET** marks a proposed
> change. **RETIRING** marks inherited voice-engine machinery the full-loop direction
> replaces — present in `main` today, but not the architecture going forward.

> 🧭 **North star.** The long-term goal of this project is the **engine/game seam
> (Track E, §2–4)** — the game-director that owns character state, memory, the world/time
> seam, and game mechanics. The Inworld full-loop **voice runtime (Track V)** is
> *enabling infrastructure*, not the destination: it gives the character a voice and
> working tools so a game can drive it. Don't let voice-runtime polish (latency,
> barge-in, audio quality) crowd out Track E. When the two interact, favor the choice
> that keeps the Track E seam clean.

## What this doc is for

The engine is a **real-time character runtime + game director**: given who a character
is and what's happening in the world, it drives a voice agent to make that character
respond, and it owns the character's memory and state across sessions. A separate
**game layer** owns the world, the clock, and the rules.

The committed technical direction is to drive **Inworld's full-loop realtime voice
agent** — one Inworld session owns STT → LLM → TTS as a single conversational loop,
which is the only way to get cross-turn voice continuity (validated by the spike;
see §1.3). This **replaces** the inherited provider-agnostic pipeline (separate
STT/LLM/TTS adapters) that this repo was seeded with. That inherited pipeline still
runs in `main` today, but it is being retired, not extended.

This doc defines the **seams**: the voice-runtime seam (engine ↔ Inworld agent) and,
the larger body of work, the **engine/game seam** (engine ↔ the game that drives it).

Two families of seam:

1. **The voice-runtime seam** (engine ↔ Inworld Realtime agent) — §1. The engine drives
   one Inworld session that owns the STT→LLM→TTS loop. **Replaces** the inherited
   modular adapter pipeline.
2. **The engine/game seam** (engine ↔ the game) — §2–4. Character depth, context-in,
   memory-write, world/time. **The bulk of the design work**, and largely independent
   of which voice runtime delivers the audio.

---

## 1. The voice-runtime seam — driving the Inworld full-loop agent (TARGET)

### 1.1 The shape

The voice runtime is **one Inworld Realtime API session**, driven over a WebSocket
(OpenAI Realtime protocol). That single session is the whole loop — **STT → LLM → TTS**
— so prosody and timbre carry **across turns** (cross-turn voice continuity), which a
per-utterance TTS fundamentally cannot give. The engine does not orchestrate STT, the
LLM, and TTS as separate steps; it **steers one agent**.

```
                ┌──────────────────────────────────────────────┐
   engine ────► │  Inworld Realtime session                    │ ────► 🔊 spoken reply
   provides:    │    STT → LLM(=Claude) → Realtime TTS-2        │       (voice continuity
   - instructions    └──────────────────────────────────────────────┘        across turns)
   - tools
   - per-request context        ▲                    │
   - tool-call results          └──── function call ─┘  (game mechanics)
```

The engine supplies four things to the session and owns everything around it:

- **Instructions = the character.** The engine compiles a character's structured
  profile into a system prompt
  ([`Character.build_prompt()`](../orchestrator/character_store.py)) and sets it as the
  session's agent instructions — the same character definition drives the voice agent.
- **The LLM is routed to Claude.** The session's `model` field routes to
  `anthropic/claude-sonnet-4-6` (the session default is otherwise a Gemini model). The
  agent reasons as Claude; Inworld owns the speech ends.
- **Tools = game mechanics.** Function-calling lets the game run logic *through the
  conversation* — a dice roll, a state change, a quest update — instead of the model
  narrating outcomes it shouldn't decide. The engine handles the tool call and returns
  the result into the session.
- **Per-request context** — the world/time situation (see §3), injected per response.

### 1.2 What the engine keeps vs. what moves into the session

| Concern | Owner under the full loop |
| --- | --- |
| STT, turn-taking, LLM hosting, TTS, voice continuity | **Inworld session** |
| Character definition → instructions (`build_prompt`) | engine |
| Tools / mechanics + tool-call handling | engine |
| Memory (short + long term) | engine |
| World/time seam + per-request situation | engine |
| Voice identity (cloned/designed voice id) | engine (set on the session) |

What the engine **gives up** from the inherited voice engine: its own STT adapters,
its own Anthropic streaming orchestration, the sentence-chunk/TTS overlap pipeline, and
the expressivity/tag layer — Inworld owns all of that inside the session.

### 1.3 Why we're confident (spike)

A text-only feasibility spike (`realtime_fullloop_spike.py`) confirmed the load-bearing
assumptions: **steering works** (the session obeys our `build_prompt()` output and stays
in character), **function-calling works** (a `roll_dice` tool fired with correct args),
and **the LLM is routable to Claude**. Open follow-ups: the exact Anthropic model id,
and tool-result *continuation* (returning `function_call_output` produced no follow-on
text — a call-id format detail). These are integration details, not viability risks.

### 1.4 RETIRING: the inherited modular adapter pipeline

The repo was seeded from the provider-agnostic voice engine, whose spine is the adapter
interface in [`adapters/base.py`](../orchestrator/adapters/base.py) — `STTAdapter`,
`LLMAdapter`, `TTSAdapter` — orchestrated by the streaming-overlap
[`Pipeline`](../orchestrator/pipeline.py). **This is what `main.py` still runs today**,
and it is genuinely good engineering (sub-second first audio via producer/consumer
overlap). But under the full-loop direction it is the **path being retired**, not the
architecture:

- The STT and TTS seams **collapse into the Inworld session** (Inworld owns both ends).
- The `LLMAdapter` is **superseded** by the in-session Claude routing.
- The overlap pipeline, sentence chunker, expressivity layer, and per-utterance TTS
  batching/fades exist to make a *separate* TTS sound continuous — a problem the
  full-loop session solves natively. They retire with it.

What survives the migration is **not** the pipeline but the things around it that the
engine still owns: `build_prompt()`, the memory tiers, and the game seam below. One
piece of the adapter layer also survives in spirit — **voice cloning/design** — since
the engine still mints the voice id it hands to the session.

> **Note for implementers:** treat new work against `adapters/base.py`'s STT/LLM/TTS
> interfaces as maintenance of a retiring path, not investment in the architecture. New
> capability belongs behind the Inworld-session integration and the engine/game seam.

---

## 2. The character model — universal core + the `game_data` extension seam (DONE)

A [`Character`](../orchestrator/character_store.py) is the unit a player talks to. The
engine is **game-agnostic about identity**: it compiles a fixed set of *universal,
dramatic* fields into the instructions (`build_prompt`) — identity, manner, backstory,
knowledge, plus game-agnostic mechanics (goals, secrets with reveal conditions,
boundaries, relationships, disposition). This survives the voice-runtime migration
untouched — it produces the instructions the Inworld session runs on.

Anything a *specific* game needs that the engine shouldn't understand lives in
**`game_data`** — an open, namespaced bag the engine stores and round-trips verbatim
but never interprets. This is already the cleanest engine/game seam in the codebase:

- A game registers a **renderer** for its namespace via
  [`register_game_extension(namespace, renderer)`](../orchestrator/character_extensions.py).
- At compile time, `build_prompt` calls `render_game_data` and appends each registered
  namespace's section. Unregistered namespaces stay inert (stored, not spoken). A
  renderer that throws is skipped, never fatal.

```
character.game_data = { "dnd5e": { "level": 5, "class": "rogue", ... } }
                              │
        register_game_extension("dnd5e", render_dnd5e)   ← game layer, at startup
                              │
        build_prompt() ──► appends render_dnd5e(sheet) as an instructions section
```

**Why it matters here:** this is the template for every other engine/game seam below.
The engine exposes a *registration point* and a *neutral data channel*; the game
supplies *meaning* at runtime. The context-in and memory seams should follow the same
shape rather than baking game concepts into the engine.

---

## 3. The engine/game seam — the core generalization (TARGET)

### 3.1 The problem: `run_turn(user_text)` is chat-shaped

Today the entry point is
[`Pipeline.run_turn(user_text, ...)`](../orchestrator/pipeline.py), called once per
finalized transcript / typed line. Two assumptions are baked in:

1. **The trigger is a user utterance.** But in a game the trigger is the *game's* to
   decide — a typed line in a crime game, a dialogue-node entry in a 2D RPG, a
   proximity/event hook in a 3D RPG. There may be no "user message" at all.
2. **The retrieval + prompt input is the player's last message.** But what a character
   should respond to is richer: where they are, the in-game time, who else is present,
   what just happened, quest state.

"Turn" is a conversation abstraction. The engine's real unit is: **produce this
character's response/action given an input + game-supplied context.** This is true
regardless of whether the Inworld session or the (retiring) pipeline delivers the audio
— the generalization is about *what feeds the agent*, not how audio is produced.

### 3.2 The shape: a `RespondRequest`, not a string

**TARGET.** Generalize the entry point to accept a structured request. Sketch:

```python
@dataclass
class RespondRequest:
    # What the character is reacting to. Exactly one is the "trigger," but both
    # may be present (e.g. a player line spoken at a specific place/moment).
    player_input: str | None = None        # a spoken/typed line, if any
    event: str | None = None               # a game event that triggered this
                                            # ("player entered the tavern")

    # Transient "what's true right now" — injected as a CURRENT SITUATION section,
    # NOT persisted. The game owns these facts; the engine just renders them.
    situation: Situation | None = None

    # What to retrieve long-term memory against. Defaults to player_input/event,
    # but the game may supply a richer query (location + situation + input).
    retrieval_query: str | None = None
```

```python
@dataclass
class Situation:
    location: str = ""        # "the back room of the Salt Crow"
    game_time: str = ""       # game-defined clock string; engine stores, never parses
    present: list[str] = field(default_factory=list)   # who else is here
    recent_events: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)          # open bag, game-namespaced
```

`run_turn(user_text, ...)` becomes a thin compatibility wrapper that builds a
`RespondRequest(player_input=user_text)`, so the current path keeps working while the
richer one opens up.

### 3.3 Context assembly: three sources, one instruction set

A character "understands their world" from three composable sources. Today
[`_build_system`](../orchestrator/pipeline.py) composes two of them; the third is new.
These compose into the instruction set the voice agent runs on.

| Source | Lifetime | Owner | Where it enters |
| --- | --- | --- | --- |
| **Static profile** | durable, authored | engine (character YAML) | `Character.build_prompt()` |
| **Long-term memory** | durable, accreting | engine (vector store) | retrieved per request, injected as "Memories…" |
| **Per-request situation** | transient | **game** | `Situation` → injected as "Current situation" (**TARGET**) |

```
                    ┌─────────────────────────────────────────┐
   ENGINE_DIRECTION │ how to stay in role (fixed)              │
                    ├─────────────────────────────────────────┤
   build_prompt()   │ # Who you are / How you speak / Secrets… │  static profile
                    │ + game_data renderer sections            │  (§2 seam)
                    ├─────────────────────────────────────────┤
   retrieve(query)  │ # Memories from past conversations       │  long-term (§4)
                    ├─────────────────────────────────────────┤
   request.situation│ # Current situation  ◄── NEW (TARGET)    │  game-pushed, transient
                    └─────────────────────────────────────────┘
```

The key point: **not everything the game knows needs to live in memory.** "It's raining
and the guard is watching you" is true *now* and injected per request; it should not
pollute the durable store. The `Situation` channel says "here's what's true at this
instant" without committing it to memory.

### 3.4 The memory-write API: durable world events (TARGET)

The other direction across the seam: the game persists **durable** world facts into a
character's memory, so retrieval surfaces them later.

```python
# engine API, called by the game when something memorable happens in the world
await memory.remember(
    namespace="cornelius",
    fact="The player burned the harbor bridge.",
    when="day 3",            # game-defined time tag; engine stores, never parses
    kind="world_event",      # vs. "exchange"; lets retrieval/decay treat them alike
)
```

Same embed-and-store path as a conversation exchange (§4), so retrieval surfaces
game-pushed events exactly like remembered dialogue. **Game-time is a tag the game
supplies** — the engine stores it opaquely; the game defines the calendar. Storing
`when` is also what unlocks **recency weighting** in retrieval (§4).

**Division of ownership, stated plainly:**

- The **engine owns the character's memory** — embedding, storage, retrieval, namespaces.
- The **game owns the world and the clock** — what happened, when, and what's true now,
  pushed across the seam two ways: transient `Situation` per request, durable
  `remember(...)` for events worth recalling.

---

## 4. Memory & retrieval (TARGET — issue #1)

### 4.1 How retrieval works today (DONE)

[`LongTermMemory`](../orchestrator/memory/long_term.py): each completed exchange is
embedded (local `all-MiniLM-L6-v2`, 384-dim) and stored in a per-character ChromaDB
collection (one per `memory_namespace`). On each request the input is embedded the same
way and the *k* nearest by cosine distance are injected. Semantic, not keyword.
[`ShortTermMemory`](../orchestrator/memory/short_term.py) is a separate verbatim rolling
buffer of recent turns. **Memory is engine-owned and survives the voice-runtime
migration unchanged.**

### 4.2 Known limits (to fix)

- **Pure similarity.** No recency or importance weighting — storing `when` (§3.4) is the
  prerequisite for recency.
- **Fixed `k=4`, no threshold.** Returns the 4 nearest even when all are weak; should
  support a relevance floor and a query-dependent `k`.
- **Query = last message only.** Should accept the game's richer `retrieval_query`
  (location + situation + input).

### 4.3 Store & embeddings — drop the heavy ANN index (TARGET)

The build pain was ChromaDB's native ANN index (hnswlib) on Windows. The realization:
**per-character memory is small** (hundreds–low-thousands of exchanges), so a heavy
approximate index buys nothing.

- **Embeddings:** `fastembed` (ONNX, no PyTorch — light, Windows-friendly), or keep
  `sentence-transformers`. **Avoid cloud embedding APIs** — a network hop per request
  hurts latency.
- **Store:** drop Chroma. `sqlite-vec` / LanceDB (embedded, pip-only, no native build),
  or — given the size — brute-force cosine over a NumPy array (sub-ms, zero deps).
- **Recommendation:** `fastembed` + LanceDB (or `sqlite-vec`). Local retrieval is a few
  ms; the latency budget is the voice agent, so memory stays off the critical path.

A swap *behind the existing `LongTermMemory` surface* (`add_exchange`, `retrieve`, plus
the new `remember`) — a one-module job.

---

## 5. Proposed seam surface (summary)

| Seam | Direction | Mechanism | Status |
| --- | --- | --- | --- |
| Voice runtime | engine → Inworld agent | one Realtime session; instructions + tools + context | TARGET (spiked) |
| Modular STT/LLM/TTS adapters | engine → vendors | `*Adapter` ABCs + overlap pipeline | RETIRING (in `main` today) |
| Voice cloning/design | engine → vendor | TTS-adapter clone/design methods | DONE (survives) |
| Character depth | game → engine | `register_game_extension` + `game_data` | DONE |
| Respond trigger + context-in | game → engine | `RespondRequest` / `Situation` | TARGET |
| Durable world events | game → engine | `memory.remember(ns, fact, when, kind)` | TARGET |
| Memory store/embeddings | engine internal | behind `LongTermMemory` | TARGET |

Design rule for every new seam: **the engine exposes a registration point and a neutral
data channel; the game supplies meaning at runtime.** No game concept (quests, factions,
D&D classes, clocks) is ever named in engine code.

---

## 6. Build order

Two roughly independent tracks.

**Track V — voice runtime (replace the inherited pipeline):**
1. Build the Inworld Realtime session integration: connect, set instructions from
   `build_prompt()`, route the LLM to Claude, stream audio to the browser.
2. Wire tools/function-calling end-to-end (close the tool-result continuation gap).
3. Cut `main.py`'s WebSocket loop over from `Pipeline` to the session; retire the STT/
   LLM/TTS adapters + overlap pipeline. (Keep voice cloning/design.)

**Track E — engine/game seam (this doc's focus, independent of Track V):**
1. Generalize the entry point: `RespondRequest` + `Situation`; make `run_turn` a
   wrapper; inject the "Current situation" section.
2. Memory store swap (fastembed + LanceDB/sqlite-vec); relevance threshold; query-dependent `k`.
3. Memory-write API + `when` tag; recency weighting once timestamps exist.
4. Richer retrieval query (location + situation + input).

Track E lands against whichever runtime is live, because it shapes the instructions and
memory the agent runs on — not the audio path.

---

## 7. Out of scope

- The game itself (rules engine, world simulation, rendering) — the *consumer* of these
  seams, a separate layer/repo.
- Multi-character scene orchestration (who speaks when) — a game-layer concern; the
  engine produces *one character's* response per request.
- Auth, cloud hosting, packaging.
- Net-new investment in the modular STT/LLM/TTS adapter seams — that path is retiring
  (§1.4); new capability belongs behind the Inworld session or the engine/game seam.
