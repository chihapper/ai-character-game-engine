"""FastAPI app: serves the frontend, the character REST API, and the voice WebSocket.

Routes
------
GET  /                      -> Conversation + Create Character UI (static)
GET  /api/characters        -> list characters
POST /api/characters        -> create a character (+ optional voice cloning)
WS   /ws?character=<slug>    -> the real-time voice loop for one session

The WebSocket carries two kinds of frames:
  * text frames  = JSON control messages (both directions)
  * binary frames = raw PCM audio (server->browser) / recorded clip (browser->server)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import replace

from fastapi import (
    FastAPI,
    File,
    Form,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .adapters.base import TTSAdapter
from .adapters.llm_anthropic import AnthropicLLM
from .adapters.stt_assemblyai_stream import AssemblyAIStream
from .adapters.tts_cartesia import CartesiaTTS
from .adapters.tts_elevenlabs import ElevenLabsTTS
from .adapters.tts_fallback import FallbackTTS
from .adapters.tts_inworld import InworldTTS
from .profile_store import (
    Profile,
    delete_profile,
    list_profiles,
    load_profile,
    save_profile,
)
from .profile_store import slugify as profile_slugify
from .character_draft import draft_card_from_concept, draft_voice_description
from .character_store import (
    Character,
    delete_character,
    list_characters,
    load_character,
    save_character,
    slugify,
)
from .config import (
    ALLOWED_DELIVERY_MODES,
    ALLOWED_MODEL_IDS,
    ALLOWED_REALTIME_MODEL_IDS,
    AVAILABLE_MODELS,
    DELIVERY_MODES,
    REALTIME_MODELS,
    WEB_DIR,
    get_settings,
)
from .context import RespondRequest, Situation
from .latency import LatencyTracker
from .memory.long_term import LongTermMemory
from .memory.short_term import ShortTermMemory
from .pipeline import Pipeline
from .legacy_voice import get_stt, router as legacy_voice_router
from .realtime.full_loop import _handle_remember, run_full_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("orchestrator")

app = FastAPI(title="Real-Time AI Character Engine")
app.include_router(legacy_voice_router)  # RETIRING voice machinery (see legacy_voice.py)


@app.on_event("startup")
async def _warm_memory_embedder() -> None:
    """Pre-warm the long-term-memory embedder so turn 1 doesn't eat the ~0.5s cold load."""
    from .memory.long_term import warm_embedder

    try:
        name = await asyncio.to_thread(warm_embedder)
        logger.info("Embedder pre-warmed at startup: %s", name)
    except Exception as exc:  # never block startup on a warm failure
        logger.warning("Embedder pre-warm skipped: %s", exc)


@app.middleware("http")
async def no_cache_frontend(request, call_next):
    """Serve the frontend with no-cache so edits always take effect on refresh —
    no more 'did you hard-refresh?' confusion during development."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".html", ".css")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


# --------------------------------------------------------------------- factories


def make_tts(provider: str) -> TTSAdapter:
    """Construct the TTS adapter for `provider`. Thin wrapper over the provider registry
    (orchestrator/tts_providers.py) — the single source of truth for adapter/profile/keys/caps."""
    from orchestrator.tts_providers import make_tts as _registry_make_tts
    return _registry_make_tts(provider)


@app.get("/api/tts/providers")
async def get_tts_providers() -> JSONResponse:
    """The TTS pick-list for a 'bring-your-own-key, choose-your-voice' UI: ready providers first,
    each with the API-key env var(s) it needs, whether those are present, and its capabilities.
    'coming_soon' providers have adapters but aren't yet verified against their live docs."""
    from orchestrator.tts_providers import list_providers
    return JSONResponse([p.public_dict() for p in list_providers()])


# ------------------------------------------------------------------- REST: chars


@app.get("/api/characters")
async def get_characters() -> JSONResponse:
    return JSONResponse([c.public_dict() for c in list_characters()])


@app.get("/api/characters/{slug}/full")
async def get_character_full(slug: str) -> JSONResponse:
    """All editable fields for one character (the list endpoint omits the detail)."""
    try:
        c = load_character(slug)
    except FileNotFoundError:
        return JSONResponse({"error": "Character not found."}, status_code=404)
    return JSONResponse(
        {
            "slug": c.slug,
            "name": c.name,
            "greeting": c.greeting,
            "tts_provider": c.tts_provider,
            "voice_id": c.voice_id,
            "concept": c.concept,
            "age": c.age,
            "role": c.role,
            "pronouns": c.pronouns,
            "temperament": c.temperament,
            "speech_style": c.speech_style,
            "backstory": c.backstory,
            "knows": c.knows,
            "doesnt_know": c.doesnt_know,
            "goals": c.goals,
            "secrets": c.secrets,
            "boundaries": c.boundaries,
            "relationships": c.relationships,
            "disposition": c.disposition,
            "sample_lines": c.sample_lines,
            "game_data": c.game_data,
            "system_prompt": c.system_prompt,
        }
    )


@app.get("/api/models")
async def get_models() -> JSONResponse:
    """Selectable LLMs for the UI dropdowns. `models`/`default` drive the draft picker (and
    the modular conversation model); `realtime_models`/`realtime_default` drive the full-loop
    conversation model. `runtime` tells the frontend which list the conversation dropdown uses."""
    s = get_settings()
    return JSONResponse({
        "models": AVAILABLE_MODELS,
        "default": s.llm_model,
        "realtime_models": REALTIME_MODELS,
        "realtime_default": s.realtime_llm_model,
        "delivery_modes": DELIVERY_MODES,
        "delivery_default": s.realtime_delivery_mode,
        "runtime": s.voice_runtime,
    })


@app.get("/api/profiles")
async def get_profiles() -> JSONResponse:
    """Saved speaker cadence profiles (for the conversation dropdown)."""
    return JSONResponse([p.public_dict() for p in list_profiles()])


@app.post("/api/profiles")
async def create_profile(request: Request) -> JSONResponse:
    """Save a calibration result (min/max turn silence + stats) under a name."""
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "A profile name is required."}, status_code=400)
    try:
        prof = Profile(
            slug=profile_slugify(name),
            name=name,
            min_turn_silence=int(data["min_turn_silence"]),
            max_turn_silence=int(data["max_turn_silence"]),
            stats=data.get("stats", {}) or {},
        )
    except (KeyError, ValueError, TypeError):
        return JSONResponse(
            {"error": "min_turn_silence and max_turn_silence are required."},
            status_code=400,
        )
    save_profile(prof)
    return JSONResponse(prof.public_dict(), status_code=201)


@app.delete("/api/profiles/{slug}")
async def remove_profile(slug: str) -> JSONResponse:
    return JSONResponse({"deleted": delete_profile(slug)})


_DEFAULT_PREVIEW_TEXT = (
    "Hello there. Sit down and rest a while — you look like you've come a long way, "
    "and the road only gets colder from here."
)


@app.get("/api/voices")
async def list_library_voices(
    provider: str = "cartesia",
    gender: str = "",
    q: str = "",
) -> JSONResponse:
    """Browse a provider's voices so the user can pick + preview one. Cartesia and
    ElevenLabs are browsable; Inworld has no comparable browse (it uses design or a
    named preset id)."""
    settings = get_settings()
    if provider == "elevenlabs":
        if not settings.elevenlabs_api_key:
            return JSONResponse({"error": "ELEVENLABS_API_KEY is not set."}, status_code=400)
        try:
            voices = await ElevenLabsTTS().list_voices(gender=gender or None, q=q or None)
        except Exception as exc:
            logger.exception("Listing ElevenLabs voices failed")
            return JSONResponse({"error": f"Couldn't load voices: {exc}"}, status_code=502)
        return JSONResponse({"voices": voices})
    if provider != "cartesia":
        return JSONResponse(
            {"voices": [], "error": "Library browsing isn't available for this provider."}
        )
    if not settings.cartesia_api_key:
        return JSONResponse({"error": "CARTESIA_API_KEY is not set."}, status_code=400)
    try:
        voices = await CartesiaTTS().list_voices(gender=gender or None, q=q or None)
    except Exception as exc:
        logger.exception("Listing Cartesia voices failed")
        return JSONResponse({"error": f"Couldn't load voices: {exc}"}, status_code=502)
    return JSONResponse({"voices": voices})


@app.get("/api/voices/preview")
async def preview_library_voice(voice_id: str = "", url: str = "") -> Response:
    """Audition a library voice. If it has a stored preview file (`url`), proxy it
    (its URL needs our API key, which the browser can't send). Otherwise synthesize
    a short sample with the voice — most library voices lack a stored preview."""
    if not get_settings().cartesia_api_key:
        return JSONResponse({"error": "CARTESIA_API_KEY is not set."}, status_code=400)
    tts = CartesiaTTS()
    try:
        if url:
            audio, media_type = await tts.fetch_preview(url)
        elif voice_id:
            audio, media_type = await tts.synthesize_preview(voice_id)
        else:
            return JSONResponse({"error": "voice_id or url required."}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("Voice preview failed")
        return JSONResponse({"error": f"Preview failed: {exc}"}, status_code=502)
    # Let the browser cache a given preview for the session.
    return Response(
        content=audio,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.post("/api/voice/describe")
async def describe_voice(request: Request) -> JSONResponse:
    """AI-write an Inworld voice description from the character card, so the designed
    voice fits the character drafted with AI."""
    body = await request.json()
    card = body.get("card") if isinstance(body.get("card"), dict) else body
    requested = (body.get("model") or "").strip()
    model = requested if requested in ALLOWED_MODEL_IDS else None
    provider = (body.get("provider") or "inworld").strip()
    try:
        description = await draft_voice_description(card or {}, model=model, provider=provider)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("Voice-description draft failed")
        return JSONResponse({"error": f"Couldn't write a description: {exc}"}, status_code=502)
    return JSONResponse({"description": description})


@app.post("/api/voice/design")
async def design_voice(
    description: str = Form(...),
    preview_text: str = Form(""),
    provider: str = Form("inworld"),
) -> JSONResponse:
    """Design a voice from a text description (Inworld or ElevenLabs). Returns a
    preview to listen to; the preview id becomes a permanent voice at create time."""
    desc = description.strip()
    text = preview_text.strip() or _DEFAULT_PREVIEW_TEXT
    try:
        if provider == "elevenlabs":
            if not desc:
                return JSONResponse({"error": "Describe the voice first."}, status_code=400)
            previews = await ElevenLabsTTS().design_voice(desc, text)
        else:
            if not (30 <= len(desc) <= 250):
                return JSONResponse(
                    {"error": "Voice description must be 30–250 characters."}, status_code=400
                )
            previews = await InworldTTS().design_voice(desc, text, num_samples=1)
    except Exception as exc:
        logger.exception("Voice design failed")
        return JSONResponse({"error": f"Voice design failed: {exc}"}, status_code=502)
    p = previews[0]
    return JSONResponse(
        {"voice_id": p["voice_id"], "audio_b64": p["audio_b64"], "mime": p["mime"]}
    )


def _as_list(value) -> list[str]:
    """Accept a list or a newline-separated string; return trimmed non-empty items."""
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _as_secrets(value) -> list[dict]:
    out: list[dict] = []
    for s in value or []:
        if isinstance(s, dict):
            text = (s.get("text") or "").strip()
            if text:
                out.append({"text": text, "reveal_when": (s.get("reveal_when") or "").strip()})
    return out


def _as_relationships(value) -> dict:
    """Accept either {who: how} or a list of {who, how} rows (what the form sends)."""
    if isinstance(value, dict):
        return {
            str(k).strip(): str(v).strip()
            for k, v in value.items()
            if str(k).strip() and str(v).strip()
        }
    out: dict = {}
    for r in value or []:
        if isinstance(r, dict):
            who, how = (r.get("who") or "").strip(), (r.get("how") or "").strip()
            if who and how:
                out[who] = how
    return out


def _character_from_card(slug: str, card: dict, voice_id: str, provider: str, namespace: str) -> Character:
    """Build a Character from the structured card the builder UI sends."""
    return Character(
        slug=slug,
        name=(card.get("name") or "").strip(),
        voice_id=voice_id,
        tts_provider=provider,
        greeting=(card.get("greeting") or "").strip(),
        concept=(card.get("concept") or "").strip(),
        age=(card.get("age") or "").strip(),
        role=(card.get("role") or "").strip(),
        pronouns=(card.get("pronouns") or "").strip(),
        temperament=(card.get("temperament") or "").strip(),
        speech_style=_as_list(card.get("speech_style")),
        backstory=(card.get("backstory") or "").strip(),
        knows=_as_list(card.get("knows")),
        doesnt_know=_as_list(card.get("doesnt_know")),
        goals=_as_list(card.get("goals")),
        secrets=_as_secrets(card.get("secrets")),
        boundaries=_as_list(card.get("boundaries")),
        relationships=_as_relationships(card.get("relationships")),
        disposition=(card.get("disposition") or "").strip(),
        sample_lines=_as_list(card.get("sample_lines")),
        game_data=card.get("game_data") if isinstance(card.get("game_data"), dict) else {},
        system_prompt=(card.get("system_prompt") or "").strip(),
        memory_namespace=namespace,
    )


async def _resolve_voice(card: dict, sample: UploadFile | None, provider: str, name: str, current: str = ""):
    """Resolve the voice id + provider from the card's chosen source. Returns
    (voice_id, provider). Raises on a provider error."""
    voice_id = (card.get("voice_id") or "").strip() or current
    design_voice_id = (card.get("design_voice_id") or "").strip()
    sample_bytes = await sample.read() if sample is not None else b""
    if sample_bytes:
        voice_id = await make_tts(provider).clone_voice(sample_bytes, name)
    elif design_voice_id:
        # Promote the previewed designed voice into a permanent one, per provider.
        if provider == "elevenlabs":
            description = (card.get("design_description") or "").strip()
            voice_id = await ElevenLabsTTS().create_designed_voice(design_voice_id, name, description)
        else:
            voice_id = await InworldTTS().publish_voice(design_voice_id, name)
            provider = "inworld"
    return voice_id, provider


@app.post("/api/characters")
async def create_character(
    card: str = Form(...),
    sample: UploadFile | None = File(None),
) -> JSONResponse:
    """Create a character from the structured builder card (JSON). Voice comes from
    one of: an uploaded `sample` (instant-clone), a designed Inworld voice, or a
    picked library/preset `voice_id`."""
    try:
        data = json.loads(card)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Malformed character data."}, status_code=400)
    name = (data.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "Name is required."}, status_code=400)

    provider = (data.get("tts_provider") or "").strip() or get_settings().default_tts_provider
    try:
        voice_id, provider = await _resolve_voice(data, sample, provider, name)
    except Exception as exc:
        logger.exception("Voice setup failed")
        return JSONResponse({"error": f"Voice setup failed: {exc}"}, status_code=502)
    if not voice_id:
        return JSONResponse(
            {"error": "Pick a voice: record a sample, design one, or choose from the library."},
            status_code=400,
        )

    slug = slugify(name)
    character = _character_from_card(slug, data, voice_id, provider, slug)
    save_character(character)
    logger.info("Created character '%s' (voice=%s, provider=%s)", slug, voice_id, provider)
    return JSONResponse(character.public_dict(), status_code=201)


@app.post("/api/characters/draft")
async def draft_character(request: Request) -> JSONResponse:
    """AI-assist: draft a full character card from a one-line concept. The user then
    reviews/edits every field. Registered before /{slug} so the path isn't captured."""
    body = await request.json()
    concept = (body.get("concept") or "").strip()
    if not concept:
        return JSONResponse({"error": "Describe the character in a line first."}, status_code=400)
    requested = (body.get("model") or "").strip()
    model = requested if requested in ALLOWED_MODEL_IDS else None  # fall back to default
    try:
        card = await draft_card_from_concept(concept, model=model)
    except Exception as exc:
        logger.exception("Character draft failed")
        return JSONResponse({"error": f"Draft failed: {exc}"}, status_code=502)
    return JSONResponse({"card": card})


@app.post("/api/characters/preview-prompt")
async def preview_prompt(card: str = Form(...)) -> JSONResponse:
    """Compile the in-progress builder card into the character's system prompt,
    without saving — so the author can see exactly what the engine builds from the
    fields (game-data extensions included if any game has registered a renderer).
    Defined before /{slug} so the static path isn't captured as a slug."""
    try:
        data = json.loads(card)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Malformed character data."}, status_code=400)
    provider = (data.get("tts_provider") or "").strip() or get_settings().default_tts_provider
    character = _character_from_card("preview", data, (data.get("voice_id") or "").strip(), provider, "preview")
    return JSONResponse({"prompt": character.build_prompt()})


@app.post("/api/characters/{slug}")
async def update_character(
    slug: str,
    card: str = Form(...),
    sample: UploadFile | None = File(None),
) -> JSONResponse:
    """Update an existing character. The slug + memory namespace stay stable (so past
    memories survive a rename). The voice changes only if a new source is given."""
    try:
        existing = load_character(slug)
    except FileNotFoundError:
        return JSONResponse({"error": "Character not found."}, status_code=404)
    try:
        data = json.loads(card)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Malformed character data."}, status_code=400)
    name = (data.get("name") or "").strip() or existing.name

    provider = (data.get("tts_provider") or "").strip() or existing.tts_provider
    try:
        voice_id, provider = await _resolve_voice(data, sample, provider, name, current=existing.voice_id)
    except Exception as exc:
        logger.exception("Voice update failed")
        return JSONResponse({"error": f"Voice update failed: {exc}"}, status_code=502)

    updated = _character_from_card(slug, data, voice_id, provider, existing.memory_namespace)
    save_character(updated)
    logger.info("Updated character '%s'", slug)
    return JSONResponse(updated.public_dict())


@app.delete("/api/characters/{slug}")
async def remove_character(slug: str) -> JSONResponse:
    """Delete a character. Past conversation memories (keyed by namespace) survive."""
    deleted = delete_character(slug)
    if not deleted:
        return JSONResponse({"error": "Character not found."}, status_code=404)
    logger.info("Deleted character '%s'", slug)
    return JSONResponse({"deleted": True, "slug": slug})


@app.post("/api/characters/{slug}/duplicate")
async def duplicate_character(slug: str) -> JSONResponse:
    """Duplicate a character: an independent copy with its own slug and memory namespace,
    reusing the original's voice and every field as-is (no re-clone / re-design). Handy
    for A/B-ing the same character across TTS providers or forking a variant to edit."""
    try:
        original = load_character(slug)
    except FileNotFoundError:
        return JSONResponse({"error": "Character not found."}, status_code=404)
    taken = {c.slug for c in list_characters()}
    base = original.name
    name = f"{base} (copy)"
    new_slug = slugify(name)
    n = 2
    while new_slug in taken:  # keep bumping until the slug is free
        name = f"{base} (copy {n})"
        new_slug = slugify(name)
        n += 1
    copy = replace(original, slug=new_slug, name=name, memory_namespace=new_slug)
    save_character(copy)
    logger.info("Duplicated character '%s' -> '%s'", slug, new_slug)
    return JSONResponse(copy.public_dict(), status_code=201)


# ----------------------------------------------------------------------- WS loop


@app.websocket("/ws")
async def voice_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    slug = websocket.query_params.get("character", "")

    # The pipeline's producer (JSON deltas) and consumer (audio frames) run
    # concurrently and both send on this socket; a lock keeps frames from
    # interleaving, which would corrupt the WebSocket stream.
    send_lock = asyncio.Lock()

    async def emit_json(payload: dict) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    async def emit_audio(chunk: bytes) -> None:
        async with send_lock:
            await websocket.send_bytes(chunk)

    # Per-session model selection from the UI dropdown, validated against the
    # allow-list so only known models reach the API.
    requested_model = websocket.query_params.get("model", "")
    model = requested_model if requested_model in ALLOWED_MODEL_IDS else get_settings().llm_model

    # Optional speaker cadence profile -> per-session endpointing timings.
    profile_min = profile_max = None
    profile_slug = websocket.query_params.get("profile", "")
    if profile_slug:
        try:
            prof = load_profile(profile_slug)
            profile_min, profile_max = prof.min_turn_silence, prof.max_turn_silence
        except Exception:
            pass

    # Full-loop runtime (Track V): drive one Inworld Realtime session instead of the
    # modular pipeline. Selected by VOICE_RUNTIME; the pipeline path below is unchanged.
    if get_settings().voice_runtime == "inworld_fullloop":
        try:
            character = load_character(slug)
        except Exception as exc:
            logger.exception("Failed to start full-loop session")
            await emit_json({"type": "error", "message": f"Could not start session: {exc}"})
            await websocket.close()
            return
        # Per-session overrides for A/B (dropdowns or ?realtime_llm= / ?delivery=), allow-listed.
        rt_llm = websocket.query_params.get("realtime_llm", "")
        rt_override = rt_llm if rt_llm in ALLOWED_REALTIME_MODEL_IDS else None
        dlv = websocket.query_params.get("delivery", "").upper()
        dlv_override = dlv if dlv in ALLOWED_DELIVERY_MODES else None
        try:
            await run_full_loop(websocket, emit_json, emit_audio, character,
                                llm_override=rt_override, delivery_override=dlv_override)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("Full-loop session error")
        finally:
            logger.info("Full-loop session for '%s' closed", slug)
        return

    # ================= LEGACY (RETIRING) — the modular pipeline branch ==================
    # Everything below to the end of voice_ws is the retiring STT/LLM/TTS path
    # (architecture-seams.md §1.4). Retirement = delete this branch + legacy_voice.py.
    # --- set up the session for the chosen character ---
    try:
        character = load_character(slug)
        llm = AnthropicLLM(model=model)
        tts = make_tts(character.tts_provider)
        # Resilience: if the primary TTS (e.g. Inworld) hangs, fall back to Cartesia
        # so a provider outage can't silence the character.
        _settings = get_settings()
        if character.tts_provider != "cartesia" and _settings.cartesia_api_key:
            try:
                tts = FallbackTTS(tts, CartesiaTTS(), _settings.cartesia_fallback_voice)
            except Exception:
                logger.exception("Could not set up TTS fallback")
        short_term = ShortTermMemory(max_turns=get_settings().short_term_turns)
        _engine_cfg = (character.game_data or {}).get("engine", {})
        long_term = LongTermMemory(
            character.memory_namespace,
            readonly=_engine_cfg.get("memory_readonly", False) or get_settings().memory_readonly,
        )
        pipeline = Pipeline(character, llm, tts, short_term, long_term)
    except Exception as exc:
        logger.exception("Failed to start session")
        await emit_json({"type": "error", "message": f"Could not start session: {exc}"})
        await websocket.close()
        return

    # Streaming STT (AssemblyAI realtime) is used when configured; otherwise the
    # browser falls back to recording a clip and we batch-transcribe it.
    streaming_enabled = get_settings().stt_provider == "assemblyai"
    await emit_json(
        {
            "type": "ready",
            "character": character.public_dict(),
            "model": model,
            "streaming": streaming_enabled,
        }
    )
    await pipeline.speak_greeting(emit_json, emit_audio)

    # One streaming turn at a time: {aai: open stream, reader: its task}.
    stream_state: dict = {"aai": None, "reader": None, "cancel": False}

    async def stream_turn(aai: AssemblyAIStream) -> None:
        """Read the realtime transcript; on end-of-turn, run the pipeline."""
        final_text: str | None = None
        try:
            async for kind, text in aai.events():
                if kind == "partial":
                    await emit_json({"type": "partial_transcript", "text": text})
                elif kind == "final":
                    final_text = text
                    break
        except Exception as exc:
            logger.exception("Streaming reader failed")
            await emit_json({"type": "error", "message": f"Transcription stream error: {exc}"})
        finally:
            await aai.close()
            stream_state["aai"] = None
        await emit_json({"type": "mic_ended"})  # tell the browser to stop capturing
        if stream_state["cancel"]:
            stream_state["cancel"] = False
            return
        if final_text and final_text.strip():
            await emit_json({"type": "transcript", "text": final_text})
            latency = LatencyTracker()
            latency.start("vad_stop")
            latency.mark("transcript_ready")  # streaming: ready at end-of-speech
            await pipeline.run_turn(final_text, latency, emit_json, emit_audio)
        else:
            await emit_json({"type": "info", "message": "Didn't catch that — try again."})

    async def start_stream() -> None:
        reader = stream_state["reader"]
        if reader is not None and not reader.done():
            return  # a turn is still being processed
        aai = AssemblyAIStream(min_silence=profile_min, max_silence=profile_max)
        await aai.connect()
        stream_state["aai"] = aai
        stream_state["cancel"] = False
        stream_state["reader"] = asyncio.create_task(stream_turn(aai))

    # --- turn loop ---
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            # Binary frame: live PCM for an open stream, else a batch clip.
            if message.get("bytes") is not None:
                aai = stream_state["aai"]
                if aai is not None:
                    await aai.send_audio(message["bytes"])
                    continue
                if streaming_enabled:
                    # Streaming mode but no open stream — these are stray frames
                    # arriving after a turn finalized; drop them (never batch).
                    continue
                latency = LatencyTracker()
                latency.start("vad_stop")
                try:
                    transcript = await get_stt().transcribe(message["bytes"])
                except Exception as exc:
                    logger.exception("STT failed")
                    await emit_json({"type": "error", "message": f"Transcription failed: {exc}"})
                    continue
                latency.mark("transcript_ready")
                if not transcript:
                    await emit_json({"type": "info", "message": "Didn't catch that — try again."})
                    continue
                await emit_json({"type": "transcript", "text": transcript})
                await pipeline.run_turn(transcript, latency, emit_json, emit_audio)

            elif message.get("text") is not None:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                mtype = data.get("type")
                if mtype == "mic_start":
                    try:
                        await start_stream()
                    except Exception as exc:
                        logger.exception("Failed to start streaming STT")
                        await emit_json({"type": "error", "message": f"Couldn't start mic: {exc}"})
                        await emit_json({"type": "mic_ended"})
                elif mtype == "mic_stop":
                    aai = stream_state["aai"]
                    if aai is not None:
                        stream_state["cancel"] = True
                        await aai.close()
                elif mtype == "text":
                    user_text = (data.get("text") or "").strip()
                    if not user_text:
                        continue
                    latency = LatencyTracker()
                    latency.start("vad_stop")
                    latency.mark("transcript_ready")  # no STT for typed input
                    await emit_json({"type": "transcript", "text": user_text})
                    # Track E: a game may attach transient context (location/time/who's
                    # present/recent events) to the turn; the engine injects it per request.
                    request = RespondRequest(
                        player_input=user_text,
                        situation=Situation.from_dict(data.get("situation")),
                    )
                    await pipeline.respond(request, latency, emit_json, emit_audio)
                elif mtype == "remember":
                    await _handle_remember(pipeline.long_term, data, emit_json)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket loop error")
    finally:
        aai = stream_state.get("aai")
        if aai is not None:
            await aai.close()
        logger.info("Session for '%s' closed", slug)


# ---------------------------------------------------------- static frontend (last)

# A new build token every server start. Injected into the asset URLs so the
# browser is forced to fetch fresh app.js / pcm-player.js after any restart —
# stale-cache can never silently serve old frontend code again.
_BUILD = str(int(time.time()))


@app.get("/")
async def index() -> HTMLResponse:
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace('src="/app.js"', f'src="/app.js?v={_BUILD}"')
    # expose the build to JS (for the worklet URL + the visible version stamp)
    html = html.replace("<head>", f'<head>\n  <script>window.__BUILD__="{_BUILD}";</script>')
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})


from .sandbox import router as sandbox_router  # noqa: E402

app.include_router(sandbox_router)


@app.get("/sandbox")
async def sandbox_page() -> HTMLResponse:
    """The director's sandbox — a dev tool to drive an NPC's world by hand (see orchestrator/sandbox.py)."""
    html = (WEB_DIR / "sandbox.html").read_text(encoding="utf-8")
    html = html.replace('src="/sandbox.js"', f'src="/sandbox.js?v={_BUILD}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})


# Mounted last so the API/WS routes above take precedence over the catch-all.
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
