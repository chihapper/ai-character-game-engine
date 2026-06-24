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

from .adapters.base import STTAdapter, TTSAdapter
from .adapters.llm_anthropic import AnthropicLLM
from .adapters.stt_assemblyai import AssemblyAISTT
from .adapters.stt_assemblyai_stream import AssemblyAIStream
from .adapters.stt_whisper import WhisperSTT
from .adapters.tts_cartesia import CartesiaTTS
from .adapters.tts_fallback import FallbackTTS
from .adapters.tts_inworld import InworldTTS
from .cadence import analyze_cadence
from .profile_store import (
    Profile,
    delete_profile,
    list_profiles,
    load_profile,
    save_profile,
)
from .profile_store import slugify as profile_slugify
from .character_store import (
    Character,
    list_characters,
    load_character,
    save_character,
    slugify,
)
from .config import (
    ALLOWED_MODEL_IDS,
    AVAILABLE_MODELS,
    WEB_DIR,
    get_settings,
)
from .latency import LatencyTracker
from .memory.long_term import LongTermMemory
from .memory.short_term import ShortTermMemory
from .pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("orchestrator")

app = FastAPI(title="Real-Time AI Character Engine")


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
    if provider == "cartesia":
        return CartesiaTTS()
    return InworldTTS()


# One shared STT instance, built lazily on first voice turn so a missing key (or
# unloaded model) never blocks server boot and text-only use keeps working.
_stt: STTAdapter | None = None


def get_stt() -> STTAdapter:
    global _stt
    if _stt is None:
        if get_settings().stt_provider == "assemblyai":
            _stt = AssemblyAISTT()
        else:
            _stt = WhisperSTT()
    return _stt


# ------------------------------------------------------------------- REST: chars


@app.get("/api/characters")
async def get_characters() -> JSONResponse:
    return JSONResponse([c.public_dict() for c in list_characters()])


@app.get("/api/characters/{slug}/full")
async def get_character_full(slug: str) -> JSONResponse:
    """Full editable fields for one character (the list endpoint omits the prompt)."""
    try:
        c = load_character(slug)
    except FileNotFoundError:
        return JSONResponse({"error": "Character not found."}, status_code=404)
    return JSONResponse(
        {
            "slug": c.slug,
            "name": c.name,
            "system_prompt": c.system_prompt,
            "greeting": c.greeting,
            "tts_provider": c.tts_provider,
            "voice_id": c.voice_id,
        }
    )


@app.get("/api/models")
async def get_models() -> JSONResponse:
    """Selectable LLMs for the UI dropdown, plus the default selection."""
    return JSONResponse({"models": AVAILABLE_MODELS, "default": get_settings().llm_model})


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
    """Browse a provider's voice library so the user can pick + preview a voice.
    Cartesia-only for now (Inworld has no comparable browse — it uses design or a
    named preset id)."""
    if provider != "cartesia":
        return JSONResponse(
            {"voices": [], "error": "Library browsing is only available for Cartesia."}
        )
    if not get_settings().cartesia_api_key:
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


@app.post("/api/voice/design")
async def design_voice(
    description: str = Form(...),
    preview_text: str = Form(""),
) -> JSONResponse:
    """Design a voice from a text description (Inworld). Returns a preview to listen
    to; the preview voice id is published into a permanent voice at create time."""
    desc = description.strip()
    if not (30 <= len(desc) <= 250):
        return JSONResponse(
            {"error": "Voice description must be 30–250 characters."}, status_code=400
        )
    text = preview_text.strip() or _DEFAULT_PREVIEW_TEXT
    try:
        previews = await InworldTTS().design_voice(desc, text, num_samples=1)
    except Exception as exc:
        logger.exception("Voice design failed")
        return JSONResponse({"error": f"Voice design failed: {exc}"}, status_code=502)
    p = previews[0]
    return JSONResponse(
        {"voice_id": p["voice_id"], "audio_b64": p["audio_b64"], "mime": p["mime"]}
    )


@app.post("/api/characters")
async def create_character(
    name: str = Form(...),
    system_prompt: str = Form(...),
    greeting: str = Form(""),
    tts_provider: str = Form(""),
    voice_id: str = Form(""),
    design_voice_id: str = Form(""),
    sample: UploadFile | None = File(None),
) -> JSONResponse:
    """Create a character with one of three voice sources:
      * `sample` uploaded -> instant-clone it (provider's clone API)
      * `design_voice_id` set -> publish a previously-designed Inworld voice
      * `voice_id` set -> use a preset/library voice as-is
    """
    settings = get_settings()
    provider = tts_provider or settings.default_tts_provider

    resolved_voice_id = voice_id.strip()
    try:
        sample_bytes = await sample.read() if sample is not None else b""
        if sample_bytes:
            resolved_voice_id = await make_tts(provider).clone_voice(sample_bytes, name)
        elif design_voice_id.strip():
            # Voice design is Inworld-only; publish the previewed voice to keep it.
            resolved_voice_id = await InworldTTS().publish_voice(design_voice_id.strip(), name)
            provider = "inworld"
    except Exception as exc:
        logger.exception("Voice setup failed")
        return JSONResponse({"error": f"Voice setup failed: {exc}"}, status_code=502)

    if not resolved_voice_id:
        return JSONResponse(
            {"error": "Provide a recorded sample, a designed voice, or a preset voice_id."},
            status_code=400,
        )

    slug = slugify(name)
    character = Character(
        slug=slug,
        name=name,
        system_prompt=system_prompt,
        voice_id=resolved_voice_id,
        tts_provider=provider,
        greeting=greeting,
        memory_namespace=slug,
    )
    save_character(character)
    logger.info("Created character '%s' (voice=%s, provider=%s)", slug, resolved_voice_id, provider)
    return JSONResponse(character.public_dict(), status_code=201)


@app.post("/api/characters/{slug}")
async def update_character(
    slug: str,
    name: str = Form(...),
    system_prompt: str = Form(...),
    greeting: str = Form(""),
    tts_provider: str = Form(""),
    voice_id: str = Form(""),
    design_voice_id: str = Form(""),
    sample: UploadFile | None = File(None),
) -> JSONResponse:
    """Update an existing character. The slug + memory namespace stay stable (so
    past memories survive a rename). The voice is only changed if a new source is
    given (recorded sample, designed voice, or a different preset id)."""
    try:
        existing = load_character(slug)
    except FileNotFoundError:
        return JSONResponse({"error": "Character not found."}, status_code=404)

    provider = tts_provider or existing.tts_provider
    resolved_voice_id = existing.voice_id  # keep current voice unless changed
    try:
        sample_bytes = await sample.read() if sample is not None else b""
        if sample_bytes:
            resolved_voice_id = await make_tts(provider).clone_voice(sample_bytes, name)
        elif design_voice_id.strip():
            resolved_voice_id = await InworldTTS().publish_voice(design_voice_id.strip(), name)
            provider = "inworld"
        elif voice_id.strip():
            resolved_voice_id = voice_id.strip()
    except Exception as exc:
        logger.exception("Voice update failed")
        return JSONResponse({"error": f"Voice update failed: {exc}"}, status_code=502)

    updated = Character(
        slug=slug,
        name=name,
        system_prompt=system_prompt,
        voice_id=resolved_voice_id,
        tts_provider=provider,
        greeting=greeting,
        memory_namespace=existing.memory_namespace,
    )
    save_character(updated)
    logger.info("Updated character '%s'", slug)
    return JSONResponse(updated.public_dict())


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
        long_term = LongTermMemory(character.memory_namespace)
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
                    await pipeline.run_turn(user_text, latency, emit_json, emit_audio)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket loop error")
    finally:
        aai = stream_state.get("aai")
        if aai is not None:
            await aai.close()
        logger.info("Session for '%s' closed", slug)


@app.websocket("/ws/calibrate")
async def calibrate_ws(websocket: WebSocket) -> None:
    """Stream ~30s of speech to AssemblyAI with a WIDE end-of-turn window (so it
    doesn't chop the speaker up), collect inter-word gaps, and derive their cadence
    on stop. The browser then names + saves the result as a profile."""
    await websocket.accept()

    async def emit_json(payload: dict) -> None:
        await websocket.send_json(payload)

    if get_settings().stt_provider != "assemblyai":
        await emit_json(
            {"type": "error", "message": "Calibration needs AssemblyAI streaming STT."}
        )
        await websocket.close()
        return

    state: dict = {"aai": None, "reader": None, "gaps": []}
    await emit_json({"type": "ready"})

    async def collect(aai: AssemblyAIStream) -> None:
        try:
            async for turn in aai.turns():
                words = turn.get("words") or []
                for i in range(1, len(words)):
                    gap = (words[i].get("start") or 0) - (words[i - 1].get("end") or 0)
                    if gap >= 0:
                        state["gaps"].append(gap)
                await emit_json(
                    {"type": "calibration_progress", "samples": len(state["gaps"])}
                )
        except Exception:
            logger.exception("Calibration collector failed")

    async def start() -> None:
        if state["reader"] is not None and not state["reader"].done():
            return
        aai = AssemblyAIStream(min_silence=1500, max_silence=4000)  # wide -> natural pauses
        await aai.connect()
        state["aai"] = aai
        state["gaps"] = []
        state["reader"] = asyncio.create_task(collect(aai))

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                aai = state["aai"]
                if aai is not None:
                    await aai.send_audio(message["bytes"])
            elif message.get("text") is not None:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                mtype = data.get("type")
                if mtype == "mic_start":
                    try:
                        await start()
                    except Exception as exc:
                        logger.exception("Failed to start calibration")
                        await emit_json({"type": "error", "message": f"Couldn't start: {exc}"})
                elif mtype == "mic_stop":
                    aai = state["aai"]
                    if aai is not None:
                        await aai.close()
                        state["aai"] = None
                    if state["reader"] is not None:
                        try:
                            await asyncio.wait_for(state["reader"], timeout=5)
                        except Exception:
                            pass
                    await emit_json(
                        {"type": "calibration_result", **analyze_cadence(state["gaps"])}
                    )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Calibration WS error")
    finally:
        aai = state.get("aai")
        if aai is not None:
            await aai.close()


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


# Mounted last so the API/WS routes above take precedence over the catch-all.
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
