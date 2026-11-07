# EVI + Custom Language Model (CLM) spike — runbook

> **Status (2026-11-07):** Frozen record, and the decision is closed: **EVI was ruled out on
> 2026-07-05/06.** The spike ran on those dates and this runbook hasn't changed since. This note is
> the repo's record of the verdict; GitHub issue #43 has the same detail. For the current voice
> setup, read the [README](../README.md#voice).
>
> Why EVI lost:
>
> - **It strips authored delivery.** A custom LLM can only return plain text, so the per-utterance
>   Octave acting `description` has no way through. The live test came back "100% real but flat",
>   and the laugh was never audible. That fails Q1.
> - **It forbids a prompt with a custom LLM.** Hume's API returns
>   `403 "Prompt use is not supported with CUSTOM_LANGUAGE_MODEL"`, so the EVI config can't carry
>   delivery direction either.
> - **EVI's own LLM abandons the engine.** Using it would restore delivery but lose relevance
>   realization, memory, relationship, and deliberation.
>
> Q2 (latency) has no end-to-end figure on record. The only number is the ~3.6s engine time from the
> self-test.
>
> The project kept Hume Octave as its chosen voice. Detecting the player's laughs and tone is now a
> separate problem: issue #43 plans a non-Hume `ProsodyAdapter`, deferred until a Godot voice-in path
> exists. Hume's standalone Expression Measurement API isn't an option, because it returned 403
> "discontinued" (`53fb3b7`).
>
> If you run this anyway: `spikes/evi_clm_server.py` has no authentication and binds all network
> interfaces (`0.0.0.0:8010`). It exists on `main` and `credibility-demo`; `game-rpg` deleted it in
> `e3cbf61`.

**Purpose (decision gate).** Decide whether to use Hume **EVI** for the voice loop
*without* changing the current demo. EVI would own the "room" (mic → ASR →
turn-taking/barge-in → prosody & vocal-burst measurement → Octave TTS) while our
**engine stays the brain** via EVI's Custom Language Model (EVI calls our
OpenAI-compatible `/chat/completions` over a socket). Two questions to answer:

- **Q1 — Voice quality.** A CLM returns plain TEXT, so we can't hand Octave the
  per-utterance acting `description` / `trailing_silence` we author in the modular
  pipeline. Does EVI's own speech-language model render our characters' bare
  dialogue *well enough*? (Listening judgment — needs a human.)
- **Q2 — Latency.** Is `user-stops-speaking → first audio` acceptable through
  EVI → our engine → back?

Everything here is isolated: separate server, separate port (`:8010`), separate
tunnel. It imports nothing from `game/server*`, so the live demo on `:8001` is
untouched.

```
   ┌───────────── EVI owns "the room" ─────────────┐
mic → ASR + prosody/vocal-burst measure → turn-taking/barge-in
                     │  (WebSocket, OpenAI /chat/completions SSE)
                     ▼
        spikes/evi_clm_server.py  = OUR ENGINE (Claude, RR, memory)
                     │  returns SPOKEN-ONLY text (stage business stripped)
                     ▼
        EVI renders it with Octave (voice from the config) → 🔊
```

## Run

1. **Start the CLM server** (this repo root; the spike branch `evi-clm-spike` no longer exists,
   and its commits are in `main` history):
   ```
   .venv/Scripts/python.exe -m spikes.evi_clm_server        # binds 0.0.0.0:8010
   ```
   Env overrides: `EVI_SPIKE_SLUG` (default `brielle-bri-castellano`),
   `EVI_SPIKE_MODEL` (default `claude-haiku-4-5`), `EVI_SPIKE_PORT` (default 8010).
   Every incoming EVI payload is logged verbatim to
   `spikes/evi_clm_requests.jsonl` — this is how we learn EVI's real
   emotional-context format (see "Open format question" below).

2. **Tunnel :8010** (separate from the demo tunnel on :8001):
   ```
   tools/cloudflared.exe tunnel --url http://127.0.0.1:8010
   ```
   Note the `https://<name>.trycloudflare.com` URL. The CLM URL EVI needs is that
   URL **+ `/chat/completions`**.

3. **Create an EVI config** (one-time, on the Hume account):
   - Hume portal → EVI → Configs → new config.
   - LLM: choose **Custom language model**, URL = `https://<tunnel>/chat/completions`
     (SSE / OpenAI-compatible).
   - Voice: **Octave**, voice = `Expressive Girl` (that's Bri's voice in
     `game/casting.py:HUME_VOICES`), so the test matches the demo's voice.
   - (Or via the create-config API with the same key — dashboard is simpler.)

4. **Talk to EVI + measure.** Use the Hume portal's "Talk to EVI" with that config
   (or a minimal EVI web-widget page). Speak a few lines to Bri — include an
   audible laugh/sigh and a raised voice to exercise the prosody/vocal-burst path.

## Decision criteria

- **Q1 PASS** if Bri sounds as in-character and expressive as the current demo's
  directly-authored Octave delivery — i.e. we don't materially miss the
  per-utterance acting descriptions. FAIL if she's flatter / generic.
- **Q2 PASS** if first-audio latency feels conversational (rough bar: ≲1.5s after
  you stop speaking). The engine generate time alone was ~3.6s on Haiku in the
  self-test **because `respond()` returns the whole reply before we stream** — so
  a PASS almost certainly requires wiring engine **token streaming** into the CLM
  (forward LLM deltas instead of the finished string). Treat that as the main
  build cost if we adopt EVI.
- **Bonus:** confirm the user's laugh/heightened voice actually shows up in the
  logged payload — that's the nonverbal-cue feature working end-to-end.

## Open format question (answered empirically)

Hume's CLM guide (paywalled/404 to the doc fetch) says the endpoint is
OpenAI-`/chat/completions`-compatible SSE and that EVI sends "conversation history
and emotional context". The EXACT shape of that emotional context (in the messages?
a side field? prosody scores? vocal-burst labels?) we read straight off
`spikes/evi_clm_requests.jsonl` after the first real call, then parse it into a
`Situation`/`remember()` signal for the engine.

## What needed the user (done; the outcome is in the status note)

- **Confirm EVI is enabled on the Hume plan** — Octave TTS access (what the demo
  uses) does NOT imply EVI access; EVI may need enabling/billing.
- **The listening test itself** (Q1) is a human judgment — you talk to Bri via EVI
  and tell me if the voice holds up.
- Everything else (server, tunnel, reading the payloads, wiring token-streaming if
  we proceed) is on me.
