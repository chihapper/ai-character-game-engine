# Project notes for coding agents

## Project state — check before you start

`docs/project-status.md` is the dated snapshot of branches, evidence, known defects, and open
decisions. The traps that matter most:

- **Three unmerged lines of work.** `main` is on GitHub. `credibility-demo` (lich demo, judge
  audition, TTS registry, local LLM) is on the owner's PC only. `game-rpg` (Godot client, `game/rpg/`)
  is 70 commits ahead of GitHub. Check your branch before assuming a file exists.
- **Cost freeze.** The owner froze paid-model testing on 2026-07-17. Unless they say it's lifted,
  don't run `tools/stress_*`, `*_demo`, `credibility_*`, `judge_*`, or anything that talks to a
  character. `python -m pytest tests` is free and offline; always pass `tests`.
- **Stage files by name, never `git add -A`.** On `credibility-demo`, `godot/`, `asset_library/`, and
  `.saves/` are untracked and not ignored, and `godot/` holds the only copies of the painted
  portraits. Don't delete or clean them.
- **`docs/embodiment-experiment.md` is rewritten at runtime** by `game/experiment_log.py`. Keep its
  `RUNS_TABLE` markers, or every game start fails.
- **IP rules.** Write "Game Master", never the trademarked title, and use no publisher marks. See
  `LICENSE-SRD.md` on `game-rpg`.

## AssemblyAI (speech-to-text)

**Always fetch https://www.assemblyai.com/docs/llms-full.txt before writing or
changing AssemblyAI code.** The API changes — do not rely on memorized parameter
names. (Narrow with `?lang=python`.)

How this repo uses it (verified against live docs, 2026-06):

- **Auth is the raw key — no `Bearer` prefix** (`Authorization: <ASSEMBLYAI_API_KEY>`).
- **Realtime streaming** (`orchestrator/adapters/stt_assemblyai_stream.py`): the
  WebSocket model is `speech_model=u3-rt-pro` (singular). `encoding` defaults to
  `pcm_s16le`; `format_turns` is a no-op on this model. Audio is PCM16 mono 16 kHz
  in 50–1000 ms binary frames. Always send `{"type":"Terminate"}` to close.
  Endpointing is automatic via `end_of_turn` — tune with `min_turn_silence` /
  `max_turn_silence` (ms); `end_of_turn_confidence_threshold` is ignored on
  u3-rt-pro. The browser must stream continuously (including the trailing silence)
  so end-of-turn fires.
- **Batch** (`orchestrator/adapters/stt_assemblyai.py`): `speech_models` is required
  and is an ordered fallback list (`["universal-3-pro", "universal-2"]`).
- The browser never holds the key — audio is proxied through our backend, which
  mints the streaming token and connects to AssemblyAI server-side.

## Voice + face pipeline (Track V) — current state

- **`Pipeline` does not run the mind.** The port 8000 `/ws` loop on its default `pipeline` runtime (`orchestrator/main.py` +
  `pipeline.py`) never constructs `Engine`. It has streaming voice, recall, and salience only: no
  relationship, scars, intent, beliefs, commitments, or deliberation. The full mind runs on the
  `Engine` paths, which generate the whole reply and then call TTS. Don't assume a mind feature
  reaches port 8000.
- **TTS = Hume Octave** (`orchestrator/adapters/tts_hume.py`), chosen after a bake-off
  (Inworld / ElevenLabs / Cartesia / Fish / Chatterbox / Hume). It's a normal provider
  behind the `TTSAdapter` seam — per-utterance acting `description`, dynamic `trailing_silence`,
  cross-turn continuity via `context.generation_id`, scoped per adapter instance. **No provider setting
  selects it:** `GAME_TTS` defaults to `inworld`, `DEFAULT_TTS_PROVIDER` to `elevenlabs`, and no
  character YAML uses `hume`. It runs on the owner's PC because their `.env` sets `GAME_TTS=hume`. The credibility tools and, on
  `game-rpg`, `game/rpg/voice.py` call Hume directly, so `GAME_TTS` doesn't affect them.
  Hume casting is in `game/casting.py`. The adapter pins `version: "1"` because acting descriptions
  are Octave-1-only. Instant mode is OFF: acting range measured 1.54x with it on versus 1.85x off
  (`ff1d853`).
- **Face / lip-sync = PAUSED.** Audio→ARKit-blendshape lip-sync lives behind
  `FaceAnimAdapter`: NVIDIA **Audio2Face** (`faceanim_a2f.py`), replaced by self-hosted
  **NeuroSync** (`faceanim_neurosync.py`) when A2F needed Ampere+ hardware the old 1080 Ti lacked
  (the dev GPU is now an RTX 5080). Wired through the mind server's `/speak_anim`. The Godot talk
  scene uses voice-amplitude motion instead, and the face layer may not resume. Don't treat
  NeuroSync/A2F as active work unless the user resumes it.
- An Inworld single-session **full-loop** runtime (`orchestrator/realtime/`) was spiked but
  **NOT adopted** — the modular pipeline was kept. It still runs behind
  `VOICE_RUNTIME=inworld_fullloop`. See `docs/track-v-full-loop-plan.md` (marked superseded). Code
  comments that call the pipeline "retiring" are stale.

## Several engine drivers — fix ALL paths

Each surface builds its own `Engine`, and their behavior has drifted: `game/runtime.py` (Ferry text
game), `game/arena/game.py` (grid arena), `game/bridge/mind_api.py` (mind server),
`orchestrator/sandbox.py` (Director's Sandbox), `orchestrator/realtime/full_loop.py` (unadopted),
`tools/_harness.py` (credibility tools), and on `game-rpg`, `game/rpg/minds.py`. A fix to one
frequently misses the others — when changing engine-facing behavior, grep all of them.

Two differences that catch people out: the arena and the mind server use `choose_action()` but never
`deliberate()`, and every game surface hard-codes `AnthropicLLM`, so a `local/<name>` actor works only
through `tools/_harness.py`. A `local/<name>` judge works everywhere on `credibility-demo`.

## Operational: restart the live server after a server-side fix

Code edits do **not** hot-reload a running server. `game.server` is one process on port 8001 hosting
the text game, arena, and mind server; `game.server_lan` is the same on all interfaces. After any
server-side change, kill the running process and restart it (`Start-Process` detached) before testing
— otherwise you're testing stale code. (This cost a debugging cycle once: a "didn't work" report was
the live server running the pre-fix build.)

## Architecture reminder

Everything external sits behind an adapter (`orchestrator/adapters/base.py`).
Keep provider specifics in the adapters. The mind's orchestration lives in `engine.py`, its judge
seat in `judgment.py`, and the port 8000 voice loop in `pipeline.py`.
The engine is **front-end-agnostic** — the text game, arena, Godot RPG, and the frozen Unity and
Unreal clients all drive the same engine; keep world/presentation concerns in the game/client layer,
never in the engine core.
