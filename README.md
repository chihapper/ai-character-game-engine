# 🎲 AI Character Game Engine

An **AI-native character engine** for dialogue-driven games — NPCs whose minds are **driven
by an LLM at every level**, not scripted. Its core — the *power* — is a deep **AI character
mind** behind a clean **engine/game seam**: relevance-realization **memory** that decays and
reinforces, an **affect model** where feelings move and *scar*, **beliefs** formed from
experience, **forgiveness that must be earned**, and **autonomous agency** — characters that
deliberate and change on their own. Every judgment — what's worth remembering, how a betrayal
lands, whether to forgive, what to *become* — is made by the AI *in character*, never by a
hard-coded rule. The same `Engine` core drives a headless game or a voice runtime alike.

This is the part that's genuinely new. Most "character engines" keep a **fixed personality plus
a relationship counter** — they optimize for *consistency*. This one is an **AI psyche that
genuinely changes**: it warms and cools, scars and heals, forms convictions and breaks them
under pressure, holds grudges and lets them go on its own. A consistent mask vs. a mind.

Because the mind sits behind a clean seam, the **front-end is pluggable** — text, 3D, or 2D,
the engine doesn't change. Built so far: a **voiced web demo** where characters speak aloud in
their own **Hume Octave** voices, and an **Unreal 5 MetaHuman** client (3D, spoken). A lip-sync
face layer (NVIDIA Audio2Face → self-hosted NeuroSync) was explored and is **currently paused**;
a **2D front-end (Godot)** is the current direction — a playable RPG ([`game/rpg`](game/rpg))
rendered by a Godot 4.7 client (see **RPG game** below). Voice and body are a **presentation layer the
engine animates, not the engine itself** — which is exactly why the front-end can change without
touching the mind.

You define a character; the game tells the engine what's happening; the AI makes that character
respond — and **evolve**: memory that decays and reinforces, feelings that move and *scar*,
beliefs formed from experience, forgiveness that must be earned, and characters that **deliberate
and change on their own**. The character mind is the heart of the project — see below, and
[`docs/engine-overview.md`](docs/engine-overview.md) for the full design.

> **Lineage.** This repo was seeded from the provider-agnostic **voice engine**, which lives on
> as its own portfolio project:
> [real-time-ai-character-engine](https://github.com/chihapper/real-time-ai-character-engine)
> (ancestry snapshot: tag **`voice-engine-v1`**, in both repos). The modular streaming pipeline
> documented later is that inheritance — and the path we **kept**: after a TTS bake-off it now
> runs **Hume Octave** for speech. (An Inworld single-session *full-loop* runtime was scoped and
> spiked but **not adopted**; the superseded plan is kept at
> [`docs/track-v-full-loop-plan.md`](docs/track-v-full-loop-plan.md).)

---

## The character mind (Track E) — the *power*

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
- **Autonomous agency** — characters that **live their own lives**: the game can push a character's
  *own* change of heart (forgiveness it reaches alone, player inactive — #19), and the character can
  **deliberate and decide unprompted**, between scenes, what it does or becomes from everything
  accumulated — evolving its goals and acting on its own (#20). Game-driven cadence; the engine
  applies the inner change, the game enacts the outward action. Runs **free** by default (the
  RR-grounded character acts as it sees fit — found to be the *more* coherent, identity-preserving
  mode); a **gated** mode is the opt-in constraint for controlled/on-rails games.

The full design and rationale live in [`docs/engine-overview.md`](docs/engine-overview.md). Every
layer is validated by the harnesses in [`tools/`](tools) — multi-arc, multi-timescale, adversarial,
scale, a lifetime-spanning integrated saga (to in-game clock 10,000) asserting hard invariants
(scars never decrease, no axis exceeds its ceiling, values stay bounded), and an autonomy-loop pass
confirming goal-evolution stays coherent and in-character over a full life.

> **From reactive to alive.** The engine began *reactive* (it animates a character on demand) and
> now reaches **autonomous agency** — characters that deliberate and act *unprompted*, living their
> own lives between scenes ([#19](https://github.com/chihapper/ai-character-game-engine/issues/19) / [#20](https://github.com/chihapper/ai-character-game-engine/issues/20), shipped). **Track V** — the voice runtime — is largely in hand (Hume Octave, voiced demo); the front-end direction is now the **2D Godot RPG** ([`game/rpg`](game/rpg); a 3D MetaHuman client also exists). Either way, the mind is the *power* and the presentation the *crown*.

---

## Architecture: adapters & seams

Two families of seam keep the pieces swappable. The full design is in
[`docs/architecture-seams.md`](docs/architecture-seams.md); in brief:

**The engine/game seam** — how a game drives the engine and pushes in world state.
A character is universal core fields plus an open `game_data` bag the engine stores but
never interprets; a game layer registers a renderer for its namespace
([`character_extensions.py`](orchestrator/character_extensions.py)) to add game-shaped
depth. The entry point is **`respond(RespondRequest)`** ([`context.py`](orchestrator/context.py))
— a player line and/or a game event plus a transient `Situation` (location, time, who's present,
recent events). Durable world events come in via the **`remember()`** memory-write API; the game
advances its own clock; and it can call **`deliberate()`** to let a character act on its own. See
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

**Provider seams** — every external vendor sits behind an adapter interface
([`adapters/base.py`](orchestrator/adapters/base.py)); the pipeline depends only on the
interface, never a concrete provider. This is what let a **TTS bake-off** swap providers with
a one-line change and settle on **Hume Octave**, and what lets a **face-animation** provider
plug in the same way:

| Role | Interface | Implementations |
| --- | --- | --- |
| Speech-to-text | `STTAdapter` | Whisper (local), AssemblyAI (batch + realtime) |
| LLM | `LLMAdapter` | Anthropic (streaming) |
| Text-to-speech | `TTSAdapter` | **Hume Octave** (chosen), Inworld, ElevenLabs, Cartesia, Fish, Chatterbox |
| Face animation | `FaceAnimAdapter` | NeuroSync (self-hosted), Audio2Face — *explored, paused* |

The audio wire format (PCM s16le, mono, 24 kHz) is fixed in
[`config.py`](orchestrator/config.py) so the browser playback path is identical
regardless of provider. Provider choice is **per-character** (the YAML `tts_provider`
field) — the cost/quality lever at scale.

---

## The voice + face layer (the *crown*, as-built)

The character mind needs no voice to work — but the engine can crown it with presentation.
What's actually built, and what isn't:

- **Voice — Hume Octave.** After a bake-off (Inworld, ElevenLabs, Cartesia, Fish, Chatterbox,
  Hume), **Hume won** on emotional range. The engine feeds it per-utterance *acting directions*
  (a character's own stage business becomes the delivery note), dynamic trailing silences, and
  cross-turn continuity. It runs **inside the modular pipeline** below — a provider behind the
  `TTSAdapter` seam, not a separate runtime.
- **Face / lip-sync — explored, paused.** Audio→ARKit-blendshape lip-sync was built through the
  `FaceAnimAdapter` seam (NVIDIA Audio2Face, then self-hosted **NeuroSync** once A2F needed
  hardware the dev GPU lacked) and drove a MetaHuman face in the Unreal client. This layer is
  **currently on pause** while the front-end direction is under review.
- **Front-ends are pluggable.** A **voiced web demo** (text + spoken Hume replies) and an
  **Unreal 5 MetaHuman** client both drive the *same* engine. A **2D Godot** RPG
  ([`game/rpg`](game/rpg)) is the current front-end direction; the engine didn't change.

```
game event / player line
        │
        ▼
  game director (this repo)  ──►  character prompt + per-request situation
        │                                         │
        │  owns: the character mind,              ▼
        │  world/time seam, mechanics       modular pipeline
        │                                   (STT → Claude → Hume Octave TTS,
        ▼                                    streaming-overlapped)
   long-term memory  ◄── remembers ───────────────┘
                                                   │
                                                   ▼
                                     🔊 spoken reply  ─(optional)─►  face-anim seam
```

> **The road not taken.** An Inworld single-session **full-loop** runtime (one session owning
> STT→LLM→TTS, for native cross-turn voice continuity) was scoped and spiked but **not adopted** —
> the modular pipeline plus Hume gave us more control over each stage. The superseded plan is kept
> for the record at [`docs/track-v-full-loop-plan.md`](docs/track-v-full-loop-plan.md).

### The modular pipeline: streaming overlap

`main` runs the modular pipeline: the character starts speaking **~1 second after the input
lands** because the stages *overlap* instead of running end-to-end. Hume Octave is the TTS
stage; the rest is the streaming machinery that keeps first-audio fast:

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
and memory feed every front-end — the text demo, the voiced web demo, and the Unreal client.

---

## Prerequisites

- **Python 3.10+**
- A microphone and a modern browser (Chrome/Edge/Firefox/Safari)
- API keys (only for the providers you actually use):
  - **Anthropic** — the LLM (the character's brain; also drives character drafting and
    memory-salience scoring). <https://console.anthropic.com/>
  - **Hume** — the chosen TTS (Octave). Emotional-range voice with per-utterance acting
    directions. From the [Hume portal](https://platform.hume.ai/): copy your API key.
  - **Inworld / ElevenLabs / Cartesia / Fish** *(optional)* — alternative TTS providers behind
    the same adapter, kept as bake-off candidates. Inworld also needs the **"Basic (Base64)"
    signature** copied verbatim (already base64-encoded — do not re-encode it).
  - **AssemblyAI** *(optional)* — cloud STT for **voice input** (local **Whisper** is the
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
  (typed input is unaffected). No ChromaDB, no native ANN
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

## RPG game (`game/rpg`)

A playable SRD-style RPG built on the same engine — procedural dungeons, free-flow exploration,
turn-based combat, an AI Game Master narrator, and named NPCs (reskinned from the tuned cast)
whose minds evolve over the campaign. Three ways to run it (after **Setup & run** above):

- **Terminal dev view (tcod):** `.venv/Scripts/python.exe -m game.rpg.play`
  — env: `RPG_SLICE` (`vault` default, or `emberdeep`), `RPG_SEED`, `RPG_MODEL`.
- **WebSocket server (Phase B IPC seam):** `.venv/Scripts/python.exe -m game.rpg.server`
  — env: `RPG_HOST`, `RPG_PORT`, `RPG_MODEL`, `RPG_VOICE`; the client honors `RPG_WS_URL`
  to point at a non-default host.
- **Godot 4.7 client:** open the [`godot/`](godot) project in the Godot editor (or launch the
  editor with `--path godot`) and press Play — it connects to the local server above.

Voiced NPC dialogue needs `HUME_API_KEY` in `.env` (voice defaults on when the key is present;
`RPG_VOICE=0` forces text-only). The NPC minds need `ANTHROPIC_API_KEY`.

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
| `VOICE_RUNTIME` | `pipeline` | `pipeline` = modular STT→LLM→TTS (the runtime in use); `inworld_fullloop` = the spiked-but-not-adopted single-session agent. |
| `LLM_MODEL` | `claude-sonnet-4-6` | Richer roleplay; switch to `claude-haiku-4-5` (fast) per session in the UI. |
| `DEFAULT_TTS_PROVIDER` | `elevenlabs` | Fallback when a character YAML doesn't specify one. **Hume** is the chosen provider and what the voiced demo uses; set `hume` (or per-character `tts_provider: hume`) to make it the default. |
| `STT_PROVIDER` | `whisper` | Modular-runtime voice input: `whisper` (local) or `assemblyai` (cloud). |
| `SALIENCE_MODEL` | `claude-sonnet-4-6` | Rates memory importance per character at write time (drop to haiku for cost). |
| `MEMORY_DEBUG` | `false` | Stream the relevance-realization panel to the browser (dev). |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | |

The character-mind layers (relationship, beliefs, scars, world-events, time-decay, agency) are
each opt-in via their own flags — see [`config.py`](orchestrator/config.py) and
[`docs/engine-overview.md`](docs/engine-overview.md). The audio wire format (PCM s16le, mono,
24 kHz) is fixed in `config.py` so playback is identical regardless of TTS provider.

---

## Project structure

```
orchestrator/
  main.py                FastAPI app: UI, character REST API, voice WebSocket
  context.py             RespondRequest / Situation + instruction assembly (engine/game seam)
  engine.py              runtime-agnostic game-director core: prepare() / reflect() / respond() / deliberate()
  pipeline.py            streaming STT→LLM→sentence-chunk→TTS loop (the overlap) + latency
  salience.py            character-aware salience + the folded per-turn reflection
                         (relationship / intent / commitment / scar, one background call)
  consolidation.py       periodic belief formation (generative-agents-style reflection)
  consistency.py         contradiction detection (player claim vs established memory)
  agency.py              autonomous deliberation: the character decides + acts unprompted (#20)
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
    tts_hume.py (chosen) / tts_inworld.py / tts_elevenlabs.py / tts_cartesia.py / tts_fish.py / tts_chatterbox.py / tts_fallback.py
    faceanim_neurosync.py / faceanim_a2f.py   FaceAnimAdapter (audio→ARKit lip-sync) — explored, paused
  realtime/
    full_loop.py / inworld_session.py   Inworld full-loop spike — scoped, NOT adopted (behind VOICE_RUNTIME=inworld_fullloop)
  memory/
    short_term.py        rolling buffer of recent turns
    long_term.py         per-character JSONL store (fastembed/lexical) + remember() / beliefs
    relevance.py         RR scorer (similarity·recency·importance·diversity) + game-time decay
    relationship.py      evolving affection/trust/respect + mood, betrayal scars, time-decay
    intent.py            the character's evolving short-term aim (agency seed)
    commitments.py       promises the character makes (open / resolve / expire → memory)
    agency_store.py      evolving standing goals + last-deliberation clock (#20)
  characters/            character profiles (YAML)
web/                     Conversation + Create Character UI, streaming PCM playback, RR debug panel
tools/clone_voice.py     CLI fallback for cloning
tools/backfill_salience.py  re-score a character's existing memories
tools/game_demo.py       headless game-loop demo driving the Engine (no voice)
tools/stress_*.py        engine validation harnesses (arcs · suite · beliefs · recovery · saga · agency)
docs/engine-overview.md      the character mind (Track E): every layer + rationale  ← current state
docs/architecture-seams.md   the engine/game seam design (Track V + Track E)
docs/track-v-full-loop-plan.md  SUPERSEDED — the Inworld full-loop plan (not adopted; kept for record)
docs/relevance-scoring.md    how memory recall is scored + decay + the debug panel
```

---

## Out of scope (for now)

Authentication, cloud hosting/deployment, and packaging to a distributable binary. The
**game integration itself** — the rules engine, world simulation, rendering — is a
separate consumer layer that drives this engine across the seams documented in
[`docs/architecture-seams.md`](docs/architecture-seams.md); this repo is the character
runtime and game director, not the game.
