"""AssemblyAI STT adapter (cloud — no local model, no CUDA, nothing to install).

Batch transcription of a recorded clip: upload the bytes, submit, poll for the
transcript. This is the realistic choice for a shippable game — players need no
local dependencies — and it transcribes noticeably better than a small local
Whisper model. WebM/Opus from the browser's MediaRecorder uploads as-is.

A future real-time upgrade uses AssemblyAI's streaming WebSocket (transcribe while
speaking); this batch adapter keeps the current click-to-talk flow.

Auth: `Authorization: <API_KEY>` (no "Bearer" prefix).
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from ..config import get_settings
from .base import STTAdapter

logger = logging.getLogger(__name__)

_BASE = "https://api.assemblyai.com"


class AssemblyAISTT(STTAdapter):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.assemblyai_api_key:
            raise RuntimeError(
                "ASSEMBLYAI_API_KEY is not set. Add it to your .env file."
            )
        self._headers = {"Authorization": settings.assemblyai_api_key}

    async def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes:
            return ""
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            # 1. Upload the raw clip (WebM/Opus accepted directly — no transcode).
            up = await client.post(
                f"{_BASE}/v2/upload",
                headers={**self._headers, "Content-Type": "application/octet-stream"},
                content=audio_bytes,
            )
            if up.status_code != 200:
                raise RuntimeError(
                    f"AssemblyAI upload error {up.status_code}: {up.text[:200]}"
                )
            upload_url = up.json()["upload_url"]

            # 2. Submit for transcription. speech_models is an ordered fallback
            # list (required on pre-recorded; tries the first available model).
            sub = await client.post(
                f"{_BASE}/v2/transcript",
                headers={**self._headers, "Content-Type": "application/json"},
                json={
                    "audio_url": upload_url,
                    "language_code": "en_us",
                    "speech_models": ["universal-3-pro", "universal-2"],
                },
            )
            if sub.status_code != 200:
                raise RuntimeError(
                    f"AssemblyAI submit error {sub.status_code}: {sub.text[:200]}"
                )
            transcript_id = sub.json()["id"]

            # 3. Poll until terminal (short utterances finish in a few seconds).
            poll_url = f"{_BASE}/v2/transcript/{transcript_id}"
            for _ in range(60):  # ~30s ceiling
                poll = await client.get(poll_url, headers=self._headers)
                if poll.status_code != 200:
                    # A transient poll hiccup (5xx, gateway blip) must not lose the
                    # job — the transcript is still cooking server-side. Re-poll.
                    await asyncio.sleep(0.5)
                    continue
                try:
                    result = poll.json()
                except ValueError:
                    await asyncio.sleep(0.5)  # non-JSON blip — same story, re-poll
                    continue
                status = result.get("status")
                if status == "completed":
                    return (result.get("text") or "").strip()
                if status == "error":
                    raise RuntimeError(
                        f"AssemblyAI transcription error: {result.get('error')}"
                    )
                await asyncio.sleep(0.5)
            raise RuntimeError("AssemblyAI transcription timed out")
