# Architecture & seams

> **What this doc is.** The design of the project's seams and why they sit where they do. A *seam* is
> a deliberate boundary: one side can change without the other noticing. This page describes the code
> as built on the `credibility-demo` branch, as of 2026-11-07. The newest commit is from 2026-07-17.
> Anything that isn't on `main` says so.
>
> [`engine-game-contract.md`](engine-game-contract.md) is the exact interface a game builds against.
> [`project-status.md`](project-status.md) holds the evidence, known defects, and open decisions.
> This doc began on 2026-06-25 as the plan for issues
> [#1 — memory & retrieval](https://github.com/chihapper/ai-character-game-engine/issues/1) and
> [#2 — generalize the engine](https://github.com/chihapper/ai-character-game-engine/issues/2),
> both now closed.

> **North star.** The long-term goal is the **engine/game seam** (§2–4): the boundary between a
> character's mind and the world it lives in. Voice is enabling infrastructure, not the destination.
> Don't let voice polish (latency, interruption handling, audio quality) crowd out that seam. When the two
> interact, favor the choice that keeps the engine/game seam clean.

## What this doc is for

The engine is a **character mind behind a game seam**: given who a character is and what's happening
in the world, it produces that character's response and owns the character's memory and state across
sessions. A separate **game layer** owns the world, the clock, and the rules. The same `Engine` drives
a text game, a grid arena, a Director's Sandbox, and the Godot RPG on the `game-rpg` branch. The Unity
and Unreal clients drove it too and are now frozen.

Two families of seam:

1. **Voice and provider seams** (§1). Every outside vendor sits behind an adapter, and three separate
   paths turn a character's words into audio.
2. **The engine/game seam** (§2–4). Character depth, context in, memory writes, world and time. This
   is the durable design, and it doesn't depend on which voice path delivers the audio.

Commit subjects call these two bodies of work **Track V** (voice) and **Track E** (engine).

---

## 1. Voice paths and provider seams

### 1.1 The real picture: three voice paths

**The fast voice path and the full mind are on different surfaces.** The app on port 8000 streams
speech while the LLM is still writing, but that voice loop runs only memory, not the full mind. The adopted surfaces that
run the full mind generate the whole reply first and voice it afterwards. The same app's `/sandbox` tool runs the full `Engine`, with no voice.

| Path | Where it runs | Mind | How audio is made | Status |
| --- | --- | --- | --- | --- |
| **Streaming pipeline** | [`Pipeline`](../orchestrator/pipeline.py) behind `/ws` in the port 8000 app, `VOICE_RUNTIME=pipeline` (the default) | Memory and salience only. No `Engine` | Separate speech-to-text (STT), LLM, and text-to-speech (TTS) adapters, overlapped sentence by sentence | Kept |
| **Engine paths** | Ferry text game, mind server, credibility tools (`credibility-demo` only), Godot RPG (`game-rpg` only) | The full [`Engine`](../orchestrator/engine.py) | Whole reply first, then the caller hands it to a TTS adapter | Kept |
| **Inworld full loop** | [`orchestrator/realtime/`](../orchestrator/realtime), `VOICE_RUNTIME=inworld_fullloop` | `Engine.prepare()` and `reflect()` around a vendor-hosted session | One Inworld session owns STT, LLM, and TTS | Spiked, **not adopted** |

The Director's Sandbox and the grid arena also run the full `Engine`, but they have no voice. A
*spike* is a quick experiment to test an idea before committing to it.

```
Streaming pipeline (port 8000)

  mic or typed line ──► STT adapter ──► LLM adapter ──► sentence chunker ──► TTS adapter ──► browser
                                            ▲              (streaming)
                  recall from long-term memory; salience and storage after the reply

Engine paths

  game ──► Engine.respond() ──► whole reply ──► game shows it ──► TTS adapter ──► player
               │                                                  (optional step)
               └── recall, context assembly, judgment, state on disk

Inworld full loop (not adopted)

  browser ◄──► one Inworld session: STT ► LLM ► TTS
                    ▲
                    ├── Engine.prepare() injects the context for each turn
                    └── Engine.reflect() runs after the turn
```

**The streaming pipeline** came from the voice engine this repo was seeded from. Two concurrent tasks
share a queue: one reads the LLM stream and pushes each finished sentence, the other voices sentences
in order. The player hears sentence one while the LLM writes sentence two. `Pipeline` uses long-term
and short-term memory, the arena query (§4.2), and salience scoring (rating how much a moment matters
to this character). It never builds an `Engine`, and [`main.py`](../orchestrator/main.py) is its only
caller. So the relationship, intent, belief, commitment, and contradiction flags have no effect on
this path.

**The Engine paths** are text-first. `Engine.respond()` returns the whole reply, then the caller hands
it to `stream_speech()` as a separate step. The Ferry game's `/voice` route (which needs
`GAME_TTS=hume`), the mind server's `/speak` routes, and the credibility tools all work this way, and
`GAME_TTS` picks the provider for the game and mind servers. This is where Hume's per-reply acting
works, because stage business (physical actions written into a reply) reaches the adapter intact. On
the pipeline, `clean_for_speech` strips the asterisks but keeps the words, and the chunker feeds the
adapter one sentence at a time. The Godot RPG (on `game-rpg`) shows the text at once and streams the
voice in behind it.

Whether to wire `Engine` into the port 8000 app is an open owner decision (decision 3 in
[`project-status.md`](project-status.md)). None of these paths was run for this snapshot, because paid
testing has been frozen since 2026-07-17.

### 1.2 Provider seams

Every outside vendor sits behind an interface in
[`adapters/base.py`](../orchestrator/adapters/base.py). Orchestration talks to the interface, so a
provider can be swapped or compared without touching the pipeline or the mind. The TTS bake-off (a
head-to-head comparison of voice providers) ran on this seam: each candidate was one adapter.

| Role | Interface | Implementations |
| --- | --- | --- |
| Speech-to-text | `STTAdapter` | Whisper (local), AssemblyAI (batch). `AssemblyAIStream`, the realtime client, is a separate class outside the interface |
| LLM | `LLMAdapter` | `AnthropicLLM` (streaming), `OpenAICompatLLM` (local servers, non-streaming; `credibility-demo` only) |
| Text-to-speech | `TTSAdapter` | Hume Octave, Inworld, ElevenLabs, Cartesia, Fish, Chatterbox. `FallbackTTS` is a wrapper that switches to a backup voice when the primary fails; only the port 8000 path uses it |
| Face animation | `FaceAnimAdapter` | NeuroSync, Audio2Face. *Paused* |

Two rules keep this seam clean:

- **One wire format.** Every TTS adapter yields raw PCM audio (signed 16-bit, mono, 24 kHz), set in
  [`config.py`](../orchestrator/config.py), so playback doesn't depend on the provider.
- **Provider specifics stay in the adapter.** The Hume adapter, for example, resamples Hume's 48 kHz
  audio to the wire format and pins the API version. Orchestration never sees either.

**Hume Octave is the chosen TTS provider, but no setting defaults to it.** Only the credibility tools pick it, hard-coded. `GAME_TTS` defaults to
`inworld`, `DEFAULT_TTS_PROVIDER` defaults to `elevenlabs`, and no character YAML sets `hume`. See
[Voice](../README.md#voice) in the README for how to turn it on.

Prompting is a second provider-keyed seam. `VoiceProfile` classes in
[`expressivity.py`](../orchestrator/expressivity.py) hold how to *write* for a provider, and
`TTSAdapter` holds how to *send* to it. On `credibility-demo`, the registry
[`tts_providers.py`](../orchestrator/tts_providers.py) ties the two together. See
[`tts-providers.md`](tts-providers.md). One gap: the profile's prompt directive reaches the model only
on the pipeline and the full loop. `Engine.respond()` passes no provider, so on Engine paths Hume's
acting comes entirely from the adapter reading stage text, not from prompting.

Voice cloning sits on the same seam through `TTSAdapter.clone_voice()`. The Create Character screen
uses it through Inworld, Cartesia, and ElevenLabs. The Hume adapter doesn't implement it.

### 1.3 Two LLM seats: actor and judge

A character runs on two LLM roles, kept apart because their requirements differ.

- **Actor.** Writes what the character says. It's the adapter passed as `Engine(llm=...)`, and it's
  used only for the spoken reply.
- **Judge.** Decides what each moment means: salience, relationship shifts, scars (the lasting
  caps a betrayal leaves on a feeling), beliefs, deliberation. Every judgment goes through `complete()` in
  [`judgment.py`](../orchestrator/judgment.py), which maps each role to one setting
  (`SALIENCE_MODEL`, `REFLECTION_MODEL`, `DELIBERATION_MODEL`). So "which model made this judgment?"
  has exactly one answer.

The audition that closed on 2026-07-17 found that open models pass a single hard moment but none held
up over a full life. Only `claude-sonnet-4-6` has passed the 46-beat battery. See
[`judge-seat-requirements.md`](judge-seat-requirements.md).

On `credibility-demo`, a judge role can run on a local server by naming a model `local/<name>`. A
local actor works only through the credibility tools, because every game surface hard-codes
`AnthropicLLM`.

### 1.4 The Inworld full loop: spiked, not adopted

In June 2026 the plan was to replace the modular pipeline with one Inworld Realtime session: a single
WebSocket connection to a vendor-hosted agent that does STT, LLM, and TTS itself. The argument was
voice continuity. One session carries prosody (the rhythm and melody of speech) across turns, which a
TTS called once per utterance could not. Inworld would own the speech ends and LLM hosting, and the
engine would keep the character definition, tools, memory, and the world seam.

A text-only spike confirmed the session obeyed `build_prompt()` output, fired a `roll_dice` function
call, and could route its LLM to Claude. That script, `realtime_fullloop_spike.py`, is gitignored and
isn't in the repo. The full plan is in [`track-v-full-loop-plan.md`](track-v-full-loop-plan.md), marked
superseded.

**The project did not adopt it.** After the TTS bake-off of 2026-07-04 it kept separate adapters,
which give more control over each stage than a single vendor-owned session. The adapter path also
gained cross-turn continuity: `HumeTTS` sends the previous generation's id as `context.generation_id`
for up to 300 seconds. That state is scoped to one adapter instance, so each game or session keeps a
single adapter, and `TTSAdapter.reset_continuation()` clears it at a scene change.

The code stays in the tree behind the flag. [`full_loop.py`](../orchestrator/realtime/full_loop.py)
wraps `Engine`: `prepare()` builds each turn's context, the session receives it as a context item and
generates the reply, and `reflect()` runs afterwards. Some limits to know about:

- A game's `Situation` reaches typed turns only. Voice turns pass none.
- It builds `Engine` with the process-default capabilities, so relationship, intent, and beliefs stay
  off unless enabled in `.env`.
- Its only tool is the placeholder `roll_dice`.

Whether to retire it is an open owner decision (decision 6 in
[`project-status.md`](project-status.md)). Code comments in `main.py`, `legacy_voice.py`, and
`orchestrator/realtime/` still call the pipeline "retiring" and the full loop the "keeper". The
opposite was decided.

---

## 2. The character model — universal core + the `game_data` extension seam

A [`Character`](../orchestrator/character_store.py) is the unit a player talks to. The
engine is **game-agnostic about identity**: it compiles a fixed set of *universal,
dramatic* fields into the instructions (`build_prompt`) — identity, manner, backstory,
knowledge, plus game-agnostic mechanics (goals, secrets with reveal conditions,
boundaries, relationships, disposition). Every voice path and game surface uses this
same compiled profile.

Anything a *specific* game needs that the engine shouldn't understand lives in
**`game_data`** — an open, namespaced bag the engine stores and round-trips verbatim
but never interprets. This is the cleanest engine/game seam in the codebase:

- A game registers a **renderer** for its namespace via
  [`register_game_extension(namespace, renderer)`](../orchestrator/character_extensions.py).
- At compile time, `build_prompt` calls `render_game_data` and appends each registered
  namespace's section. Unregistered namespaces stay inert (stored, not spoken). A
  renderer that throws is skipped, never fatal.

```
character.game_data = { "srd5": { "level": 5, "class": "rogue", ... } }
                              │
        register_game_extension("srd5", render_srd5)   ← game layer, at startup
                              │
        build_prompt() ──► appends render_srd5(sheet) as an instructions section
```

**As built, no game registers a renderer yet**, on any branch, so `game_data` is stored but adds
nothing to the prompt today. Game layers currently add context through `Situation.extra` and
`game/casting.py`, which writes the world frame into the character's backstory. One reserved key is
an exception to "never interprets": the port 8000 path reads `game_data.engine` for per-character `memory_readonly` and `arena_query` settings, and the full loop reads it for `memory_readonly` only.

**Why it matters here:** this is the template for every other engine/game seam below.
The engine exposes a *registration point* and a *neutral data channel*; the game
supplies *meaning* at runtime. The context-in and memory seams follow the same shape
rather than baking game concepts into the engine.

---

## 3. The engine/game seam — the core generalization

> **The concrete contract** a game builds against — real method signatures, what the
> engine *applies* vs *returns*, the in-the-moment reaction recipe, cadence/time ownership,
> and capability flags — lives in [`engine-game-contract.md`](engine-game-contract.md). This
> section is the design rationale; that doc is the interface.

### 3.1 The problem: `run_turn(user_text)` is chat-shaped

The entry point inherited from the voice engine was
[`Pipeline.run_turn(user_text, ...)`](../orchestrator/pipeline.py), called once per
finalized transcript or typed line. Two assumptions are baked into that shape:

1. **The trigger is a user utterance.** But in a game the trigger is the *game's* to
   decide — a typed line in a crime game, a dialogue-node entry in a 2D RPG, a
   proximity/event hook in a 3D RPG. There may be no "user message" at all.
2. **The retrieval + prompt input is the player's last message.** But what a character
   should respond to is richer: where they are, the in-game time, who else is present,
   what just happened, quest state.

"Turn" is a conversation abstraction. The engine's real unit is: **produce this
character's response/action given an input + game-supplied context.** This holds on
every voice path, because the generalization is about *what feeds the model*, not how
audio is produced.

### 3.2 The shape: a `RespondRequest`, not a string

A game calls **`Engine.respond(RespondRequest)`** in
[`engine.py`](../orchestrator/engine.py). The two request types live in
[`context.py`](../orchestrator/context.py):

```python
@dataclass
class RespondRequest:
    player_input: str | None = None     # a spoken/typed player line, if any
    event: str | None = None            # a game event that triggered this
                                        # ("player entered the tavern")
    situation: Situation | None = None  # transient "what's true right now"
    retrieval_query: str | None = None  # overrides what long-term memory is searched against
```

```python
@dataclass
class Situation:
    location: str = ""        # "the back room of the Salt Crow"
    game_time: str = ""       # game-defined clock string for display; the engine never parses it
    present: list[str] = field(default_factory=list)        # who else is here
    recent_events: list[str] = field(default_factory=list)  # what just happened
    extra: dict = field(default_factory=dict)               # open bag, rendered generically
    clock: float | None = None  # numeric game clock; the game owns the units
```

Four details matter when driving it:

- **`player_input` wins.** If a request carries both a line and an `event`, the engine uses the line
  and ignores the event.
- **Spoken lines are framed.** The model sees `The player says to you: "..."`, so a line like
  "Barkeep: a warm meal" can't be misread as a script label. An `event` stays unframed.
- **`Situation` is transient.** It's rendered into the prompt and never persisted. The game decides what's
  durable through `remember()` (§3.4).
- **`clock` and `game_time` do different jobs.** `game_time` is display text. `clock` is the number
  behind memory decay (§4) and working memory, and the engine only ever takes differences of it.

`Pipeline.respond()` takes the same request, and `Pipeline.run_turn()` is a thin wrapper that builds
`RespondRequest(player_input=user_text)`. A typed `/ws` turn can attach a `situation` payload. On that
path, recall and the `Situation` are all that reach the model.

### 3.3 Context assembly: many sources, one prompt

A character understands its world from these sources. The game owns only the last one.

| Source | Lifetime | Owner | Where it enters |
| --- | --- | --- | --- |
| **Static profile** | durable, authored | engine (character YAML) | `Character.build_prompt()`, in the system prompt |
| **Long-term memory** | durable, accreting | engine | recalled per request (§4) |
| **Beliefs** | durable, formed from experience | engine | the top few always, plus any recalled |
| **Evolved goals** | durable, changed by `deliberate()` | engine | shown once goals have moved from the profile |
| **Relationship** | durable, updated per turn | engine | feelings and scars, once the player has shaped them |
| **Intent** | durable, short-term aim | engine | shown when the character has one |
| **Commitments** | durable until closed | engine | open ones always injected |
| **Recent happenings** | a short clock window over stored memories | engine | fresh, high-salience events and the character's own acts |
| **Per-request situation** | transient | **game** | `Situation`, never stored |

`Engine.respond()` lays these out with the stable text first:

```
system prompt (byte-identical every turn)
  ENGINE_DIRECTION                how to stay in role (fixed)
  build_prompt()                  # Who you are / How you speak / Secrets…
                                  + game_data renderer sections (§2)

messages
  short-term history              recent turns, verbatim
  current user turn
    <context>
      # What's happening right now                       working memory
      # Memories from past conversations with this user  long-term recall (§4)
      # What you've come to believe about this person    beliefs
      # What you want now                                evolved goals
      # How the player has affected you                  relationship and scars
      # What you're trying to do right now               intent
      # Open commitments you've made                     commitments
      # Current situation                                game-pushed, transient
    </context>
    The player says to you: "…"
```

The layout exists for prompt caching, where the LLM provider reuses an unchanged prefix at lower cost.
The dynamic context used to be a second system block. It changed every turn, so it invalidated the
cached message history behind it. In the user turn it sits after the cached prefix, and because it
isn't saved to short-term memory, the history stays lean and byte-stable.

The other paths differ. `Pipeline` folds only recall and `Situation` into the system prompt, plus the
provider's performance directive. The full loop keeps its base instructions stable and injects the
same dynamic context as a session context item.

The key point: **not everything the game knows needs to live in memory.** "It's raining
and the guard is watching you" is true *now* and injected per request; it should not
pollute the durable store. The `Situation` channel says "here's what's true at this
instant" without committing it to memory.

### 3.4 The memory-write API: durable world events

The other direction across the seam: the game persists **durable** world facts into a
character's memory, so retrieval surfaces them later.

```python
# called by the game when something memorable happens in the world
salience = await eng.remember(
    "The player burned the harbor bridge.",
    player_role="caused",    # the player did it, so the character's disposition shifts too
    t=day,                   # numeric game clock; drives decay
    when="day 3",            # display tag; the engine stores it and never parses it
)
```

The signature is `Engine.remember(fact, *, player_role, actor, importance, magnitude, **kw)`, and
`t`, `when`, and `kind` pass through `**kw` to the store. It follows the same path as a conversation
exchange: the text is embedded (turned into numbers that can be compared for meaning) and stored (§4),
so retrieval surfaces game-pushed events exactly like remembered dialogue.

- **Attribution.** With `player_role` ("caused" or "benefited"), or `actor="self"` for the character's
  own change of heart, the judge also shifts the character's disposition. With neither, it's a pure
  memory write.
- **Salience.** Omit `importance` and the character appraises how much the event matters to *them*,
  optionally informed by a coarse `magnitude` hint. Pin `importance` and it's honored verbatim.
- **The return value** is the stored salience. The game reads it to decide, by its own policy, whether
  the event is worth interrupting the scene for.
- **Time.** Recency uses the numeric `t`, or insertion order when there's no clock. `when` is display
  only.

The `remember` message on the port 8000 `/ws` route is a narrower write. It goes straight to
`LongTermMemory` with no `Engine`, so `player_role` and `actor` are ignored and importance defaults to
0.7.

**Division of ownership, stated plainly:**

- The **engine owns the character's memory** — embedding, storage, retrieval, namespaces.
- The **game owns the world and the clock** — what happened, when, and what's true now,
  pushed across the seam two ways: transient `Situation` per request, durable
  `remember(...)` for events worth recalling.

### 3.5 The rest of the surface

The rule across all of these: the engine applies inner change and only *returns* outward actions.

- **`deliberate(situation, mode="free")`.** The game calls it whenever it wants, and the character
  decides on its own what it does or how it changes. The engine applies the inner half (feelings,
  intent, goals) and returns the decision, so the game can enact any `world_action`. `gated` mode is
  the opt-in constraint for on-rails games.
- **`choose_action(situation, options)`.** Picks one action from the concrete options the game
  supplies, grounded in the character's goals, aim, relationship, and beliefs. The game executes the
  choice and can render or ignore the returned expression.
- **`commit()` and `resolve_commitment()`.** Declare an obligation and close it. A closed commitment
  converts into an ordinary memory. No game surface calls `commit()` yet; only `tools/game_demo.py`
  does.
- **`prepare()` and `reflect()`.** The two halves of a turn, for a host that generates the reply
  itself. `respond()` calls both internally. The full loop is the only surface that calls them from outside `Engine`; `tools/stress_suite.py` also calls `prepare()` to capture context.
- **`EngineCaps`.** Each `Engine` takes a frozen snapshot of its capability flags when it's built. One
  surface can't silently reconfigure another's mind, and two engines with different capabilities can
  coexist in one process. Game surfaces force relationship, reflection, and intent on in code.
- **`last_postscript`.** The engine detaches a trailing `[[...]]` line from a reply and exposes it
  verbatim. A game's performance rules define what it means; the engine neither asks for it nor reads
  it.

### 3.6 Who drives the engine

A *driver* is any code that builds an `Engine` and calls it.

| Driver | File | Uses |
| --- | --- | --- |
| Ferry text game | [`game/runtime.py`](../game/runtime.py) | `respond`, `remember`, `deliberate` |
| Grid arena | [`game/arena/game.py`](../game/arena/game.py) | `respond`, `remember`, `choose_action` |
| Mind server | [`game/bridge/mind_api.py`](../game/bridge/mind_api.py) | `respond`, `remember`, `choose_action` |
| Director's Sandbox | [`orchestrator/sandbox.py`](../orchestrator/sandbox.py) | `respond`, `remember`, `deliberate` |
| Inworld full loop | [`orchestrator/realtime/full_loop.py`](../orchestrator/realtime/full_loop.py) | `prepare`, `reflect`, `remember`, `resolve_commitment` |
| Credibility tools (`credibility-demo` only) | [`tools/_harness.py`](../tools/_harness.py) | varies by tool |
| Godot RPG (`game-rpg` only) | `game/rpg/minds.py` | `respond`, `remember`, `deliberate`, `choose_action` |

Stress harnesses and one-off scripts under `tools/` and `spikes/` build their own engines too. Each
driver is separate and their behavior has drifted, so a fix to one often misses the others.

---

## 4. Memory & retrieval (issue #1)

> **Framing — relevance realization (RR).** An NPC in a game world faces a "large world":
> limitless possible memories/facts. Semantic top-k is a single fixed relevance function —
> exactly the "small world" where "everything and nothing is relevant at the same time"
> (Vervaeke et al.). So recall is an **opponent-processing** balance —
> similarity (focus) · recency (salience) · importance (goal/arena bearing) · diversity
> (explore) — relative to the live query under a budget. Honestly an *approximation* (true
> RR is non-computational); the LLM is the real relevance realizer, and this shapes what
> enters its context. Implemented in [`memory/relevance.py`](../orchestrator/memory/relevance.py);
> the scoring + how-to-read-the-debug-panel guide is [`relevance-scoring.md`](relevance-scoring.md).

### 4.1 How retrieval works

[`LongTermMemory`](../orchestrator/memory/long_term.py): each completed exchange — and any
durable world event pushed via `remember` — is stored per character in a JSONL file (one JSON
record per line), one file per `memory_namespace`, with `importance`/`kind`/`when`. The `importance` is a **character-aware
salience** scored at write time by [`salience.py`](../orchestrator/salience.py) (an LLM rates
how memorable the moment is *to this character* — pivotal for a caring Bri, ~nil for a cold
Corvin), so old-but-pivotal memories survive recency decay. Embeddings are derived at load
(**fastembed** ONNX → sentence-transformers → a dependency-free **lexical fallback**, so
recall never silently disables). On each request, [`realize_relevance`](../orchestrator/memory/relevance.py)
selects by the opponent-processing balance above (with z-score similarity spreading;
brute-force over the small per-character set — no native ANN index).
[`ShortTermMemory`](../orchestrator/memory/short_term.py) is a separate verbatim rolling
buffer of recent turns. Scoring guide: [`relevance-scoring.md`](relevance-scoring.md).

### 4.2 The old limits — and where they stand

Before 2026-06-26, each exchange was embedded with local `all-MiniLM-L6-v2` into a per-character
ChromaDB collection, and the *k* nearest by cosine distance were injected. That was semantic, not
keyword, but it had three limits:

- **Pure similarity.** Fixed: recency and importance are now weighted (opponent processing).
- **Fixed `k=4`, no threshold.** Fixed: a budget (default 6) and a relevance floor drop weak matches.
- **Query = last message only.** Fixed: the **arena query** (`context.build_arena_query`) searches
  against the trigger + recent conversation + the live `Situation` + goals, so recall resolves
  referents ("her" → mom) and thin queries. Toggle: `ARENA_QUERY`. Engine paths also fold in the
  character's current stance toward the player and any evolved goals.

### 4.3 Store & embeddings — no heavy ANN index

The build pain was ChromaDB's native ANN index (hnswlib), an approximate-nearest-neighbor search
structure, on Windows. The realization: **per-character memory is small** (hundreds to low thousands
of exchanges), so a heavy approximate index buys nothing.

- **Store:** one human-readable JSONL file per character in `.memory/`. Records stay in memory and
  are scored by brute force. The character's other state sits beside it as sibling files: commitments,
  relationship, intent, and agency. Whole-file rewrites are atomic, so a crash can't truncate a mind. New memories are plain appends, so a crash mid-append can lose that one line, which the loader skips and logs as an error.
- **Embeddings:** derived from the text at load and never stored, so the file survives an embedder
  swap. The chain is `fastembed` (a small local library with no PyTorch, light and
  Windows-friendly), then `sentence-transformers`, then the lexical fallback. Only `requirements-optional.txt` installs
  `fastembed`, and `sentence-transformers` needs a manual install, so a core-only install runs on the
  lexical fallback.
- **No cloud embedding APIs.** A network hop per request would hurt latency. Keeping retrieval local
  keeps memory off the critical path.

All of this sits behind the `LongTermMemory` surface (`add_exchange`, `add_belief`, `retrieve`,
`remember`), so a later store swap is a one-module job.

---

## 5. Seam surface (summary)

"Built" means the code exists. For what was actually tested and when, see
[`project-status.md`](project-status.md).

| Seam | Direction | Mechanism | Status |
| --- | --- | --- | --- |
| Streaming voice path | engine → vendors | `Pipeline` + adapters, overlapped | Kept. Port 8000, no `Engine` |
| Engine voice path | game → vendors | `Engine.respond()`, then `TTSAdapter.stream_speech()` | Kept. Text first, voice after |
| Inworld full loop | engine → Inworld agent | One Realtime session around `prepare()` / `reflect()` | Spiked, not adopted |
| STT, LLM, TTS adapters | engine → vendors | `STTAdapter`, `LLMAdapter`, `TTSAdapter` | Built |
| TTS provider registry | engine → vendors | `tts_providers.py` + `VoiceProfile` | Built. Registry is `credibility-demo` only |
| Voice cloning/design | engine → vendor | `clone_voice()`, `design_voice()` on adapters | Built. Not on Hume |
| Face animation | engine → vendor | `FaceAnimAdapter`, through the mind server's `/speak_anim` | Built, paused |
| Actor LLM | game → engine | `Engine(llm=...)` | Built. Game surfaces hard-code `AnthropicLLM` |
| Judge LLM | engine → vendor | `judgment.complete()`, one model per role | Built. `local/<name>` is `credibility-demo` only |
| Character depth | game → engine | `register_game_extension` + `game_data` | Built. No game registers a renderer yet |
| Respond trigger + context-in | game → engine | `Engine.respond(RespondRequest)` + `Situation` | Built |
| Durable world events | game → engine | `Engine.remember(...)` | Built. `/ws` `remember` is a memory-only write |
| Commitments | game → engine | `Engine.commit()`, `resolve_commitment()` | Built. No game surface calls `commit()` yet |
| Autonomous change | game → engine | `Engine.deliberate()` | Built. The arena and mind server don't call it |
| Embodied action | game → engine | `Engine.choose_action(situation, options)` | Built |
| Host-run generation | voice runtime → engine | `Engine.prepare()` + `reflect()` | Built. Only the full loop generates a reply around it |
| Per-engine capabilities | driver → engine | `EngineCaps`, frozen at construction | Built |
| Working memory | engine internal | `_recent_happenings`, needs a clock | Built |
| Memory store/embeddings | engine internal | behind `LongTermMemory` | Built (JSONL + fastembed/lexical) |
| Relevance scoring | engine internal | `memory/relevance.py` opponent-processing + z-score spread | Built |
| Character-aware salience | engine internal | `salience.py` (LLM rates importance per character) | Built |

Design rule for every new seam: **the engine exposes a registration point and a neutral
data channel; the game supplies meaning at runtime.** No game concept (quests, factions,
character classes, calendars) drives engine logic, though the event-impact judge prompt in `salience.py` mentions a player's "faction or allies". One known leak: when `deliberate()` assembles
its grounding, it reads two `Situation.extra` keys by name, `Why you're here tonight` and `The world
you live in`, which the game drivers set.

---

## 6. Build order, as it happened

Dates come from git. All of this is on `main` unless marked.

**Track E, the engine/game seam:**

1. **2026-06-26.** `RespondRequest` + `Situation` (`context.py`). `run_turn` became a wrapper over
   `respond`.
2. **2026-06-26.** Store swap: dropped ChromaDB for a per-character JSONL store with a lexical
   fallback, brute-force scoring, a relevance floor, and a budget.
3. **2026-06-26.** Memory-write API and relevance realization (`memory/relevance.py`). See
   [`relevance-scoring.md`](relevance-scoring.md).
4. **2026-06-26.** Richer retrieval query: the arena query (`context.build_arena_query`), plus a
   role/competence baseline in salience, so a competent character reliably recalls domain facts even
   when routine (a bartender a drink order).
5. **2026-06-27.** Temporal decay ([issue #5](https://github.com/chihapper/ai-character-game-engine/issues/5)):
   recency by *in-game time*, modulated by salience and recall reinforcement (`rr_decay_*` in
   `config.py`), so a one-off fades while a pivotal or rehearsed memory persists.
6. **2026-06-27.** The `Engine` core, plus relationship state, intent, and belief consolidation.
7. **2026-06-28.** Autonomous agency: self-driven change and `deliberate()`, with `free` as the
   default mode.
8. **2026-06-29 to 06-30.** Director's Sandbox, goal reconciliation, working memory, the engine/game
   contract doc, and the Ferry text game.
9. **2026-07-01.** `EngineCaps`, the shared `judgment.py` layer, and the first grid arena code.
10. **2026-07-02.** The mind server, first built for the Unity client.
11. **2026-07-16 to 07-17.** Judge fixes from the audition. The neutral rubric and thinking headroom
    are on `main`. `local/<name>` routing and the scar wording fix are `credibility-demo` only.

**Track V, voice:**

1. **2026-06-26.** The Inworld full loop wired in behind `VOICE_RUNTIME=inworld_fullloop`, with
   per-turn memory recall added the same day.
2. **2026-06-27.** Full loop refactored onto the `Engine` core.
3. **2026-07-04.** TTS bake-off round 2 added the Hume, Fish, and Chatterbox adapters. Hume's acting
   directions and cross-turn continuation landed the same day, as did the `FaceAnimAdapter` seam.
4. **2026-07-05.** The docs recorded the decision to keep the modular pipeline.
5. **2026-07-08.** TTS provider registry (`credibility-demo` only).

What comes next isn't set here. The open decisions are in [`project-status.md`](project-status.md).

---

## 7. Boundaries

- **The game is a separate layer in the same repo.** `game/` holds the Ferry text game, the grid arena,
  and the mind server. `game/rpg/` and the Godot client live on `game-rpg`. Nothing in `orchestrator/`
  imports `game/`. The frozen Unity and Unreal clients own their worlds and reach the mind through the
  mind server.
- **Multi-character scene orchestration is a game-layer job.** The engine produces *one character's*
  response per request. In the Ferry game, `pick_responders` in [`game/dm.py`](../game/dm.py) decides
  who speaks.
- **Auth, cloud hosting, and packaging** aren't built.
