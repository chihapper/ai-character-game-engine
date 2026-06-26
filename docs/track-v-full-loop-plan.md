# Track V — full-loop migration plan (scoping)

> Implementation plan for replacing the inherited modular pipeline with **Inworld's
> full-loop realtime agent**. Companion to [`architecture-seams.md`](architecture-seams.md)
> (which says *what* the architecture is and why); this says *how* we get `main` there.
> Status: **scoping** — no code yet. Several load-bearing details are unverified and
> explicitly gated behind a Phase-0 audio spike (§5); this plan does not assume Inworld
> audio specifics from memory.

## 1. Goal & success criteria

Replace the per-turn modular pipeline (STT adapter → Anthropic streaming → sentence
chunk → TTS adapter) with a single **Inworld Realtime session** that owns STT → LLM
(Claude) → TTS-2 with cross-turn voice continuity. Done when:

- A player holds-to-talk (or types) and hears the character reply **in its cloned/
  designed voice, with continuity across turns**, driven by one Inworld session.
- The character obeys `build_prompt()` (steering) and can run **tools** (dice/state).
- **Memory still works**: retrieval shapes the turn; each completed exchange is stored.
- First-audio latency is **measured** and within a turn of the current ~1s budget.
- The modular pipeline + STT/LLM/TTS adapters are removed from the live path.

## 2. Invariants to preserve (do not break these)

These are the contracts the migration must hold so blast radius stays server-side:

1. **The browser WS protocol is frozen.** The frontend already speaks: inbound control
   messages `ready` / `partial_transcript` / `transcript` / `assistant_delta` /
   `assistant_done` / `audio_start` / `audio_end` / `latency` / `error` / `info`, binary
   frames = **PCM s16le mono 24 kHz** for playback ([`app.js:16`](../web/app.js),
   `playPcmFrame`), and outbound mic = **PCM16 mono 16 kHz** binary frames + JSON
   `mic_start` / `mic_stop` / `text`. **The new session loop must emit/consume exactly
   these.** No frontend change is in scope. (This is the same discipline that already
   proxies AssemblyAI streaming entirely server-side.)
2. **24 kHz PCM wire format** ([`config.py:22`](../orchestrator/config.py)) — whatever
   Inworld emits, the backend resamples to this before `emit_audio`.
3. **Memory ownership stays in the engine** — `LongTermMemory` / `ShortTermMemory` are
   untouched (Track E owns their evolution).
4. **`build_prompt()` is the instruction source** — the session is steered by the same
   compiled character prompt, including `game_data` renderer sections.
5. **Voice cloning/design survives** — the create/edit flows and `tools/clone_voice.py`
   still mint the `voice_id` we set on the session.

## 3. What the spike already proved (and didn't)

From `realtime_fullloop_spike.py` (text-only, OpenAI-Realtime protocol over
`wss://api.inworld.ai/api/v1/realtime/session`, `Authorization: Basic <INWORLD_API_KEY>`):

- **Proven:** session steering via `session.update.instructions`; LLM routing to Claude
  via `session.update.model`; tool *definition* + the agent *emitting* a
  `function_call` with correct args; designed voice set via `audio.output.voice`.
- **Event shape known:** `response.output_text.delta`, `response.output_item.added`
  (function_call), `response.function_call_arguments.delta/done`, `response.done`
  (carries the LLM model in usage metadata).
- **NOT proven / open:** see §5. Chiefly — **no audio path was exercised at all**
  (`output_modalities=["text"]`), and **tool-result continuation returned no text**.

## 4. Target component: the realtime session integration

A new server-side module — proposed `orchestrator/realtime/inworld_session.py` — owns
one WS session's lifecycle. It is **not** a `TTSAdapter`; it's a conversation runtime
that supersedes the `Pipeline`. Shape:

```python
class InworldSession:
    async def connect(self, character, voice_id, tools) -> None      # session.update
    async def update_context(self, instructions) -> None             # per-turn re-steer (§5.6)
    async def send_text(self, text) -> None                          # typed input
    async def send_audio(self, pcm16_frame: bytes) -> None           # mic passthrough
    async def commit_user_turn(self) -> None                         # if manual turn mode
    def events(self) -> AsyncIterator[Event]                         # normalized events out
    async def close(self) -> None                                    # session teardown
```

`events()` normalizes Inworld's wire events into the engine's vocabulary so `main.py`
maps them straight onto the frozen browser protocol:

| Inworld event | Engine event | Browser message |
| --- | --- | --- |
| input STT partial | `partial_transcript` | `partial_transcript` |
| input STT final | `transcript` | `transcript` (+ memory write key) |
| `response.output_text.delta` | `assistant_delta` | `assistant_delta` |
| output audio chunk | `audio` (resampled→24k) | binary PCM frame (+ `audio_start` once) |
| `response.output_item.added`=function_call | `tool_call` | (handled server-side) |
| `response.done` | `assistant_done` | `assistant_done` + `audio_end` + `latency` |

## 5. Open problems — each resolved by Phase 0 before any cutover

These are the risks. None are believed fatal (the spike de-risked viability), but each
needs a verified answer, not a guess.

**5.1 Output audio format & sample rate.** What encoding/rate does the Realtime session
emit (PCM16? what Hz? framed how)? → Resolve by turning on `output_modalities=["audio"]`
in a spike, capturing frames, and confirming the resample-to-24k path. The HTTP
`inworld-tts-2` adapter already yields 24 kHz PCM, so parity is plausible but must be
verified on the *Realtime* surface.

**5.2 Input audio format for STT.** Does the session accept the browser's 16 kHz PCM16
via `input_audio_buffer.append` (+ `.commit`), and what rate/encoding does it want? →
Spike: stream a known clip, confirm transcription.

**5.3 Turn-taking & barge-in.** Server-side VAD (automatic) vs manual
(`response.create`)? Does the session interrupt playback when the user speaks over it?
→ Decide based on spike behavior; the frozen browser protocol already has `mic_start`/
`mic_stop`, so map those to whichever mode we pick. Barge-in needs an interrupt → send a
`reset` to the PCM player.

**5.4 Tool-result continuation (the known TODO).** Returning `function_call_output`
produced no follow-on text in the spike — likely a `call_id` format detail. → Resolve in
a focused tool round-trip spike; this blocks game mechanics.

**5.5 Exact Anthropic model id.** Spike routed to `anthropic/claude-sonnet-4-6`;
confirm Inworld accepts it and which ids are available (and whether Haiku is selectable
for the latency lever). → Read it back from `response.done` usage metadata.

**5.6 Per-turn context injection (the Track E plug point).** The session sets
`instructions` once, but the engine composes instructions **per turn** (retrieved
memories + the game's `Situation`). Two options:
- (a) `session.update` the `instructions` before each `response.create`, or
- (b) inject retrieved memories + situation as a context message in the conversation.

→ This decision is where Track E meets Track V; pick the one that re-steers reliably
without resetting voice continuity. Verify in the spike.

**5.7 Latency.** Measure VAD-stop → first-audio under the full loop and compare to the
current budget; the `LatencyTracker` marks port over.

## 5R. Phase-0 spike results (2026-06-25)

Ran `realtime_audio_spike.py` (gitignored) against the live Inworld Realtime API with a
SAPI-synthesized 16 kHz clip (the real browser mic format), resampled to 24 kHz.

**GREEN — resolved:**
- **5.1 Output audio.** Carried as `response.output_audio.delta` (base64 PCM16 in the
  `.delta` field); session echoes output format **`audio/pcm @ 24000`** — *our 24 kHz
  wire format exactly*, so Inworld frames forward to the browser with **no resample**.
- **5.2 Input STT.** Works; verbatim-accurate transcript via
  `conversation.item.input_audio_transcription.completed`. Input format is
  **`audio/pcm @ 24000`**, so the browser's 16 kHz mic is resampled **server-side**
  (cheap; we already do this elsewhere).
- **5.3 Turn-taking.** `turn_detection: semantic_vad` (`create_response:true`) is
  default-**on** and races a manual commit → empty response. Setting
  `audio.input.turn_detection: null` gives deterministic manual turns
  (append → commit → `response.create`), matching our `mic_start`/`mic_stop`. Use manual
  for v1; revisit server-VAD/barge-in later.
- **5.5 Model.** `anthropic/claude-sonnet-4-6` confirmed via `response.done` usage.

**RED — must clear before Phase 1:**
- **5.7 Latency ≈ 4.0 s to first audio** on a ~72-word reply (manual turns). Well over
  the ~1 s budget — the top risk. Audio *does* stream (65 deltas), so investigate TTS
  TTFB, stricter brevity, and whether the voice/model fallback (below) inflates it.
- **NEW — voice not applied (HIGH).** Sent `audio.output.{voice=<char design id>,
  model=inworld-tts-2}`; the session silently fell back to **`voice: Olivia,
  model: inworld-tts-1.5-mini`**. The character's designed voice never loaded — resolve
  the Realtime voice/model schema (and whether designed voices need publishing or a
  tts-2-compatible id). Blocks "the character speaks in its own voice."
- **5.4 — tool CALL works, CONTINUATION broken (BLOCKER).** The model emits `roll_dice`
  with correct args, but returning `function_call_output` (call_id `toolu_…`) yields an
  **empty** response — no text, no audio. Reproduces the text-spike TODO; not
  audio-specific. Blocks game mechanics. Needs Inworld's continuation contract
  (likely a call-id / output-format detail) — **fetch the docs, don't guess**.
- **NEW — stage directions get voiced (ARCHITECTURAL).** Even with `ENGINE_DIRECTION`
  forbidding asterisk actions, the model emitted `*a tray balanced…*` in the spoken
  transcript. The full loop couples LLM→TTS *inside* Inworld, so our
  `text_cleanup`/`expressivity` seam — which today strips this **between** LLM and TTS —
  has nowhere to live. Mitigation is prompt-only (shown unreliable here) unless Inworld
  TTS ignores the markup in the actual audio (needs a listen to confirm). A real cost of
  the coupled loop.

**Net:** the loop is viable end-to-end (voice in → Claude → voice out, with tool
*calls*). Four items gate Phase 1: voice wiring, tool continuation, latency, and
stage-direction leakage. Next step is **Inworld Realtime API docs** for the voice/model
and tool-continuation schemas (fetch, don't guess), then a targeted re-spike.

## 6. Memory integration (engine stays in charge)

Per logical turn, around the session:
- **Before** triggering the response: `long_term.retrieve(query)` + the game `Situation`
  → fold into instructions/context per §5.6.
- **On** input STT final: capture the user transcript (the memory write key).
- **On** `response.done`: accumulate the assistant text (from deltas, or an output
  transcript event if the audio path provides one) and write
  `short_term.add_*` + `long_term.add_exchange(user, assistant)`.

A logical "turn" boundary = input-final → matching `response.done`. This is the same
retrieve→generate→speak→remember shape as `Pipeline.run_turn`, minus our STT/TTS.

## 7. `main.py` cutover

The `/ws` handler keeps its structure (accept, per-session setup, turn loop, teardown)
but swaps the engine:

- **Setup:** instead of `AnthropicLLM` + `make_tts` + `Pipeline`, build an
  `InworldSession`, `connect()` it with `character`, `voice_id`, and the registered
  tools. Keep `ShortTermMemory` + `LongTermMemory`.
- **Greeting:** speak via the session (or keep the authored greeting as a primed
  assistant item).
- **Turn loop:** binary mic frames → `session.send_audio`; `text` message →
  `session.send_text`; a reader task pumps `session.events()` onto the frozen browser
  protocol (the §4 table) and drives the memory writes (§6).
- **Teardown:** `session.close()`.

`/ws/calibrate` is unaffected (it's its own AssemblyAI flow; keep or retire separately).

## 8. What gets removed vs kept

**Retire (once the session path is proven):**
[`pipeline.py`](../orchestrator/pipeline.py), [`sentence_chunker.py`](../orchestrator/sentence_chunker.py),
[`expressivity.py`](../orchestrator/expressivity.py), [`text_cleanup.py`](../orchestrator/text_cleanup.py),
[`timing.py`](../orchestrator/timing.py), the STT adapters
(`stt_whisper.py`, `stt_assemblyai.py`, `stt_assemblyai_stream.py`), `llm_anthropic.py`'s
streaming reply path, and the streaming/clone split in the TTS adapters.

**Keep:** `character_store.py` + `build_prompt()`, `character_extensions.py`,
`memory/*`, `character_draft.py`, the voice **clone/design** methods on the TTS adapters
(used by create/edit + `tools/clone_voice.py`), `config.py`, `latency.py`, the whole
`web/` frontend.

**Decide later:** `cadence.py` / `profile_store.py` / calibration exist to tune
AssemblyAI endpointing — moot if Inworld owns turn-taking. Likely retire with STT.

## 9. Config & keys

- `INWORLD_API_KEY` already present (Basic auth, verbatim base64 — see `CLAUDE.md`).
- Add: realtime model id (Claude), realtime audio output model/rate, turn-taking mode,
  realtime endpoint. Mirror the existing `Settings` pattern in `config.py`.
- `ANTHROPIC_API_KEY` is no longer on the live voice path (the LLM is billed/routed
  through Inworld) — but keep it: `character_draft.py` still calls Anthropic directly.

## 10. Phased delivery (de-risk audio first)

- **Phase 0 — audio-on spike.** Extend the existing spike: `output_modalities=["audio"]`,
  push a mic clip in, dump output audio + resolve every §5 item. **Gate:** all of §5
  answered. *No production code until this passes.*
- **Phase 1 — voice loop, happy path.** `InworldSession` + a `/ws` variant behind a
  feature flag (`VOICE_RUNTIME=inworld_fullloop`), text + mic in, audio out on the frozen
  protocol. Modular path stays default.
- **Phase 2 — tools + memory.** Tool round-trip end-to-end (§5.4); retrieve/remember
  wired (§6); per-turn context injection (§5.6).
- **Phase 3 — cutover.** Flip the flag default; delete the retired modules (§8).
- **Phase 4 — polish.** Latency readout under the loop, barge-in, error/reconnect
  handling, docs (fold the proven facts back into `architecture-seams.md`).

## 11. Risk & rollback

- **Feature-flag the runtime** (`VOICE_RUNTIME`) through Phases 1–3 so `main` keeps a
  working voice loop the entire time; the modular path is the rollback until Phase 3.
- **Biggest unknowns:** output-audio reconciliation (§5.1) and tool continuation (§5.4).
  Both are isolated to Phase 0 — if either can't be resolved against the live API, we
  stop and reassess *before* deleting anything.
- **Cost:** the audio spike bills TTS (text-only was the cheap probe). Keep Phase-0
  clips short.
