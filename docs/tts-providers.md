# TTS provider registry

`orchestrator/tts_providers.py` and this doc exist only on the `credibility-demo` branch. On `main`
and `game-rpg`, `make_tts()` in `orchestrator/main.py` is a plain `if` chain and the pipeline picks
batching by provider name.

The goal is a bring-your-own-key flow: a user chooses a TTS provider, enters their own API key, and
the engine prompts correctly for that provider and speaks. **That flow isn't built.** The registry
is a backend with no front end:

- `GET /api/tts/providers` exists, but nothing in the repo calls it.
- There's no key-entry screen, and no route accepts a user's key. Keys come from `.env`.
- The Create Character provider list is hard-coded to ElevenLabs, Inworld, and Cartesia
  (`web/index.html`), so Hume, Fish, and Chatterbox aren't offered there.
- Provider status isn't enforced (see [The registry](#the-registry)).

What the registry does today is build the adapters for the port 8000 app and the credibility tools, and tell the pipeline
whether to batch. The game surfaces don't use it.

## Which provider actually runs

| Where | What picks the provider | If unset |
| --- | --- | --- |
| Port 8000 app | `tts_provider` in the character's YAML | `DEFAULT_TTS_PROVIDER`, which defaults to `elevenlabs` |
| Game server and mind server | `GAME_TTS` in the environment | `inworld` |
| Ferry voice route (`POST /api/game/{gid}/voice`) | `GAME_TTS` | Returns 404 unless it's `hume` |

## The two provider-keyed seams

The engine keeps "how to write for a provider" separate from "how to send it". Both are keyed to the
provider, and on the port 8000 app both are selected per character (`character.tts_provider`).

1. **Prompting** — `VoiceProfile` (`orchestrator/expressivity.py`). Four subclasses exist: ElevenLabs,
   Inworld, Cartesia, and Hume. `profile_for()` falls back to Cartesia's, so Fish and Chatterbox
   silently get Cartesia's profile until each gains its own. A profile has two halves, and they
   reach different paths:
   - `directive()` is the how-to-perform text injected into the LLM's system prompt
     (`performance_directive(provider)` → `build_instructions()` in `context.py`). **It reaches the
     model only on the port 8000 pipeline and the full loop.** The pipeline passes the character's
     `tts_provider`, and the full loop always passes `inworld`. `Engine.respond()` passes no provider,
     so the game server, mind server, sandbox, and credibility tools get no provider prompt. On the
     game surfaces, `PERFORMANCE_RULES` in `game/policy.py` sets the writing style instead, and the
     adapter converts whatever comes out. Because no shipped character YAML selects Hume,
     `HumeProfile.directive()` runs in no shipped configuration.
   - `render_tags(text, provider)` renders or drops the model's markup for that provider. Each
     adapter calls it, so this half applies wherever an adapter does the speaking. On the full loop, Inworld's session voices replies with no adapter, so only the greeting passes through it.

   **Each provider's directive must be verified against that provider's live docs** before it's
   marked `ready`.
2. **Transport** — `TTSAdapter` (one subclass per provider, `orchestrator/adapters/tts_*.py`).
   Owns the provider's API request shape; yields PCM at `config.AUDIO_SAMPLE_RATE`.

## The registry

`orchestrator/tts_providers.py` ties the two seams together with everything a bring-your-own-key
picker would need:

```python
TTSProviderInfo(name, display_name, status, key_env, caps, make, notes)
#   status   = "ready" | "coming_soon"        (advisory; nothing enforces it)
#   key_env  = required API-key env var(s)     (settings field == env name lowercased)
#   caps     = TTSCaps(streaming, batch, continuation, voice_clone, instant_mode, local)
#   make     = lazy adapter factory
```

**Status is advisory.** `GET /api/tts/providers` reports it, but neither `make_tts()` nor the UI
checks it. `make_tts()` builds any provider, including `coming_soon` ones such as `elevenlabs`.

**Capabilities are mostly declarations so far.** Only `batch` changes behavior: the pipeline batches
same-tone sentences when `caps(provider).batch` is true (Inworld), instead of the old
`provider == "inworld"` string-check. Nothing reads the other flags yet, and provider-name branches
remain in `orchestrator/main.py` and `game/bridge/mind_api.py`.

Three declarations don't match the adapters. Chatterbox declares `streaming` but returns one whole
clip. Fish and Chatterbox implement `clone_voice()` but declare `voice_clone=False`.

### Public API
- `list_providers()` / `ready_providers()` — the providers in picker order (ready first, then
  coming-soon).
- `make_tts(name)` — the adapter. An unknown name falls back to the registry's own default,
  `inworld`, not to `DEFAULT_TTS_PROVIDER`. A known provider with no key raises the adapter's own
  "API key not set" error.
- `caps(name)` — capability flags for behavior branching.
- `get_provider(name).missing_keys()` / `.has_keys()` — what a key prompt would ask for.
- `set_provider_key(name, key)` — inject a user's key at runtime (sets the env var, refreshes the
  cached settings). Persisting/securing the key is the caller's concern. Only the tests call it.
- `await validate_provider_key(name)` — cheap live check (synthesize one word) → `(ok, detail)`.
  Nothing calls it yet.
- REST: `GET /api/tts/providers` on the port 8000 app returns the picker payload (name, display
  name, status, required keys, has_keys, capabilities, notes). No front end calls it.

## Adding / promoting a provider
1. Write `orchestrator/adapters/tts_<name>.py` (a `TTSAdapter`) and a `VoiceProfile` in
   `expressivity.py`, **following that provider's live API docs**.
2. Add one `TTSProviderInfo` to the registry with `status="coming_soon"` and its `caps`.
3. Update the places the registry doesn't drive:
   - the provider dropdown in `web/index.html` and `VOICE_MODES` in `web/app.js`
   - `_tts()` and `_adapter_named()` in `game/bridge/mind_api.py`
   - the voice routes in `orchestrator/main.py`
4. Verify end-to-end (directive produces markup the provider performs; adapter speaks it; no markup
   read aloud). Only then flip `status="ready"`.

## Hume specifics

Hume Octave won the TTS bake-off, but **no setting defaults to it** and no shipped character YAML
uses it. Only the credibility tools pick it, hard-coded as `make_tts("hume")`.

- **Turning it on.** For the game server, set `HUME_API_KEY` and `GAME_TTS=hume`. For the port 8000
  app, set `tts_provider: hume` and a Hume `voice_id` in the character's YAML by hand. `HUME_VOICES` isn't consulted there.
- **Known defect on the mind server.** On `main` and `credibility-demo`, its `voice_ready` check
  ignores `HUME_API_KEY`, so with no ElevenLabs key set, `/speak` and `/speak_anim` return 404. The
  fix exists only on `game-rpg` (`e3cbf61`).
- **Casting.** Game voices are cast in code, in `HUME_VOICES` in `game/casting.py`. The lookup order
  is the `HUME_VOICE_<SLUG>` env var, then that map, then `BAKEOFF_HUME_VOICE`, then `Ava Song`.
- **Voice ids.** `HUME_AI:<uuid or name>` is a Voice Library voice. `CUSTOM_VOICE:<uuid>` is a voice
  saved in your account. With no prefix, a bare UUID is a custom voice and anything else is a Voice
  Library name.
- **No in-app cloning.** `clone_voice()` raises `NotImplementedError`, and the registry declares
  `voice_clone=False`. Create the voice in Hume's own UI and use its id.
- **Version pin.** Every request sends `version: "1"`. Acting `description`s work on Octave 1 only
  (checked against Hume's docs on 2026-07-09). With no version, Hume picks the model itself, which
  could silently drop all the acting. Keep the pin until Octave 2 supports descriptions.
- **How acting reaches the voice.** The adapter splits a reply into per-sentence utterances and
  turns leading `[tags]`, `*stage directions*`, and narration around quoted speech into each
  utterance's `description`, 100 characters at most. That needs the whole raw reply, so it works on
  the `Engine` paths. On the port 8000 pipeline, `clean_for_speech` removes the asterisks but keeps
  the words, and the adapter gets one sentence at a time, so `*leans in*` would be spoken. That path
  relies on the Hume directive instead, which asks for leading bracket tags and no physical actions.
- **Continuity.** Prosody carries across turns through `context.generation_id`, held per adapter
  instance for 300 seconds. Reuse one `HumeTTS` per session, or continuity stops.
  `reset_continuation()` clears it for a new scene.
- **Instant mode stays off.** `HUME_INSTANT` defaults to false because instant mode narrowed the
  acting range: 1.54x with it on against 1.85x with it off, on the streaming endpoint (commit
  `ff1d853`).
- **Dependency.** The adapter imports `numpy`, which no requirements file lists. `fastembed` brings
  it in, so install `requirements-optional.txt`.

## Status
- **ready:** Inworld, Hume. Both were marked ready when the registry landed on 2026-07-08. Neither
  has been rechecked against live docs since July.
- **coming_soon:** ElevenLabs, Cartesia, Fish, Chatterbox (self-hosted) — adapters exist, not yet
  verified against current docs. The label doesn't stop them running. ElevenLabs is the default for
  `DEFAULT_TTS_PROVIDER`, and one shipped character uses it. Cartesia is the outage fallback on the
  port 8000 voice path whenever `CARTESIA_API_KEY` is set.

*(The same registry pattern generalizes to STT and the LLM; only TTS is registry-backed today.)*
