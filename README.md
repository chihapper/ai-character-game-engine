# 🎲 AI Character Game Engine

A **game director** for dialogue-driven games: it drives **Inworld's full-loop
realtime voice agent** (STT → Claude LLM → Realtime TTS-2, with cross-turn voice
continuity) and owns the **game logic** — character definition and state, memory,
tools/mechanics, and the **world/time seam** between the game and the engine.

You define a character; the game tells the engine what's happening; the engine makes
that character respond — out loud, in a consistent cloned voice, with an **evolving inner
life**: memory that decays and reinforces, feelings that move and *scar*, beliefs formed
from experience, and forgiveness that must be earned. See
**[The character mind (Track E)](#the-character-mind-track-e)** below — it's the heart of
the project — and [`docs/engine-overview.md`](docs/engine-overview.md) for the full design.

> **Lineage.** This repo was seeded from the provider-agnostic **voice engine**, which
> lives on as its own portfolio project:
> [real-time-ai-character-engine](https://github.com/chihapper/real-time-ai-character-engine)
> (ancestry snapshot: tag **`voice-engine-v1`**, in both repos). The modular streaming
> pipeline described below is that inheritance — the path the full-loop agent
> **replaces**. It still runs in `main` today, but it is being retired, not extended.
>
> **Architecture & direction:** see [`docs/architecture-seams.md`](docs/architecture-seams.md)
> for the engine/game seam design, and open issues
> **[#1](https://github.com/chihapper/ai-character-game-engine/issues/1)** (memory/retrieval)
> and **[#2](https://github.com/chihapper/ai-character-game-engine/issues/2)** (generalizing
> the engine for the game-director).

---

## The technical setup: Inworld's full loop

The voice runtime is **Inworld's Realtime API agent**, driven over a WebSocket
(OpenAI Realtime protocol). One agent session is the whole loop — **STT → LLM → TTS** —
so we get **cross-turn voice continuity** (prosody and timbre carry between turns)
that a per-utterance TTS can't give. Inside that session:

- **The LLM is routed to Claude** (`anthropic/claude-sonnet-4-6`) — the agent reasons
  as Claude, Inworld handles the speech ends.
- **Our character *is* the agent's instructions.** The engine compiles a character's
  structured profile into a system prompt
  ([`Character.build_prompt()`](orchestrator/character_store.py)) and hands it to the
  session as the agent's instructions — so the same character definition that drives
  the text path drives the voice agent.
- **Tools are how the game runs mechanics.** Function-calling lets the engine execute
  game logic *through the conversation* — a dice roll, a state change, a quest update —
  instead of having the model narrate outcomes it shouldn't decide. (Feasibility for
  steering + tools is validated; see the spike on branch `inworld-full-loop`.)

```
game event / player line
        │
        ▼
  game director (this repo)  ──►  character prompt + tools + per-request situation
        │                                         │
        │  owns: character state, memory,         ▼
        │  world/time seam, mechanics      Inworld Realtime agent
        │                                  (STT → Claude → Realtime TTS-2,
        ▼                                   cross-turn voice continuity)
   long-term memory  ◄── remembers ───────────────┘
                                                   │
                                                   ▼
                                            🔊 spoken, in-voice reply
```

What the engine owns vs. what Inworld owns is the point: **Inworld owns the voice
loop; this repo owns the game-character logic.** The seams between them — context-in,
the memory-write API, the world/time channel — are specified in
[`docs/architecture-seams.md`](docs/architecture-seams.md).

---

## The inherited pipeline: streaming overlap (being retired)

Before the full-loop agent lands, `main` still runs the inherited modular pipeline, so
it's documented here. It's good engineering — the character starts speaking **~1 second
after the input lands** because the stages *overlap* instead of running end-to-end — but
the full-loop session gives cross-turn voice continuity natively, so this path is being
**replaced**, not extended:

```
input (player line / event)
      │
      ▼
  STT  ──►  transcript
                │
                ▼
          LLM (Claude, streaming)  ──► "Oh, you're back." ──► "I wondered…" ──► …
                                              │                      │
                                  sentence 1 ready             sentence 2 ready
                                              │                      │
                                              ▼                      ▼
                                        TTS sentence 1   ║    TTS sentence 2   (overlapping)
                                              │                      │
                                              ▼                      ▼
                               🔊 you hear sentence 1  while  sentence 2 is still being made
```

As the LLM streams tokens, [`sentence_chunker.py`](orchestrator/sentence_chunker.py)
splits them into sentences on the fly; the moment sentence 1 is complete it's sent to
TTS and audio streams back — **while the LLM is still generating the rest**. The
overlap logic lives in [`pipeline.py`](orchestrator/pipeline.py). Every stage is timed
and the **latency panel** in the UI makes the budget visible. The same prompt-assembly
and memory that feed this pipeline feed the full-loop agent.

---

## Architecture: adapters & seams

Two families of seam keep the pieces swappable. The full design is in
[`docs/architecture-seams.md`](docs/architecture-seams.md); in brief:

**Provider seams (inherited, retiring)** — every external vendor sits behind an adapter
interface ([`adapters/base.py`](orchestrator/adapters/base.py)); the pipeline depends
only on the interface, never a concrete provider. Under the full loop the STT and TTS
seams collapse into the Inworld session and the `LLMAdapter` is superseded by in-session
Claude routing — so treat this layer as the retiring path. Voice cloning/design is the
piece that survives (the engine still mints the voice id it hands to the session):

| Role | Interface | Implementations |
| --- | --- | --- |
| Speech-to-text | `STTAdapter` | Whisper (local), AssemblyAI (batch + realtime) |
| LLM | `LLMAdapter` | Anthropic (streaming) |
| Text-to-speech | `TTSAdapter` | Inworld, ElevenLabs, Cartesia, Fallback |

The audio wire format (PCM s16le, mono, 24 kHz) is fixed in
[`config.py`](orchestrator/config.py) so the browser playback path is identical
regardless of provider. Provider choice is **per-character** (the YAML `tts_provider`
field) — the cost/quality lever at scale.

**The engine/game seam** — how a game drives the engine and pushes in world state.
A character is universal core fields plus an open `game_data` bag the engine stores but
never interprets; a game layer registers a renderer for its namespace
([`character_extensions.py`](orchestrator/character_extensions.py)) to add game-shaped
depth. The entry point is generalized from "reply to a chat message" to
**`respond(RespondRequest)`** ([`context.py`](orchestrator/context.py)) — a player line
and/or a game event plus a transient `Situation` (location, time, who's present, recent
events) injected as a "Current situation" section; `run_turn` is now a thin wrapper.
Durable world events come in via the **`remember()`** memory-write API. See
[`docs/architecture-seams.md`](docs/architecture-seams.md) and issue
[#2](https://github.com/chihapper/ai-character-game-engine/issues/2).

**Memory** is two-tier: a short-term verbatim buffer of recent turns
([`memory/short_term.py`](orchestrator/memory/short_term.py)) plus a long-term store
([`memory/long_term.py`](orchestrator/memory/long_term.py)) recalled by **relevance
realization**, not a fixed top-k. Each turn, [`memory/relevance.py`](orchestrator/memory/relevance.py)
balances *similarity · recency · importance · diversity* under a budget — an
opponent-processing scorer inspired by Vervaeke et al.; similarity is z-score-spread to
counter embedder anisotropy. Stored memories carry a **character-aware salience**
(`importance`) scored at write time by [`salience.py`](orchestrator/salience.py) — the
player's loss is pivotal for a caring Bri, near-forgettable for a cold Corvin. Embeddings
are local **fastembed** (ONNX; a lexical fallback when it's absent) — no ChromaDB, no
native build. See [`docs/relevance-scoring.md`](docs/relevance-scoring.md) and issues
[#1](https://github.com/chihapper/ai-character-game-engine/issues/1) /
[#3](https://github.com/chihapper/ai-character-game-engine/issues/3).

---

## The character mind (Track E)

Recall is the foundation; the inner life built on top of it is the heart of the project. One
runtime-agnostic **`Engine`** core ([`engine.py`](orchestrator/engine.py)) exposes
`prepare()` → `reflect()` (plus a headless `respond()`), so the *same* mind drives the voice
loop and any headless game. A single background "reflection" call updates the whole state each
turn at **~0 added player latency**, and every judgment is **AI-driven and character-aware** —
the LLM is the relevance realizer, never a hard-coded rule. Each layer is opt-in via config.

- **Relevance-realization recall** with **game-time decay + reinforcement** — trivial moments
  fade, pivotal ones stay vivid for in-game years; rehearsed memories resist forgetting
  (issues [#3](https://github.com/chihapper/ai-character-game-engine/issues/3) / #5).
- **Character-aware salience** — how memorable a moment is depends on *who the character is*.
- **Evolving relationship** — affection / trust / respect + mood, updated **asymptotically**
  (extremes are hard-won) and **character-aware** (pleasantries roll off a guarded character) (#6).
- **Trust is lost fast, regained slowly** — recovery after a betrayal is grinding and
  **sacrifice-gated**, never bought with words or the mere passage of time.
- **Permanent, multi-axis betrayal scars** — a betrayal caps an axis; *which* axes and how deep is
  AI-judged by character × betrayal type (a business double-cross spares respect; a romantic one
  doesn't). Scars can **heal**, but only by extraordinary, wound-relevant proof — and the *memory*
  of the betrayal never goes (#16 / #17).
- **Short-term intent** — the character pursues its own immediate aim, not just reacts (#8).
- **Commitments** — promises it makes are tracked, honored, and expire into memory (#4).
- **Beliefs** — it periodically consolidates experience into higher-level convictions that colour
  every turn — and can act *against* them under pressure, as relevance realization predicts (#9).
- **Knowledge boundaries + contradiction detection** — it knows only what it has lived, is honestly
  ignorant beyond that, and catches a player who contradicts established memory (#10).
- **World events + time** — disposition shifts from events the game pushes (even ones that hit the
  character indirectly), and feelings drift toward the character's baseline over in-game time —
  while a scar holds the line (#12).

The full design and rationale live in [`docs/engine-overview.md`](docs/engine-overview.md). Every
layer is validated by the harnesses in [`tools/`](tools) — multi-arc, multi-timescale, adversarial,
scale, and a lifetime-spanning integrated saga (to in-game clock 10,000) that asserts hard
invariants (scars never decrease, no axis exceeds its ceiling, values stay bounded).

> **Roadmap frontier.** The engine is *reactive* — it animates a character on demand. The next
> horizon is **autonomous agency**: NPCs that deliberate and act *unprompted*, living their own
> lives between sessions (issues [#19](https://github.com/chihapper/ai-character-game-engine/issues/19) / [#20](https://github.com/chihapper/ai-character-game-engine/issues/20)).

---

## Prerequisites

- **Python 3.10+**
- A microphone and a modern browser (Chrome/Edge/Firefox/Safari)
- API keys (only for the providers you actually use):
  - **Anthropic** — the LLM (the character's brain; also drives character drafting and
    memory-salience scoring). <https://console.anthropic.com/>
  - **Inworld** — TTS + voice cloning, and — in the full-loop runtime — the realtime
    agent that runs STT + LLM + TTS in one session. From the
    [Inworld portal](https://platform.inworld.ai/): API Keys → copy the **"Basic
    (Base64)" signature** verbatim (already base64-encoded — do not re-encode it).
  - **ElevenLabs / Cartesia** *(optional)* — alternative TTS providers behind the same adapter.
  - **AssemblyAI** *(optional)* — cloud STT for **voice input on the inherited modular
    runtime only** (the full loop uses Inworld's built-in STT; local **Whisper** is the
    offline alternative). Typed input needs no STT at all.

---

## Setup & run

```bash
git clone <this-repo>
cd ai-character-game-engine
cp .env.example .env        # then edit .env and paste your keys
```

Launch with the single command for your OS:

**macOS / Linux** — `./run.sh`  ·  **Windows (PowerShell)** — `./run.ps1`

The launch script creates a virtualenv, installs dependencies, and starts the server.
Open **<http://127.0.0.1:8000>**.

### Core vs. optional dependencies

The dependencies are split so the app always boots:

- **`requirements.txt`** (core) — the full text → LLM → TTS loop, character creation,
  voice cloning, **and cross-session memory** (relevance-realization recall works out of
  the box via a dependency-free lexical embedder). Installs cleanly everywhere.
- **`requirements-optional.txt`** — **fastembed** (ONNX semantic embeddings — sharper
  recall than the lexical fallback) and **Whisper** (local STT for voice input on the
  modular runtime). Installed **best-effort**; if they're absent the app still runs —
  memory just uses the coarser lexical embedder and local voice input is unavailable
  (typed input and the Inworld full loop are unaffected). No ChromaDB, no native ANN
  build (dropped per issue [#1](https://github.com/chihapper/ai-character-game-engine/issues/1)).

> fastembed downloads a small ONNX model on first use (and Whisper its model, if
> installed). Subsequent runs are fast.

### Manual run

```bash
python -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt            # core: text + LLM + TTS
pip install -r requirements-optional.txt   # optional: voice input + memory
python -m orchestrator.main
```

---

## Using it

**Conversation view** — pick a character and **Connect**; it greets you in its voice.
**Hold to talk**, speak, click to stop; ~1s later it replies out loud. You can also
type (handy for quick testing). The **latency panel** shows the headline number —
first audio N ms after you stopped talking.

**Create Character view** — enter the structured fields (or AI-draft them from a
one-line concept), then give it a voice: **record a ~12s sample** (instant-cloned by
the selected provider), **design** one from a text description, or **pick** a library/
preset voice. Create, switch back to Conversation, **Refresh**, and talk to it.

> **Consent:** voice cloning requires that the recorded sample is your own voice or a
> consenting party's — both providers' terms require this.

---

## Character profiles

One YAML per character in [`orchestrator/characters/`](orchestrator/characters), written
by the Create Character flow (or hand-authored). The engine compiles the structured
fields into the system prompt; game-specific data rides in an open `game_data` bag the
engine stores but never interprets (the engine/game seam):

```yaml
name: "Aria"
concept: "a sharp-witted archivist who speaks in clipped, dry sentences"
temperament: "Guarded, dry, allergic to small talk."
goals: ["Find out why you came back"]
secrets:
  - text: "She kept the letters you never sent."
    reveal_when: "you admit you missed her"
boundaries: ["Won't discuss the fire"]
tts_provider: inworld          # or: elevenlabs / cartesia — no code change
voice_id: "Ashley"             # preset, library, or a clone id from Create Character
greeting: "Oh — you're back. I wondered when you'd show up."
game_data: {}                  # open, namespaced; a game layer renders this
memory_namespace: "aria"       # isolates this character's long-term memory
```

Legacy characters with only a freeform `system_prompt` still work. To A/B two TTS
providers on the same cloned voice, clone it on both and flip `tts_provider` between
two YAMLs (or use the **Duplicate** action).

---

## Configuration

All settings live in [`config.py`](orchestrator/config.py), overridable in `.env`:

| Setting | Default | Notes |
| --- | --- | --- |
| `VOICE_RUNTIME` | `pipeline` | `pipeline` = inherited modular STT→LLM→TTS (current default); `inworld_fullloop` = drive Inworld's realtime agent. |
| `LLM_MODEL` | `claude-sonnet-4-6` | Richer roleplay; switch to `claude-haiku-4-5` (fast) per session in the UI. |
| `DEFAULT_TTS_PROVIDER` | `elevenlabs` | Fallback when a character YAML doesn't specify one. |
| `STT_PROVIDER` | `whisper` | Modular-runtime voice input: `whisper` (local) or `assemblyai` (cloud). |
| `SALIENCE_MODEL` | `claude-sonnet-4-6` | Rates memory importance per character at write time (drop to haiku for cost). |
| `MEMORY_DEBUG` | `false` | Stream the relevance-realization panel to the browser (dev). |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | |

The audio wire format (PCM s16le, mono, 24 kHz) is fixed in `config.py` so playback is
identical regardless of TTS provider. The relevance-realization memory weights
(`RR_WEIGHT_*`, `RR_SIMILARITY_SPREAD`, …) live in `config.py` too — see
[`docs/relevance-scoring.md`](docs/relevance-scoring.md).

---

## Project structure

```
orchestrator/
  main.py                FastAPI app: UI, character REST API, voice WebSocket
  context.py             RespondRequest / Situation + instruction assembly (engine/game seam)
  engine.py              runtime-agnostic game-director core: prepare() / reflect() / respond()
  pipeline.py            streaming STT→LLM→sentence-chunk→TTS loop (the overlap) + latency
  salience.py            character-aware salience + the folded per-turn reflection
                         (relationship / intent / commitment / scar, one background call)
  consolidation.py       periodic belief formation (generative-agents-style reflection)
  consistency.py         contradiction detection (player claim vs established memory)
  config.py              settings + env loading
  sentence_chunker.py
  expressivity.py        per-provider performance-tag handling
  character_store.py     Character model + YAML load/list/save; build_prompt()
  character_extensions.py  game_data renderer registry (the engine/game seam)
  adapters/
    base.py              STTAdapter, LLMAdapter, TTSAdapter (the interfaces)
    _audio.py            PCM helpers (resample, fades, WAV)
    stt_whisper.py / stt_assemblyai.py / stt_assemblyai_stream.py
    llm_anthropic.py
    tts_inworld.py / tts_elevenlabs.py / tts_cartesia.py / tts_fallback.py
  realtime/
    inworld_session.py   Inworld full-loop runtime (behind VOICE_RUNTIME=inworld_fullloop)
  memory/
    short_term.py        rolling buffer of recent turns
    long_term.py         per-character JSONL store (fastembed/lexical) + remember() / beliefs
    relevance.py         RR scorer (similarity·recency·importance·diversity) + game-time decay
    relationship.py      evolving affection/trust/respect + mood, betrayal scars, time-decay
    intent.py            the character's evolving short-term aim (agency seed)
    commitments.py       promises the character makes (open / resolve / expire → memory)
  characters/            character profiles (YAML)
web/                     Conversation + Create Character UI, streaming PCM playback, RR debug panel
tools/clone_voice.py     CLI fallback for cloning
tools/backfill_salience.py  re-score a character's existing memories
tools/game_demo.py       headless game-loop demo driving the Engine (no voice)
tools/stress_*.py        engine validation harnesses (arcs · suite · beliefs · recovery · full saga)
docs/engine-overview.md      the character mind (Track E): every layer + rationale  ← current state
docs/architecture-seams.md   the engine/game seam design (Track V + Track E)
docs/track-v-full-loop-plan.md  the Inworld full-loop migration plan
docs/relevance-scoring.md    how memory recall is scored + decay + the debug panel
```

---

## Out of scope (for now)

Authentication, cloud hosting/deployment, and packaging to a distributable binary. The
**game integration itself** — the rules engine, world simulation, rendering — is a
separate consumer layer that drives this engine across the seams documented in
[`docs/architecture-seams.md`](docs/architecture-seams.md); this repo is the character
runtime and game director, not the game.
