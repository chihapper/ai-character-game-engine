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

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .adapters.base import STTAdapter, TTSAdapter
from .adapters.llm_anthropic import AnthropicLLM
from .adapters.stt_assemblyai import AssemblyAISTT
from .adapters.stt_whisper import WhisperSTT
from .adapters.tts_cartesia import CartesiaTTS
from .adapters.tts_inworld import InworldTTS
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


_DEFAULT_PREVIEW_TEXT = (
    "Hello there. Sit down and rest a while — you look like you've come a long way, "
    "and the road only gets colder from here."
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

    # --- set up the session for the chosen character ---
    try:
        character = load_character(slug)
        llm = AnthropicLLM(model=model)
        tts = make_tts(character.tts_provider)
        short_term = ShortTermMemory(max_turns=get_settings().short_term_turns)
        long_term = LongTermMemory(character.memory_namespace)
        pipeline = Pipeline(character, llm, tts, short_term, long_term)
    except Exception as exc:
        logger.exception("Failed to start session")
        await emit_json({"type": "error", "message": f"Could not start session: {exc}"})
        await websocket.close()
        return

    await emit_json({"type": "ready", "character": character.public_dict(), "model": model})
    await pipeline.speak_greeting(emit_json, emit_audio)

    # --- turn loop ---
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            latency = LatencyTracker()

            # Voice turn: a complete recorded clip arrived as a binary frame.
            if message.get("bytes") is not None:
                latency.start("vad_stop")  # browser already endpointed (click-to-talk)
                audio = message["bytes"]
                try:
                    transcript = await get_stt().transcribe(audio)
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

            # Text turn: a typed message (used by the text-first vertical slice).
            elif message.get("text") is not None:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                if data.get("type") == "text":
                    user_text = (data.get("text") or "").strip()
                    if not user_text:
                        continue
                    latency.start("vad_stop")
                    latency.mark("transcript_ready")  # no STT for typed input
                    await emit_json({"type": "transcript", "text": user_text})
                    await pipeline.run_turn(user_text, latency, emit_json, emit_audio)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket loop error")
    finally:
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


# Mounted last so the API/WS routes above take precedence over the catch-all.
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
