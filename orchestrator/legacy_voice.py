"""RETIRING voice machinery, quarantined (arch review theme E; architecture-seams.md §1.4).

Everything here belongs to the modular STT/LLM/TTS path that the Inworld full-loop runtime
replaces: the lazily-built shared STT instance and the speech-cadence calibration WebSocket.
Retirement = delete this file (+ the marked LEGACY branch in main.voice_ws) and drop the
include_router in main.py. Do not invest here.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .adapters.base import STTAdapter
from .adapters.stt_assemblyai import AssemblyAISTT
from .adapters.stt_assemblyai_stream import AssemblyAIStream
from .adapters.stt_whisper import WhisperSTT
from .cadence import analyze_cadence
from .config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


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




@router.websocket("/ws/calibrate")
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

