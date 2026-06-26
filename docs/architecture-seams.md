# Architecture & seams

> Design doc for the **game-director direction**. Status: design (target state),
> not yet built. Tracks issues
> [#1 — memory & retrieval](https://github.com/chihapper/ai-character-game-engine/issues/1)
> and [#2 — generalize the engine](https://github.com/chihapper/ai-character-game-engine/issues/2).
> Where the current code already implements a seam, it's marked **DONE**; where this
> doc proposes a change, it's marked **TARGET**.

## What this doc is for

The engine is a **real-time character runtime**: given who a character is and what's
happening, it produces that character's spoken response, with memory across sessions.
A separate **game layer** owns the world, the clock, and the rules. This doc defines
the **seams** between the two — the interfaces that let either side change without
touching the other — and the one generalization the game-director direction requires:
making the engine's unit of work *"produce this character's response given game
context,"* not *"reply to a user's chat message."*

There are two distinct families of seam, and keeping them separate is the whole
design:

1. **Provider seams** (engine ↔ external AI vendors) — STT, LLM, TTS. **Mature.**
2. **The engine/game seam** (engine ↔ the game that drives it) — context-in,
   memory-write, world/time, game-specific character depth. **The work ahead.**

---

## 1. Provider seams — the adapter spine (DONE)

Everything external sits behind an abstract adapter in
[`adapters/base.py`](../orchestrator/adapters/base.py). The pipeline depends only on
the interfaces, never on a concrete vendor.

| Role | Interface | Method | Implementations |
| --- | --- | --- | --- |
| Speech-to-text | `STTAdapter` | `transcribe(audio) -> str` | Whisper (local), AssemblyAI (batch + realtime stream) |
| LLM | `LLMAdapter` | `stream_reply(messages, system) -> AsyncIterator[str]` | Anthropic (streaming) |
| Text-to-speech | `TTSAdapter` | `stream_speech(text, voice_id) -> AsyncIterator[bytes]`, `clone_voice(...)` | Inworld, ElevenLabs, Cartesia, Fallback |

Two invariants make these swappable:

- **Fixed audio wire format.** Every `TTSAdapter` MUST emit PCM s16le, mono,
  `AUDIO_SAMPLE_RATE` (24 kHz) — see [`config.py:19`](../orchestrator/config.py).
  The browser playback path is identical regardless of which provider is live.
- **The pipeline never names a provider.** [`Pipeline`](../orchestrator/pipeline.py)
  takes `LLMAdapter` and `TTSAdapter` by interface. Provider selection happens once,
  at session setup, in [`main.py`](../orchestrator/main.py) (`make_tts`, `get_stt`).

Provider choice is **per-character** (a character's YAML `tts_provider` field) and the
default is config-driven (`default_tts_provider`). `FallbackTTS` composes two adapters
so a primary outage can't silence a session — itself a demonstration that the seam
holds (a `TTSAdapter` wrapping `TTSAdapter`s).

**This family is settled.** It is the foundation, not the subject of this doc. The
only forward note: the TTS interface carries inline performance tags (`[whispering]`,
`[laughs]`) and each adapter renders-or-drops them per its provider profile — keep
that contract when adding providers.

---

## 2. The character model — universal core + the `game_data` extension seam (DONE)

A [`Character`](../orchestrator/character_store.py) is the unit a player talks to. The
engine is **game-agnostic about identity**: it compiles a fixed set of *universal,
dramatic* fields into the system prompt (`build_prompt`) — identity, manner,
backstory, knowledge, plus game-agnostic mechanics (goals, secrets with reveal
conditions, boundaries, relationships, disposition).

Anything a *specific* game needs that the engine shouldn't understand lives in
**`game_data`** — an open, namespaced bag the engine stores and round-trips verbatim
but never interprets. This is already the cleanest engine/game seam in the codebase:

- A game registers a **renderer** for its namespace via
  [`register_game_extension(namespace, renderer)`](../orchestrator/character_extensions.py).
- At prompt-compile time, `build_prompt` calls `render_game_data` and appends each
  registered namespace's section. Unregistered namespaces stay inert (stored, not
  spoken). A renderer that throws is skipped, never fatal.

```
character.game_data = { "dnd5e": { "level": 5, "class": "rogue", ... } }
                              │
        register_game_extension("dnd5e", render_dnd5e)   ← game layer, at startup
                              │
        build_prompt() ──► appends render_dnd5e(sheet) as a prompt section
```

**Why it matters here:** this is the template for every other engine/game seam below.
The engine exposes a *registration point* and a *neutral data channel*; the game
supplies *meaning* at runtime. We want the context-in and memory seams to follow the
same shape rather than baking game concepts into the engine.

---

## 3. The engine/game seam — the core generalization (TARGET)

### 3.1 The problem: `run_turn(user_text)` is chat-shaped

Today the entry point is
[`Pipeline.run_turn(user_text, latency, emit_json, emit_audio)`](../orchestrator/pipeline.py),
called from the WebSocket loop in [`main.py`](../orchestrator/main.py) once per
finalized transcript / typed line. Two assumptions are baked in:

1. **The trigger is a user utterance.** But in a game the trigger is the *game's* to
   decide — a typed line in a crime game, a dialogue-node entry in a 2D RPG, a
   proximity/event hook in a 3D RPG. There may be no "user message" at all.
2. **The retrieval + prompt input is the player's last message.** But what a character
   should respond to is richer: where they are, the in-game time, who else is present,
   what just happened, quest state.

"Turn" is a conversation abstraction. The engine's real unit is: **produce this
character's response/action given an input + game-supplied context.**

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
`RespondRequest(player_input=user_text)` — so the current voice loop keeps working
unchanged while the richer path opens up.

The streaming pipeline itself (producer/consumer overlap, sentence chunking, batching,
fades — section "the one thing that matters" in the README) is **untouched**. This
generalization is entirely about *what feeds the prompt and the retrieval query*, not
how audio is produced.

### 3.3 Prompt assembly: three sources, one system prompt

A character "understands their world" from three composable sources. Today
[`_build_system`](../orchestrator/pipeline.py) composes two of them; the third is new.

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

The key design point: **not everything the game knows needs to live in memory.**
"It's raining and the guard is watching you" is true *now* and injected per request;
it should not pollute the durable store. The `Situation` channel is how the game says
"here's what's true at this instant" without committing it to memory.

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

This is the same embed-and-store path as a conversation exchange (see §4), so
retrieval surfaces game-pushed events exactly like remembered dialogue. **Game-time is
a tag the game supplies** — the engine stores it opaquely; the game defines the
calendar. Storing `when` is also what unlocks **recency weighting** in retrieval (§4).

**Division of ownership, stated plainly:**

- The **engine owns the character's memory** — embedding, storage, retrieval,
  namespaces.
- The **game owns the world and the clock** — it decides what happened, when, and
  what's true right now, and pushes that across the seam two ways: transient
  `Situation` per request, durable `remember(...)` for events worth recalling.

---

## 4. Memory & retrieval (TARGET — issue #1)

### 4.1 How retrieval works today (DONE)

[`LongTermMemory`](../orchestrator/memory/long_term.py): each completed exchange is
embedded (local `all-MiniLM-L6-v2`, 384-dim) and stored in a per-character ChromaDB
collection (one collection per `memory_namespace`). On each request the input is
embedded the same way and the *k* nearest by cosine distance are injected. Semantic,
not keyword: *"remember the boat I fixed?"* surfaces the boat exchange even if worded
differently. [`ShortTermMemory`](../orchestrator/memory/short_term.py) is a separate
verbatim rolling buffer of the last N turns.

### 4.2 Known limits (to fix)

- **Pure similarity.** No recency or importance weighting — an ancient weak match can
  edge out a recent strong one. Storing `when` (§3.4) is the prerequisite for recency.
- **Fixed `k=4`, no threshold.** Returns the 4 nearest even when all are weak; should
  support a relevance floor and a query-dependent `k`.
- **Query = last message only.** Should accept the game's richer `retrieval_query`
  (location + situation + input), per §3.2.

### 4.3 Store & embeddings — drop the heavy ANN index (TARGET)

The build pain was ChromaDB's native ANN index (hnswlib) on Windows. The key
realization: **per-character memory is small** (hundreds–low-thousands of exchanges),
so a heavy approximate index buys nothing.

- **Embeddings:** `fastembed` (ONNX, no PyTorch — light, Windows-friendly), or keep
  `sentence-transformers` (GPU-accelerable). **Avoid cloud embedding APIs** — a
  network hop per request hurts latency.
- **Store:** drop Chroma. Either `sqlite-vec` / LanceDB (embedded, pip-only, no native
  build, ~1–10 ms), or — given the data size — brute-force cosine over a NumPy array
  (sub-millisecond, zero extra deps).
- **Recommendation:** `fastembed` + LanceDB (or `sqlite-vec`). Local retrieval is a few
  ms; the real latency budget is LLM + TTS, so memory stays off the critical path.

This is a swap *behind the existing `LongTermMemory` surface* (`add_exchange`,
`retrieve`, plus the new `remember`). Because the pipeline only touches that surface,
the store change is a one-module job — the same discipline as the provider seams.

---

## 5. Proposed seam surface (summary)

The engine exposes, and the game consumes:

| Seam | Direction | Mechanism | Status |
| --- | --- | --- | --- |
| Provider (STT/LLM/TTS) | engine → vendor | `*Adapter` ABCs | DONE |
| Character depth | game → engine | `register_game_extension` + `game_data` | DONE |
| Respond trigger + context-in | game → engine | `RespondRequest` / `Situation` | TARGET |
| Durable world events | game → engine | `memory.remember(ns, fact, when, kind)` | TARGET |
| Memory store/embeddings | engine internal | behind `LongTermMemory` | TARGET |

Design rule for every new seam: **the engine exposes a registration point and a
neutral data channel; the game supplies meaning at runtime.** No game concept
(quests, factions, D&D classes, clocks) is ever named in engine code.

---

## 6. Build order

1. **Generalize the entry point.** Introduce `RespondRequest` + `Situation`; make
   `run_turn` a wrapper. Inject the "Current situation" section in `_build_system`.
   Pipeline internals unchanged. *(Smallest change that unblocks the game-director.)*
2. **Memory store swap.** Replace Chroma behind `LongTermMemory` with
   fastembed + LanceDB/sqlite-vec. Add a relevance threshold and query-dependent `k`.
3. **Memory-write API + `when` tag.** Add `remember(...)`; store the game-time tag;
   add recency weighting to retrieval now that timestamps exist.
4. **Richer retrieval query.** Wire `RespondRequest.retrieval_query` (location +
   situation + input) through `retrieve`.

Steps 1–2 are independent and can land in either order; 3 depends on 2, and 4 on 1.

---

## 7. Out of scope

- The game itself (rules engine, world simulation, rendering) — that's the *consumer*
  of these seams, a separate layer/repo.
- Multi-character scene orchestration (who speaks when) — a game-layer concern; the
  engine produces *one character's* response per request.
- Auth, cloud hosting, packaging — unchanged from v1's out-of-scope list.
- Provider-seam churn — the STT/LLM/TTS adapters are settled; don't reopen them here.
