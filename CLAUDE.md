# Project notes for coding agents

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

- **TTS = Hume Octave** (`orchestrator/adapters/tts_hume.py`), chosen after a bake-off
  (Inworld / ElevenLabs / Cartesia / Fish / Chatterbox / Hume). It's a normal provider
  behind the `TTSAdapter` seam — per-sentence utterances, per-utterance acting `description`,
  dynamic `trailing_silence`, cross-turn continuity via `context.generation_id`. Instant mode
  is OFF (quality mode; fp16 was flat on the dev GPU).
- **Face / lip-sync = PAUSED.** Audio→ARKit-blendshape lip-sync lives behind
  `FaceAnimAdapter`: NVIDIA **Audio2Face** (`faceanim_a2f.py`), replaced by self-hosted
  **NeuroSync** (`faceanim_neurosync.py`) once A2F needed Ampere+ hardware the 1080 Ti lacks.
  Wired through the mind server's `/speak_anim`. **Currently on pause** — front-end direction
  is under review (a 2D **Godot** game is being considered; the face layer may not resume).
  Don't treat NeuroSync/A2F as active work unless the user resumes it.
- An Inworld single-session **full-loop** runtime (`orchestrator/realtime/`) was spiked but
  **NOT adopted** — the modular pipeline was kept. See `docs/track-v-full-loop-plan.md`
  (marked superseded).

## Two engine drivers — fix BOTH paths

`game/runtime.py` (the text web demo) and `game/bridge/mind_api.py` (the mind server for
Unreal/Unity) are **two parallel drivers** of the same engine. A fix to one frequently
misses the other — when changing engine-facing behavior, grep both.

## Operational: restart the live server after a server-side fix

Code edits do **not** hot-reload the running `server_lan` / mind-server process. After any
server-side change, kill the running process and restart it (`Start-Process` detached) before
testing against the hosted URL — otherwise you're testing stale code. (This cost a debugging
cycle once: a "didn't work" report was the live server running the pre-fix build.)

## Architecture reminder

Everything external sits behind an adapter (`orchestrator/adapters/base.py`).
Keep provider specifics in the adapters; orchestration lives in `pipeline.py`.
The engine is **front-end-agnostic** — text demo, Unreal client, and any future 2D (Godot)
front-end all drive the same engine; keep world/presentation concerns in the game/client layer,
never in the engine core.
