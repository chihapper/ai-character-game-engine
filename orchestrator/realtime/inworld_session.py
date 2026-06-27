"""One Inworld Realtime session — the full-loop voice runtime.

A single WebSocket session owns the whole loop: STT -> LLM (routed to Claude) ->
Realtime TTS-2, with cross-turn voice continuity. The engine *steers* it (character
instructions + tools + per-turn input) and owns memory/state around it; it does NOT
orchestrate STT/LLM/TTS as separate stages (that's the retiring modular pipeline).

Everything here is lifted from the Phase-0 spikes, which verified against the live API
(docs/track-v-full-loop-plan.md, §5R/5D/5E). The load-bearing facts:

  * Protocol is OpenAI-Realtime over `wss://api.inworld.ai/api/v1/realtime/session`,
    `Authorization: Basic <INWORLD_API_KEY>`.
  * `session.update.session.type` must be `"realtime"`.
  * Audio in AND out are PCM s16le mono @ 24 kHz (== our wire format). The browser mic
    is 16 kHz, so `send_audio` resamples 16->24 server-side.
  * Voice MUST be a *published* library voice id (a design preview silently falls back
    to a default). Model `inworld-tts-2` honors `[bracket]` steering tags.
  * Manual turn-taking: append audio -> commit -> `response.create`. (`turn_detection`
    is disabled; push-to-talk drives the turn, matching the existing mic UX.)
  * Function calling: on a tool call, run it and submit a `function_call_output` item
    (NOT `function_call_result`) — and do NOT send `response.create` after it: the tool
    output AUTO-continues. A manual `response.create` cancels it (reason "superseded").

`events()` is a long-running async iterator that normalizes the wire events into the
engine's vocabulary; `send_*` methods write to the same socket concurrently.
"""
from __future__ import annotations

import base64
import json
import logging
import uuid
from typing import AsyncIterator

import websockets

from ..adapters._audio import resample_pcm16
from ..config import AUDIO_SAMPLE_RATE, get_settings

logger = logging.getLogger(__name__)

_WS_BASE = "wss://api.inworld.ai/api/v1/realtime/session"
# The browser mic streams at this rate (web/app.js STREAM_RATE); we resample to the
# session's 24 kHz input.
MIC_INPUT_RATE = 16_000


class InworldSession:
    def __init__(
        self,
        *,
        instructions: str,
        voice_id: str,
        tools: list[dict] | None = None,
        llm_model: str | None = None,
        tts_model: str | None = None,
        delivery_mode: str | None = None,
    ) -> None:
        settings = get_settings()
        if not settings.inworld_api_key:
            raise RuntimeError(
                "INWORLD_API_KEY is not set. Add it to your .env file "
                "(the Portal's Base64 signature, pasted verbatim)."
            )
        self._auth_header = f"Basic {settings.inworld_api_key}"
        self._instructions = instructions
        self._voice_id = voice_id
        self._tools = tools or []
        self._llm_model = llm_model or settings.realtime_llm_model
        self._tts_model = tts_model or settings.realtime_tts_model
        mode = (delivery_mode or settings.realtime_delivery_mode or "CREATIVE").upper()
        self._delivery_mode = mode if mode in {"STABLE", "BALANCED", "CREATIVE"} else "CREATIVE"
        self._ws = None
        self._resample_state = None  # carried across mic frames for click-free resampling

    # ---------------------------------------------------------------- lifecycle

    async def connect(self) -> None:
        """Open the session and push our config. Returns once `session.updated` lands."""
        key = f"session-{uuid.uuid4().hex}"
        url = f"{_WS_BASE}?key={key}&protocol=realtime"
        self._ws = await websockets.connect(
            url, additional_headers={"Authorization": self._auth_header}, max_size=None
        )
        await self._send(
            {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "model": self._llm_model,  # routes the agent's LLM (e.g. Claude)
                    "instructions": self._instructions,
                    "output_modalities": ["audio", "text"],
                    "audio": {
                        # turn_detection: None -> manual turns (push-to-talk drives them).
                        "input": {
                            "format": {"type": "audio/pcm", "rate": AUDIO_SAMPLE_RATE},
                            "turn_detection": None,
                        },
                        "output": {
                            "format": {"type": "audio/pcm", "rate": AUDIO_SAMPLE_RATE},
                            "model": self._tts_model,
                            "voice": self._voice_id,
                        },
                    },
                    "tools": self._tools,
                    "tool_choice": "auto" if self._tools else "none",
                    # tts-2 generation preset (stability vs expressiveness).
                    "providerData": {"tts": {"delivery_mode": self._delivery_mode}},
                },
            }
        )
        # Drain until the server acknowledges the config (or errors).
        assert self._ws is not None
        async for raw in self._ws:
            msg = _loads(raw)
            if msg is None:
                continue
            if msg.get("type") == "session.updated":
                out = (msg.get("session") or {}).get("audio", {}).get("output", {})
                logger.info(
                    "Inworld session ready: voice=%s model=%s llm=%s delivery=%s",
                    out.get("voice"), out.get("model"),
                    (msg.get("session") or {}).get("model"), self._delivery_mode,
                )
                return
            if msg.get("type") == "error":
                raise RuntimeError(f"Inworld session error: {json.dumps(msg.get('error'))[:300]}")

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    # ------------------------------------------------------------------- writes

    async def send_audio(self, pcm16_mic: bytes) -> None:
        """Append a browser mic frame (16 kHz PCM16) to the input buffer, resampled to
        the session's 24 kHz. Call repeatedly while the user holds to talk."""
        if self._ws is None or not pcm16_mic:
            return
        pcm24, self._resample_state = resample_pcm16(
            pcm16_mic, MIC_INPUT_RATE, AUDIO_SAMPLE_RATE, self._resample_state
        )
        await self._send(
            {"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm24).decode()}
        )

    async def commit_audio(self) -> None:
        """Commit the buffered audio (manual turn). Does NOT trigger a response — the
        input transcript arrives next (events()), so the caller can retrieve memories and
        re-steer before calling respond()."""
        self._resample_state = None
        await self._send({"type": "input_audio_buffer.commit"})

    async def add_text(self, text: str) -> None:
        """Add a typed user turn to the conversation. Does NOT trigger a response."""
        await self._send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )

    async def update_instructions(self, instructions: str) -> None:
        """Re-steer the session's system instructions mid-conversation. Replaces the whole
        instructions string — so re-sending the full character prompt every turn busts the
        provider's prompt cache. Prefer add_context() for per-turn memory injection; this
        stays for whole-prompt changes."""
        await self._send({"type": "session.update", "session": {"instructions": instructions}})

    async def add_context(self, text: str, *, item_id: str | None = None) -> None:
        """Inject per-turn dynamic context (recalled memories + live Situation) as a small
        SYSTEM context item, leaving the big base instructions untouched (so they stay
        cached). The model treats it as its own background knowledge — verified in the #2
        latency spike. Pair with delete_item() to keep only the current turn's item live."""
        item = {"type": "message", "role": "system", "content": [{"type": "input_text", "text": text}]}
        if item_id:
            item["id"] = item_id
        await self._send({"type": "conversation.item.create", "item": item})

    async def delete_item(self, item_id: str) -> None:
        """Remove a prior conversation item (e.g. last turn's memory context) so the
        per-turn RR selection doesn't accumulate stale memory blocks in the session."""
        await self._send({"type": "conversation.item.delete", "item_id": item_id})

    async def respond(self) -> None:
        """Ask the model to generate its turn (after the user input + any re-steer)."""
        await self._send({"type": "response.create"})

    async def interrupt(self) -> None:
        """Barge-in: stop the in-progress response and drop any audio the server has queued
        but not yet streamed. Send when the player starts talking over the character. The
        cancelled response surfaces as response.done status=cancelled, which events() ignores."""
        await self._send({"type": "response.cancel"})
        await self._send({"type": "output_audio_buffer.clear"})

    # Convenience wrappers (input + immediate response, no interposed retrieval).
    async def commit_audio_turn(self) -> None:
        await self.commit_audio()
        await self.respond()

    async def send_text_turn(self, text: str) -> None:
        await self.add_text(text)
        await self.respond()

    async def send_tool_result(self, call_id: str, output: dict | str) -> None:
        """Return a tool result. The continuation is AUTOMATIC — we deliberately do NOT
        send `response.create` (that spawns a second response that cancels this one,
        reason 'superseded' — see §5E)."""
        out = output if isinstance(output, str) else json.dumps(output)
        await self._send(
            {
                "type": "conversation.item.create",
                "item": {"type": "function_call_output", "call_id": call_id, "output": out},
            }
        )

    async def _send(self, msg: dict) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps(msg))
            except websockets.ConnectionClosed:
                pass

    # -------------------------------------------------------------------- reads

    async def events(self) -> AsyncIterator[tuple[str, object]]:
        """Yield normalized engine events until the socket closes:

            ("partial_transcript", str)  user STT, interim
            ("transcript", str)          user STT, final (the turn's input)
            ("assistant_delta", str)     spoken-reply text, as it streams
            ("audio", bytes)             24 kHz PCM, browser-ready
            ("tool_call", dict)          {name, call_id, args} — caller runs it then
                                         calls send_tool_result()
            ("assistant_done", str)      a response finished (full spoken text)
            ("error", str)
        """
        if self._ws is None:
            return
        spoken: list[str] = []          # accumulates the current reply's spoken text
        fn: dict | None = None          # function call being assembled
        fn_args: list[str] = []
        async for raw in self._ws:
            msg = _loads(raw)
            if msg is None:
                continue
            t = msg.get("type", "")

            if t == "response.output_audio.delta":
                audio = _audio_bytes(msg.get("delta"))
                if audio:
                    yield ("audio", audio)
            elif t in ("response.output_audio_transcript.delta", "response.audio_transcript.delta"):
                delta = msg.get("delta") or ""
                if delta:
                    spoken.append(delta)
                    yield ("assistant_delta", delta)
            elif "input_audio_transcription" in t:
                text = msg.get("transcript") or msg.get("delta") or ""
                if t.endswith(".completed") and text:
                    yield ("transcript", text)
                elif text:
                    yield ("partial_transcript", text)
            elif t == "response.output_item.added" and (msg.get("item") or {}).get("type") == "function_call":
                it = msg["item"]
                fn = {"name": it.get("name"), "call_id": it.get("call_id")}
                fn_args = []
            elif t == "response.function_call_arguments.delta":
                fn_args.append(msg.get("delta", ""))
            elif t == "response.function_call_arguments.done" and fn is not None:
                fn["args"] = msg.get("arguments") or "".join(fn_args)
                yield ("tool_call", fn)
                fn = None
            elif t == "response.done":
                status = (msg.get("response") or {}).get("status")
                # A "cancelled/superseded" response carries no new content; ignore it.
                if status != "cancelled":
                    yield ("assistant_done", "".join(spoken).strip())
                spoken = []
            elif t == "error":
                yield ("error", json.dumps(msg.get("error"))[:300])


def _loads(raw) -> dict | None:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _audio_bytes(delta) -> bytes:
    if not isinstance(delta, str) or not delta:
        return b""
    try:
        return base64.b64decode(delta)
    except Exception:
        return b""
