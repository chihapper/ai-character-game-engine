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

## Architecture reminder

Everything external sits behind an adapter (`orchestrator/adapters/base.py`).
Keep provider specifics in the adapters; orchestration lives in `pipeline.py`.
