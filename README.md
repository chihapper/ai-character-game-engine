# 🎲 AI Character Game Engine

An **AI-native character engine** for dialogue-driven games: NPCs whose minds are **driven by an LLM
at every level**, not scripted. The core is a deep **AI character mind** behind a clean
**engine/game seam**: relevance-realization **memory** that decays and reinforces, an **affect
model** where feelings move and *scar*, **beliefs** formed from experience, **forgiveness that must
be earned**, and **autonomous agency**, where characters deliberate and change on their own. Every
judgment (what's worth remembering, how a betrayal lands, whether to forgive, what to *become*) is
made by the AI *in character*, never by a hard-coded rule.

This is the part that's genuinely new. Most "character engines" keep a **fixed personality plus a
relationship counter**, because they optimize for *consistency*. This one is an **AI psyche that
genuinely changes**: it warms and cools, scars and heals, forms convictions and breaks them under
pressure, holds grudges and lets them go on its own. A consistent mask vs. a mind.

Because the mind sits behind a clean seam, the **front-end is pluggable**. The same `Engine` core
drives a text game, a grid arena, a Director's Sandbox, a Godot RPG, and earlier Unity and Unreal
clients. Voice and body are a **presentation layer the engine animates, not the engine itself**.

---

## Current state

> Dated snapshot: **2026-11-07**. The newest commit on any branch is from 2026-07-17. Evidence, known
> defects, and open decisions are in [`docs/project-status.md`](docs/project-status.md).

**The code is split across three lines of work, and they have not been merged.** Check which branch
you're on before following anything below.

| Branch | Where it is | What it holds |
| --- | --- | --- |
| `main` | GitHub default | Engine, Ferry text game, grid arena, mind server, Director's Sandbox, frozen Unity and Unreal source |
| `credibility-demo` | Owner's PC only, not pushed | Everything on `main`, plus the lich demo, judge audition, TTS provider registry, and local-LLM support |
| `game-rpg` | Owner's PC, 70 commits ahead of GitHub | The Godot RPG client and `game/rpg/`. Its engine predates the July judge fixes |

Tests pass on all three lines: 72 on `credibility-demo`, 65 on `main`, and 60 on `game-rpg`. Nothing
that calls a paid model was exercised for this snapshot, because paid testing has been frozen by the
owner since 2026-07-17.

### What each surface actually runs

**"The engine" and "the voice app" are not the same thing.** The app on port 8000 has the fast
streaming voice but only memory, not the full mind. The surfaces that run the full mind generate
the whole reply first and voice it afterwards. "Full mind" below means relationship, beliefs, and intent on; commitment detection and contradiction recording stay off unless set in `.env` (the RPG on `game-rpg` turns both on).

| Surface | Start it with | Open | Full mind? | Voice | Status |
| --- | --- | --- | --- | --- | --- |
| **Conversation app** | `python -m orchestrator.main` | `:8000/` | **No.** Memory and salience only | Streaming, sentence by sentence | Built, on every branch |
| **Director's Sandbox** | same process | `:8000/sandbox` | Yes | None | Built, on every branch |
| **Ferry text game** | `python -m game.server` | `:8001/play` | Yes | Optional Hume, after the text | Built, on every branch |
| Ferry, terminal version | `python -m game.play_cli` | terminal | Yes | None | Built, on every branch |
| **Grid arena** (experiment) | same process as Ferry | `:8001/embodied` | Yes, without `deliberate()` | None | Built, never evaluated |
| **Mind server** (HTTP API) | same process as Ferry | API prefix `:8001/api/mind/…`, no page | Yes, without `deliberate()` | TTS after the reply | No active client |
| **Credibility demo** | see [below](#credibility-demo) | `:8778/lich_demo.html` | Recorded runs | None yet | Built, not shipped |
| **Godot RPG** | see [below](#the-godot-rpg) | Godot 4.7 | Yes | Hume, streamed after the text | `game-rpg` only, idle since 2026-07-08 |
| Unity and Unreal clients | see [`unity/README.md`](unity/README.md), [`docs/unreal-port.md`](docs/unreal-port.md) | | Yes, without `deliberate()`, through the mind server | Yes | Frozen since July 2026. The full clients can't be rebuilt from this repo alone |

---

## The character mind

One runtime-agnostic **`Engine`** ([`engine.py`](orchestrator/engine.py)) exposes `respond()`,
`remember()`, `commit()`, `deliberate()`, and `choose_action()`. `respond()` is the live entry point
on every game surface. The lower-level `prepare()` and `reflect()` remain for a host that generates
the reply itself, which today only the unadopted full-loop runtime does.

A single folded judgment call updates salience, relationship, and intent for each turn, plus commitments when `commitment_detection` is on, which no game surface on this branch does.
Belief formation and contradiction checks are separate calls. With `background_reflection` on, the
judgment runs after the reply, so the player doesn't wait for it.

- **Relevance-realization recall** with **game-time decay + reinforcement**: trivial moments fade,
  pivotal ones stay vivid for in-game years, and rehearsed memories resist forgetting.
- **Character-aware salience**: how memorable a moment is depends on *who the character is*.
- **Evolving relationship**: affection, trust, respect, and mood, updated **asymptotically** (extremes
  are hard-won) and **character-aware** (pleasantries roll off a guarded character).
- **Trust is lost fast, regained slowly**: recovery after a betrayal is grinding and
  **sacrifice-gated**, never bought with words or the mere passage of time.
- **Multi-axis betrayal scars**: a betrayal caps an axis, and *which* axes and how deep is AI-judged
  by character and betrayal type. A business double-cross spares respect; a romantic one doesn't.
  Scars can **heal**, but only by extraordinary, wound-relevant proof or the character's own hard-won change of heart, and the *memory* of the
  betrayal never goes.
- **Short-term intent**: the character pursues its own immediate aim, not just reacts.
- **Commitments**: promises it makes are tracked, honored, and expire into memory.
- **Beliefs**: it periodically consolidates experience into higher-level convictions that color every
  turn, and it can act *against* them under pressure.
- **Knowledge boundaries + contradiction detection**: it knows only what it has lived, and it catches
  a player who contradicts established memory.
- **World events + time**: disposition shifts from events the game pushes, and feelings drift toward
  the character's baseline over in-game time, while a scar holds the line.
- **Autonomous agency**: the character can **deliberate and decide unprompted**, between scenes, and
  evolve its own goals. The game sets the cadence, the engine applies the inner change, and the game
  enacts any outward action. `deliberate()` runs **free** by default; **gated** mode is the opt-in
  constraint for on-rails games.

The full design is in [`docs/engine-overview.md`](docs/engine-overview.md). The integration contract
is [`docs/engine-game-contract.md`](docs/engine-game-contract.md).

**How it's validated.** The harnesses in [`tools/`](tools) cover multi-arc, multi-timescale,
adversarial, and lifetime-spanning runs. They were last run in June 2026, before the July judge
changes, and their reports aren't in the repo. The newest engine-level check is the 46-beat judge
battery of 2026-07-17. The demo's recorded data passes `tools/credibility_audit.py`, which checks
invariants such as "no axis ever exceeds its scar ceiling".

### Two seats: actor and judge

A character runs on two LLM roles, and they have very different requirements.

| Seat | Job | Set by | Default |
| --- | --- | --- | --- |
| **Actor** | Writes what the character says | The `Engine(llm=...)` adapter | Varies by surface |
| **Judge** | Decides what each moment means: salience, deltas, scars, beliefs, deliberation | `SALIENCE_MODEL`, `REFLECTION_MODEL`, `DELIBERATION_MODEL` | `claude-sonnet-4-6` for all three |

The audition, closed 2026-07-17, found that some open models pass a single hard moment but none held up
over a full life. **Only `claude-sonnet-4-6` has passed the 46-beat battery.** Haiku 4.5 and the
DeepSeek models failed it; Sonnet 5 and Opus 4.8 have never run it. A local model is viable for the
actor seat. See [`docs/judge-seat-requirements.md`](docs/judge-seat-requirements.md).

Any judge role can run locally by naming a model `local/<name>` (except on port 8000 once the Sandbox is used, which resets all three to Sonnet), which routes to an OpenAI-compatible
server such as Ollama or llama-server. A local **actor** works only through the credibility tools,
because every game surface currently hard-codes the Anthropic adapter.

---

## Architecture: adapters & seams

The full design is in [`docs/architecture-seams.md`](docs/architecture-seams.md). In brief:

**The engine/game seam.** The engine owns the *mind* and the game owns the *world*. A character is
universal core fields plus an open `game_data` bag the engine stores but never interprets. Games call
**`respond(RespondRequest)`** ([`context.py`](orchestrator/context.py)) with a player line and/or an
event plus a transient `Situation`, push durable events through **`remember()`**, advance their own
clock, and call **`deliberate()`** or **`choose_action()`** to let a character act. The engine applies
inner change and only *returns* outward actions.

**Memory** is two-tier: a short-term buffer of recent turns
([`memory/short_term.py`](orchestrator/memory/short_term.py)) plus a long-term store
([`memory/long_term.py`](orchestrator/memory/long_term.py)) recalled by **relevance realization**, not
a fixed top-k. [`memory/relevance.py`](orchestrator/memory/relevance.py) balances *similarity,
recency, importance, and diversity* under a budget. See
[`docs/relevance-scoring.md`](docs/relevance-scoring.md). Embeddings use local **fastembed** when
installed and fall back to a dependency-free lexical embedder. Each character's mind is a set of
files in `.memory/`, which is why it survives a restart.

**Provider seams.** Most external vendors sit behind an interface in
[`adapters/base.py`](orchestrator/adapters/base.py).

| Role | Interface | Implementations |
| --- | --- | --- |
| Speech-to-text | `STTAdapter` | Whisper (local), AssemblyAI (batch). The realtime client, `AssemblyAIStream`, sits outside the interface |
| LLM | `LLMAdapter` | Anthropic (streaming), OpenAI-compatible local server (non-streaming) |
| Text-to-speech | `TTSAdapter` | **Hume Octave** (the bake-off winner), Inworld, ElevenLabs, Cartesia, Fish, Chatterbox |
| Face animation | `FaceAnimAdapter` | NeuroSync, Audio2Face: *explored, paused* |

The audio wire format (PCM s16le, mono, 24 kHz) is fixed in [`config.py`](orchestrator/config.py), so
playback is identical regardless of provider.

---

## Voice

**Hume Octave won the bake-off, but no setting turns it on for you.** `GAME_TTS` and `DEFAULT_TTS_PROVIDER` don't select it, and no character YAML uses it. Two surfaces have Hume written into their code and speak whenever `HUME_API_KEY` is set: the credibility live server and, on `game-rpg`, the RPG server (`RPG_VOICE=0` turns it off). To turn it on for the Ferry game, set both of these in `.env`. On this branch the mind server's `/speak` also needs a non-empty `ELEVENLABS_API_KEY`, because of a `voice_ready` bug:

```bash
HUME_API_KEY=...
GAME_TTS=hume
```

`GAME_TTS` otherwise defaults to `inworld`, and the Ferry game's voice route only works with
`GAME_TTS=hume`. Hume voices are cast per character in `game/casting.py`. The adapter pins Octave
`version: "1"` because acting directions are Octave-1-only, and instant mode stays off because it
measurably narrowed the acting range.

There are three voice paths:

1. **Streaming pipeline** (the port 8000 app). Speech starts as soon as the first sentence is ready,
   while the LLM is still writing the rest. This is the fast path, but it runs no mind beyond memory.
   TTS is picked per character by the YAML `tts_provider`, or `DEFAULT_TTS_PROVIDER` if unset.
2. **Engine paths** (game server, mind server, credibility tools). The whole reply is generated, then
   voiced. This is where Hume's per-utterance acting directions work, because stage business reaches the
   adapter intact. The Godot RPG shows the text instantly and streams the voice in behind it.
3. **Inworld full loop** (`VOICE_RUNTIME=inworld_fullloop`). Spiked, still wired in but not re-tested, **not adopted**. Kept
   for the record in [`docs/track-v-full-loop-plan.md`](docs/track-v-full-loop-plan.md).

```
                          LLM (streaming) ──► "Oh, you're back." ──► "I wondered…" ──► …
                                                     │                     │
                                          sentence 1 ready        sentence 2 ready
                                                     ▼                     ▼
 Path 1, the overlap:                          TTS sentence 1  ║   TTS sentence 2
                                                     ▼                     ▼
                                      🔊 you hear sentence 1 while sentence 2 is still being made
```

The overlap logic lives in [`pipeline.py`](orchestrator/pipeline.py) and
[`sentence_chunker.py`](orchestrator/sentence_chunker.py). The latency panel in the port 8000 UI
shows the timing of each stage.

**Face and lip-sync are paused.** Audio-to-blendshape lip-sync was built through the `FaceAnimAdapter`
seam. NVIDIA Audio2Face drove a MetaHuman face in the Unreal client, and self-hosted NeuroSync later
replaced it behind the same seam.

---

## Setup

**You need:** Python 3.10 to 3.13 (development uses 3.13; 3.14 is untested), and an **Anthropic API key** for anything
that talks to a character. The port 8000 app has no text-only mode, so it also needs the TTS key of the character you connect to. Other keys are only needed for the providers you use:

- **Hume**: the chosen TTS.
- **Inworld, ElevenLabs, Cartesia, Fish**: other TTS providers. On port 8000, Inworld is required for 14 of the 15 shipped characters and ElevenLabs for the other. Inworld needs the "Basic
  (Base64)" signature copied verbatim.
- **AssemblyAI** *(optional)*: cloud speech-to-text. Local Whisper is the offline option, and typed
  input needs neither.

```bash
git clone <this-repo>
cd ai-character-game-engine
cp .env.example .env        # then edit .env and paste your keys
```

Then launch with one command. The script creates a virtualenv, installs dependencies, and starts
**only the port 8000 app**.

```bash
bash run.sh                 # macOS / Linux
```

```bash
./run.ps1                   # Windows PowerShell
```

Or install by hand:

```bash
python -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt            # core
pip install -r requirements-optional.txt   # fastembed + Whisper
pip install -r requirements-dev.txt        # pytest
python -m orchestrator.main
```

| File | What it's for |
| --- | --- |
| `requirements.txt` | Core app. Also pins `nvidia-audio2face-3d`, used only by the paused face layer |
| `requirements-optional.txt` | **fastembed** for sharper recall, **Whisper** for local speech-to-text |
| `requirements-gpu.txt` | NVIDIA libraries for running Whisper on a GPU |
| `requirements-dev.txt` | `pytest` |

> **Install the optional file if you want Hume.** The Hume adapter imports `numpy`, which no
> requirements file lists; the optional packages currently bring it in.

### Tests

```bash
python -m pytest tests
```

Install `requirements-dev.txt` first and activate the virtualenv, because the run scripts do neither. The tests need no keys and no network, and finish in seconds. Include the `tests` argument: a bare
`pytest` from the repo root can pick up stray local spike files.

### What costs money

Talking to any character bills your LLM key, and voice bills your TTS key. These are free: the test
suite, viewing the [credibility demo](#credibility-demo) page, `python -m tools.credibility_audit`,
and `python -m game.arena.inspect` without `--step`.

---

## Using it

### Conversation app (port 8000)

**Conversation:** pick a character and **Connect**, then type or use the talk button. With Whisper
you click to record and click again to send. With AssemblyAI, partial text streams and the turn ends
automatically.

**Create Character:** enter the fields or **Draft with AI**, then give it a voice by cloning a ~12s
sample, designing one, or picking a preset. The UI offers ElevenLabs, Inworld, and Cartesia. Hume is
not in the dropdown yet; set `tts_provider: hume` in the YAML by hand.

**Train Voice:** calibrates end-of-turn timing to your speech. Requires `STT_PROVIDER=assemblyai`.

> **Consent:** voice cloning requires that the sample is your own voice or a consenting party's.

### Director's Sandbox (`:8000/sandbox`)

The workbench for watching a mind change. Talk to a character, jump the clock, inject events, trigger
a deliberation, save and load the whole world, and pick the model for each role. It isn't linked from
the main UI, so open the URL directly.

### Ferry's Last Crossing (`:8001/play`)

The text game: an LLM Game Master, five authored beats, four NPCs, and free-form speaking and acting.
`python -m game.server` serves it on `127.0.0.1:8001`, and `python -m game.server_lan` binds all
interfaces. Each game has isolated minds, with up to five at once.

The same process serves the **grid arena** at `/embodied`, the treatment arm of the embodiment
experiment in [`docs/embodiment-experiment.md`](docs/embodiment-experiment.md), and the **mind
server** at `/api/mind`.

> ⚠️ **Starting a game at `/embodied` (the **Step inside** button), starting a mind-server session, running `game.play_cli`, or even loading
> `/api/mind/bakeoff` deletes `.memory/corvin-ashgrave-inworld.*`.** That's the credibility demo's
> default mind.

### The Godot RPG

**On the `game-rpg` branch only**, which isn't fully on GitHub yet. A Python game core owns all rules;
Godot 4.7 is a thin renderer over a local WebSocket. The game renders in 3D by default on a flat tile
grid, with a 2D fallback.

```bash
python -m game.rpg.server        # from the repo root, on ws://127.0.0.1:8787
```

Then open `godot/` in Godot 4.7 and press Play. Start order doesn't matter, because the client
retries. Choose the slice with `RPG_SLICE` in the environment of the **Godot** process.

| Slice | What it is | State |
| --- | --- | --- |
| `vault` (default) | Rooms-and-corridors dungeon | Completes end to end in the headless harness; not played in Godot |
| `emberdeep` | Cellular-automata caverns | Completes end to end in the headless harness; not played in Godot |
| `graywater` | Social town, Act 1 of *The Hollow Accord* | Explorable, no completable objective yet |

You explore under fog of war, talk to people, recruit them through conversation, fight turn-based
combat on SRD-based rules, and earn XP and loot. The world autosaves to `.saves/`, and minds persist
in `.memory/`. NPC replies and the Game Master default to `claude-haiku-4-5` (`RPG_MODEL`). Use
`RPG_VOICE=0` for text only and `RPG_2D=1` for the 2D view.

Campaign content, class choice, equipment, spells, voice input, and native packaging aren't built
yet. See [`docs/project-status.md`](docs/project-status.md).

### Credibility demo

**One mind, three futures:** the same character branched into three futures, each run through three
memory architectures (plain RAG, an affinity tracker, and this engine), to show what recall alone
can't do. Recorded on `credibility-demo`, and free to view:

```bash
python -m http.server 8778 --directory docs/credibility-demo
```

Then open <http://localhost:8778/lich_demo.html>. The page's talk links need the live server, which
bills per turn. See [`docs/credibility-demo.md`](docs/credibility-demo.md).

---

## Character profiles

One YAML per character in [`orchestrator/characters/`](orchestrator/characters), written by Create
Character or by hand. The engine compiles the fields into the system prompt.

```yaml
name: "Aria"
concept: "a sharp-witted archivist who speaks in clipped, dry sentences"
temperament: "Guarded, dry, allergic to small talk."
goals: ["Find out why you came back"]
secrets:
  - text: "She kept the letters you never sent."
    reveal_when: "you admit you missed her"
boundaries: ["Won't discuss the fire"]
tts_provider: inworld          # used on the port 8000 path; the game server uses GAME_TTS instead
voice_id: "Ashley"             # preset, library, or a clone id from Create Character
greeting: "Oh — you're back. I wondered when you'd show up."
game_data: {}                  # open, namespaced; a game layer renders this
memory_namespace: "aria"       # isolates this character's long-term memory
```

Legacy characters with only a freeform `system_prompt` still work. The shipped Inworld voice IDs may
be tied to the original workspace, and six characters have a blank `voice_id`, so you may need to set
your own.

---

## Configuration

Settings live in [`config.py`](orchestrator/config.py) and can be overridden in `.env`. This is the
short list; [`config.py`](orchestrator/config.py) has the rest. `GAME_*` and `LOCAL_JUDGE_*` are read from the environment, not from `config.py`.

| Setting | Default | Notes |
| --- | --- | --- |
| `VOICE_RUNTIME` | `pipeline` | Keep this. `inworld_fullloop` is the unadopted spike |
| `LLM_MODEL` | `claude-sonnet-4-6` | Port 8000 actor. Selectable per session in the UI |
| `DEFAULT_TTS_PROVIDER` | `elevenlabs` | Used when a character sets no provider |
| `GAME_TTS` | `inworld` | Mind server voice: `hume`, `inworld`, `elevenlabs`, `fish`, `chatterbox`. Ferry `/play` voice works only with `hume`. On this branch, the mind server also needs `ELEVENLABS_API_KEY` for any value except `inworld` |
| `STT_PROVIDER` | `whisper` | `whisper` (local) or `assemblyai` (cloud) |
| `SALIENCE_MODEL` | `claude-sonnet-4-6` | Judge: per-turn judgment and events |
| `REFLECTION_MODEL` | `claude-sonnet-4-6` | Judge: belief formation |
| `DELIBERATION_MODEL` | `claude-sonnet-4-6` | Judge: deliberation and goal reconciliation |
| `LOCAL_JUDGE_BASE_URL` | `http://127.0.0.1:8080/v1` | Local model server. Ollama uses port 11434 |
| `MEMORY_DIR` | `.memory/` | Where minds are stored |
| `MEMORY_DEBUG` | `false` | Streams the relevance panel to the browser |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Port 8000 app |
| `GAME_HOST` / `GAME_PORT` | `127.0.0.1` / `8001` | Game server |

**Local model settings and `.env`.** `LOCAL_JUDGE_*` are read straight from the process environment.
The game server and tools load `.env` into it, but `orchestrator.main` doesn't, so for port 8000 set
them in your shell.

**Capabilities.** Off by default: `relationship_state`, `intent_state`, `reflection_enabled`,
`commitment_detection`, `contradiction_detection`, `reinforce_on_recall`, and
`background_reflection`. On by default: `salience_scoring`, `relationship_time_decay`, `arena_query`,
and `recent_happenings`. Each `Engine` takes a snapshot of these as `EngineCaps` (except `reinforce_on_recall`, which the memory store reads from settings), and game surfaces
force relationship, reflection, and intent on in code, so setting those in `.env` has no effect there.

---

## Project structure

```
orchestrator/            the engine, plus the port 8000 app
  engine.py              the Engine: respond / remember / commit / deliberate / choose_action
  judgment.py            the judge seat: model routing, thinking headroom, empty-reply retry
  salience.py            character-aware salience + the folded per-turn judgment
  agency.py              autonomous deliberation and goal reconciliation
  consolidation.py       belief formation
  consistency.py         contradiction detection
  context.py             RespondRequest, Situation, and instruction assembly
  character_store.py     Character model, YAML load/save, build_prompt()
  character_extensions.py  game_data renderer registry
  character_draft.py     AI character drafting
  sandbox.py             Director's Sandbox backend
  config.py              settings, env loading, EngineCaps
  main.py                FastAPI app for port 8000: UI, character API, voice WebSockets
  pipeline.py            streaming STT → LLM → TTS loop. Does not use Engine
  sentence_chunker.py  expressivity.py  text_cleanup.py  timing.py  latency.py
  cadence.py  legacy_voice.py  profile_store.py   Train Voice: speaker timing calibration
  tts_providers.py       TTS registry (credibility-demo only)
  adapters/              stt_*, llm_anthropic, llm_openai_compat, tts_*, faceanim_*
  realtime/              Inworld full-loop spike, not adopted
  memory/                short_term, long_term, relevance, relationship, intent,
                         commitments, agency_store, base_store
  characters/            character YAMLs
game/
  runtime.py  dm.py  casting.py  policy.py  scenarios/   the Ferry text game
  web.py  web/           its web API and pages
  server.py              one process on :8001 hosting the text game, arena, and mind server
  server_lan.py          same, bound to all interfaces
  play_cli.py            terminal version
  arena/                 the grid arena (embodiment experiment)
  bridge/mind_api.py     the mind server, /api/mind
  experiment_log.py      run logger; rewrites docs/embodiment-experiment.md
  rpg/                   the RPG game core (game-rpg only)
godot/                   the Godot 4.7 client (game-rpg only)
unity/  unreal/          frozen 3D clients
web/                     port 8000 UI and the Sandbox UI
tests/                   offline test suite
tools/                   stress_* validation, *_demo scripts, credibility_*, judge_*
docs/                    see below
spikes/  scripts/        one-off probes and bake-off scripts
```

Only one of these needs care when editing: `docs/embodiment-experiment.md` is rewritten by the game
at runtime and must keep its `RUNS_TABLE` markers, or every game start fails.

---

## Documentation

**Living docs, kept current:**

| Doc | What it covers |
| --- | --- |
| [`docs/project-status.md`](docs/project-status.md) | Dated snapshot: branches, evidence, defects, decisions |
| [`docs/engine-overview.md`](docs/engine-overview.md) | Every layer of the mind, and why |
| [`docs/engine-game-contract.md`](docs/engine-game-contract.md) | The integration contract for a game |
| [`docs/architecture-seams.md`](docs/architecture-seams.md) | How the seams are designed |
| [`docs/relevance-scoring.md`](docs/relevance-scoring.md) | How recall is scored |
| [`docs/judge-seat-requirements.md`](docs/judge-seat-requirements.md) | Actor and judge seats, the audition |
| [`docs/tts-providers.md`](docs/tts-providers.md) | The TTS provider registry |
| [`docs/credibility-demo.md`](docs/credibility-demo.md) | The credibility demo |

**Records, kept for history:** [`docs/embodied-demo-architecture.md`](docs/embodied-demo-architecture.md),
[`docs/embodiment-experiment.md`](docs/embodiment-experiment.md),
[`docs/unity-client-architecture.md`](docs/unity-client-architecture.md),
[`docs/unreal-port.md`](docs/unreal-port.md),
[`docs/architecture-review-2026-07.md`](docs/architecture-review-2026-07.md),
[`docs/track-v-full-loop-plan.md`](docs/track-v-full-loop-plan.md). Each opens with a note on its
current status.

---

## Licence and IP

This repo is private and **has no licence file yet**, so no rights are granted. On `game-rpg`,
`LICENSE-SRD.md` covers the RPG's SRD 5.1 content under CC-BY-4.0 and sets naming rules: use "Game
Master", and don't use the publisher's trademarks. Most assets carry their own licences (`town/` has no licence file) under
`godot/assets/`.

**Lineage.** This repo was seeded from the provider-agnostic voice engine in
`chihapper/real-time-ai-character-engine`, also private. The shared ancestor is tag
**`voice-engine-v1`**, in both repos.

## Out of scope for now

Authentication, cloud hosting, and packaging to a distributable binary. Running the RPG today needs
Python, Godot, and API keys. There's also no CI, so tests only run when someone runs them.
