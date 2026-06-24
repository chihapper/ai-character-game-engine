"""AssemblyAI realtime streaming STT.

Unlike the batch adapter, this transcribes audio *as it arrives* and signals
end-of-turn the moment the speaker stops — so the transcript is ready with no
post-speech delay. The browser streams 16 kHz PCM16 to our backend, which proxies
it here (the API key never leaves the server).

Flow per turn:
    stream = AssemblyAIStream(); await stream.connect()
    ... await stream.send_audio(pcm) repeatedly ...
    async for kind, text in stream.events():   # "partial" | "final"
        ...
    await stream.close()

Docs: wss://streaming.assemblyai.com/v3/ws ; token via GET /v3/token.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx
import websockets

from ..config import get_settings

logger = logging.getLogger(__name__)

STREAM_SAMPLE_RATE = 16_000  # AssemblyAI streaming input rate
# u3-rt-pro = Universal-3 Pro Realtime (the wire value; "Universal-3.5 Pro" is the
# marketing name). `encoding` defaults to pcm_s16le and `format_turns` is a no-op
# on this model (formatting is built into end-of-turn), so we omit both.
_STREAM_MODEL = "u3-rt-pro"
_TOKEN_URL = "https://streaming.assemblyai.com/v3/token?expires_in_seconds=120"
_WS_BASE = (
    "wss://streaming.assemblyai.com/v3/ws"
    f"?sample_rate={STREAM_SAMPLE_RATE}&speech_model={_STREAM_MODEL}"
)


async def _mint_token(api_key: str) -> str:
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
        resp = await client.get(_TOKEN_URL, headers={"Authorization": api_key})
        if resp.status_code != 200:
            raise RuntimeError(
                f"AssemblyAI token error {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()["token"]


class AssemblyAIStream:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.assemblyai_api_key:
            raise RuntimeError("ASSEMBLYAI_API_KEY is not set. Add it to your .env file.")
        self._api_key = settings.assemblyai_api_key
        self._min_silence = settings.assemblyai_min_turn_silence
        self._max_silence = settings.assemblyai_max_turn_silence
        self._ws = None  # active websocket connection, or None

    async def connect(self) -> None:
        token = await _mint_token(self._api_key)
        self._ws = await websockets.connect(f"{_WS_BASE}&token={token}", max_size=None)
        # Make end-of-turn detection patient enough for slow/disfluent speech.
        await self._ws.send(
            json.dumps(
                {
                    "type": "UpdateConfiguration",
                    "min_turn_silence": self._min_silence,
                    "max_turn_silence": self._max_silence,
                }
            )
        )

    async def send_audio(self, pcm: bytes) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(pcm)
            except websockets.ConnectionClosed:
                pass

    async def events(self) -> AsyncIterator[tuple[str, str]]:
        """Yield ("partial", text) for interim results and ("final", text) when a
        turn ends (end_of_turn). Returns when the session terminates."""
        if self._ws is None:
            return
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            mtype = msg.get("type")
            if mtype == "Turn":
                text = msg.get("transcript", "") or ""
                if msg.get("end_of_turn"):
                    yield ("final", text)
                else:
                    yield ("partial", text)
            elif mtype in ("Termination", "SessionTerminated"):
                return
            elif mtype == "error" or msg.get("error"):
                logger.warning("AssemblyAI streaming error: %s", str(msg)[:200])

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "Terminate"}))
            except Exception:
                pass
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
