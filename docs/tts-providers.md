# TTS providers — pick your voice, bring your own key

Goal: a user chooses a TTS provider, enters their own API key, and the engine **prompts correctly
for that provider** and speaks. Inworld and Hume are verified and ship **ready**; the rest are
listed **coming soon** until verified against their live docs.

## The two provider-keyed seams

The engine keeps "how to write for a provider" separate from "how to send it" — both keyed to the
provider, both selected per character (`character.tts_provider`):

1. **Prompting** — `VoiceProfile` (one subclass per provider, `orchestrator/expressivity.py`).
   `directive()` is the how-to-perform text injected into the LLM's system prompt
   (`performance_directive(provider)` → `context.py`), and `render_tags(text, provider)` renders or
   drops the model's markup for that provider. This is what makes *pick Inworld → prompt for
   Inworld; switch to Hume → prompt for Hume* correct. **Each provider's directive must be verified
   against that provider's live docs** (CLAUDE.md rule) — that verification is the gate for `ready`.
2. **Transport** — `TTSAdapter` (one subclass per provider, `orchestrator/adapters/tts_*.py`).
   Owns the provider's API request shape; yields PCM at `config.AUDIO_SAMPLE_RATE`.

## The registry — single source of truth

`orchestrator/tts_providers.py` ties the two seams together with everything a BYO-key picker needs:

```python
TTSProviderInfo(name, display_name, status, key_env, caps, make, notes)
#   status   = "ready" | "coming_soon"        (gates the picker; only verified providers are ready)
#   key_env  = required API-key env var(s)     (settings field == env name lowercased)
#   caps     = TTSCaps(streaming, batch, continuation, voice_clone, instant_mode, local)
#   make     = lazy adapter factory
```

Behavior branches on **declared capabilities, not provider names** — e.g. the pipeline batches
same-tone sentences when `caps(provider).batch` is true (Inworld), instead of the old
`provider == "inworld"` string-check. Adding a provider is **one registry entry** (+ its adapter
file + its `VoiceProfile`); nothing else in the codebase needs to change.

### Public API
- `list_providers()` / `ready_providers()` — the picker (ready first, then coming-soon).
- `make_tts(name)` — the adapter (unknown name → the default provider, never a crash).
- `caps(name)` — capability flags for behavior branching.
- `get_provider(name).missing_keys()` / `.has_keys()` — what to prompt the user for.
- `set_provider_key(name, key)` — inject a user's key at runtime (sets the env var, refreshes the
  cached settings). Persisting/securing the key is the caller's concern.
- `await validate_provider_key(name)` — cheap live check (synthesize one word) → `(ok, detail)`.
- REST: `GET /api/tts/providers` returns the picker payload (status, required keys, has_keys, caps).

## Adding / promoting a provider
1. Write `orchestrator/adapters/tts_<name>.py` (a `TTSAdapter`) and a `VoiceProfile` in
   `expressivity.py`, **following that provider's live API docs**.
2. Add one `TTSProviderInfo` to the registry with `status="coming_soon"` and its `caps`.
3. Verify end-to-end (directive produces markup the provider performs; adapter speaks it; no markup
   read aloud). Only then flip `status="ready"`.

## Status
- **ready:** Inworld, Hume.
- **coming_soon:** ElevenLabs, Cartesia, Fish, Chatterbox (self-hosted) — adapters exist, not yet
  verified against current docs.

*(The same registry pattern generalizes to STT and the LLM; only TTS is registry-backed today.)*
