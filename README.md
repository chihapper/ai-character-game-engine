# Real-Time AI Character Engine

A cloud-first, provider-agnostic engine for **real-time spoken conversation** with an
AI character. You speak; a character with a distinct personality and a **cloned
voice** answers out loud, in real time, and **remembers** past conversations.

It runs locally as a web app: a Python backend serving a browser UI on `localhost`.

> This is the foundation for a future multi-character "dialogue-driven game." v1 is
> the full voice-to-voice loop plus in-app character creation — the game itself is
> out of scope.

---

## The one thing that matters: streaming overlap

The character starts speaking **~1 second after you stop talking**. That only works
because the pipeline stages *overlap* instead of running end-to-end:

```
You stop talking
      │
      ▼
  STT (Whisper)  ──►  transcript
                          │
                          ▼
                    LLM (Claude, streaming)  ──► "Oh, you're back." ──► "I wondered…" ──► …
                                                        │                      │
                                            sentence 1 ready              sentence 2 ready
                                                        │                      │
                                                        ▼                      ▼
                                                  TTS sentence 1   ║    TTS sentence 2   (overlapping)
                                                        │                      │
                                                        ▼                      ▼
                                         🔊 you hear sentence 1  while  sentence 2 is still being made
```

As the LLM streams tokens, [`sentence_chunker.py`](orchestrator/sentence_chunker.py)
splits them into sentences on the fly. The moment sentence 1 is complete it's sent to
TTS and audio streams back to the browser — **while the LLM is still generating the
rest**. We never wait for the full reply before starting speech, and never wait for a
full audio render before playback.

Every stage is timed (VAD stop → transcript → LLM first token → first audio chunk →
playback) and the **latency panel** in the UI makes the budget visible.

---

## Architecture

```
mic (browser) → STT → Orchestrator → LLM → sentence chunker → TTS → audio (browser)
                                  ↕
                          two-tier memory
```

Every external provider sits behind an **adapter interface**
([`adapters/base.py`](orchestrator/adapters/base.py)). The pipeline depends only on
the interfaces — never on a specific provider. That swappability is the architectural
spine:

| Role | Interface | Default implementation | Swap to |
| --- | --- | --- | --- |
| Speech-to-text | `STTAdapter` | `WhisperSTT` (faster-whisper + Silero VAD, local) | any `STTAdapter` |
| LLM | `LLMAdapter` | `AnthropicLLM` (`claude-haiku-4-5`, streaming) | any `LLMAdapter` |
| Text-to-speech | `TTSAdapter` | `InworldTTS` (default) / `CartesiaTTS` | per-character via YAML |

- **Swapping the TTS provider** is a one-line change in a character's YAML
  (`tts_provider: inworld` → `cartesia`) — no code changes.
- **Swapping the LLM** is a one-file adapter change.

Memory is two-tier: a **short-term** rolling buffer of recent turns
([`memory/short_term.py`](orchestrator/memory/short_term.py)) plus **long-term** vector
recall in a local ChromaDB, embedded with a local sentence-transformers model
([`memory/long_term.py`](orchestrator/memory/long_term.py)). Each completed exchange is
embedded and stored; each new turn retrieves the top-k relevant past exchanges and
injects them into the prompt — so the character remembers you across sessions.

---

## Prerequisites

- **Python 3.10+**
- A microphone and a modern browser (Chrome/Edge/Firefox/Safari)
- API keys:
  - **Anthropic** — the LLM. Get one at <https://console.anthropic.com/>.
  - **Inworld** — default TTS + voice cloning. From the
    [Inworld portal](https://platform.inworld.ai/): API Keys → copy the **"Basic
    (Base64)" signature** and paste it verbatim (it's already base64-encoded — do not
    re-encode it).
  - **Cartesia** *(optional)* — alternative TTS, for A/B testing on the same cloned
    voice. Key format `sk_car_...` from <https://play.cartesia.ai/keys>.

You only need the keys for the providers you actually use. The text-first vertical
slice needs **Anthropic + Inworld** (or Cartesia).

---

## Setup & run

```bash
git clone <this-repo>
cd "Real-Time AI Character Engine"

cp .env.example .env        # then edit .env and paste your keys
```

Then launch with the single command for your OS:

**macOS / Linux**
```bash
./run.sh
```

**Windows (PowerShell)**
```powershell
./run.ps1
```

The launch script creates a virtualenv, installs dependencies, and starts the server.
Open **<http://127.0.0.1:8000>**.

> First run downloads the local Whisper and embedding models (a few hundred MB) and is
> slower to start. Subsequent runs are fast.

### Manual run (if you prefer)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m orchestrator.main
```

---

## Using it

**Conversation view**
1. Pick a character (the sample **Aria** ships with the repo) and click **Connect**.
   She greets you in her voice.
2. Click **Hold to talk**, speak, click again to stop. ~1s later she replies out loud.
   You can also type in the text box (handy for the text-first slice / quick testing).
3. Watch the **latency panel** — "First audio N ms after you stopped talking" is the
   headline number, and you can see the first audio chunk leave before the full reply
   is generated.

**Create Character view**
1. Enter a name, a personality (system prompt), and a greeting.
2. Either **record a ~12s voice sample** (it gets instant-cloned by the selected
   provider) **or** paste a preset `voice_id` (e.g. `Ashley` for Inworld).
3. Click **Create**, switch back to Conversation, **Refresh**, and talk to your new
   character in its own cloned voice.

> **Consent:** voice cloning requires that the recorded sample is your own voice or a
> consenting party's — both providers' terms require this.

---

## Character profiles

One YAML per character in [`orchestrator/characters/`](orchestrator/characters), written
by the Create Character flow (or hand-authored):

```yaml
name: "Aria"
system_prompt: |
  You are Aria, a sharp-witted archivist who speaks in clipped, dry sentences.
  [personality, speaking style, what they know, boundaries, how they treat the user]
tts_provider: inworld          # or: cartesia  — changes the voice provider, no code
voice_id: "Ashley"             # preset, or a clone id from the Create Character flow
greeting: "Oh — you're back. I wondered when you'd show up."
memory_namespace: "aria"       # isolates this character's long-term memory
```

To A/B Inworld vs Cartesia on the **same** cloned voice: clone the voice on both
providers (Create Character once per provider, or `tools/clone_voice.py`), then flip
`tts_provider` between two YAMLs.

---

## Configuration

All settings live in [`orchestrator/config.py`](orchestrator/config.py) and can be
overridden in `.env`:

| Setting | Default | Notes |
| --- | --- | --- |
| `LLM_MODEL` | `claude-haiku-4-5` | Fast model for snappy dialogue. Swap to `claude-sonnet-4-6` for richer personality at some latency cost. |
| `DEFAULT_TTS_PROVIDER` | `inworld` | Fallback provider when a character YAML doesn't specify one. |
| `WHISPER_MODEL` | `base.en` | faster-whisper size; larger = more accurate, slower. |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | |

The audio wire format (PCM s16le, mono, 24 kHz) is fixed in `config.py` so the browser
playback path is identical regardless of which TTS provider is active.

---

## Project structure

```
orchestrator/
  main.py            FastAPI app: serves the UI, character REST API, voice WebSocket
  pipeline.py        streaming STT→LLM→sentence-chunk→TTS loop (the overlap) + latency
  config.py          settings + env loading
  sentence_chunker.py
  latency.py         per-stage latency instrumentation
  character_store.py load / list / save character YAML
  adapters/
    base.py          STTAdapter, LLMAdapter, TTSAdapter (the interfaces)
    stt_whisper.py   faster-whisper + Silero VAD
    llm_anthropic.py Anthropic Messages API, streaming
    tts_inworld.py   Inworld streaming TTS + instant clone
    tts_cartesia.py  Cartesia WebSocket TTS + instant clone
    _audio.py        shared PCM helper
  memory/
    short_term.py    rolling buffer of recent turns
    long_term.py     ChromaDB + sentence-transformers vector recall
  characters/        character profiles (YAML)
web/
  index.html         Conversation + Create Character views
  app.js             WebSocket client + streaming PCM playback + mic capture
tools/
  clone_voice.py     CLI fallback for cloning
```

## How it maps to the build order

1. **Text-first vertical slice** — type → `AnthropicLLM` → chunker → `InworldTTS` →
   audio in the browser, overlap working. (Use the text box in the Conversation view.)
2. **Voice input** — `WhisperSTT` + Silero VAD + browser mic → full voice-to-voice.
3. **In-app character creation + cloning** — the Create Character view.
4. **Memory** — short-term buffer, then ChromaDB long-term recall across sessions.
5. **Second TTS adapter** — `CartesiaTTS` behind the same interface, selectable by config.
6. **Polish** — latency readout, this README, graceful API-error/WS handling.

---

## Troubleshooting

- **"Could not start session" on connect** — a required key is missing or wrong. Check
  `.env`. The Inworld key must be the portal's Base64 signature, pasted verbatim.
- **No audio plays** — browsers block audio until a user gesture; the AudioContext is
  created when you click **Connect**, so connect before expecting sound. Check the OS
  output device and tab volume.
- **Mic does nothing** — the page must be `localhost`/`127.0.0.1` (or HTTPS) for
  `getUserMedia`. Grant the mic permission when prompted.
- **First start is slow** — Whisper + embedding models download once and cache locally.
- **Transcription is rough** — bump `WHISPER_MODEL` (e.g. `small.en`) in `.env`.

---

## Out of scope for v1

Game integration, authentication, cloud hosting/deployment, packaging to a distributable
`.exe`. Character creation is intentionally minimal (create, save, select) — profile
editing, voice re-takes, avatars, and a browsable library come later.
