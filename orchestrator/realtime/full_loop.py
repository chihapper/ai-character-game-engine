"""The full-loop voice runtime (Track V — the KEEPER): drive one Inworld Realtime session as the
whole STT->LLM->TTS conversational loop, steering it with the engine's per-turn RR context and
executing tool calls. Moved out of main.py so the committed runtime lives beside its session
wrapper (arch review theme E: decompose by FATE — this file survives the pipeline retirement).
`_handle_remember` is the WS memory-write seam, shared with the legacy pipeline branch until that
branch is deleted."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time

from fastapi import WebSocket

from .inworld_session import InworldSession
from ..adapters.tts_inworld import InworldTTS
from ..config import get_settings
from ..context import RespondRequest, Situation, build_instructions
from ..engine import Engine

logger = logging.getLogger(__name__)


# ------------------------------------------------------- full-loop runtime (Track V)

# Demo tool so the wired full loop exercises mechanics end-to-end. Real game tools
# arrive via the game/engine seam (Track E, issue #2); this placeholder rolls dice
# locally so we can see tool calls drive in-character continuations today.
_REALTIME_TOOLS = [
    {
        "type": "function",
        "name": "roll_dice",
        "description": "Roll dice for a check when the scene calls for chance.",
        "parameters": {
            "type": "object",
            "properties": {
                "sides": {"type": "integer", "description": "die size, e.g. 20 for a d20"},
                "reason": {"type": "string", "description": "what the roll is for"},
            },
            "required": ["sides", "reason"],
        },
    }
]


def _run_realtime_tool(call: dict) -> dict:
    """Execute a tool call from the session. Placeholder until the game-tool seam exists."""
    if call.get("name") == "roll_dice":
        try:
            args = json.loads(call.get("args") or "{}")
        except json.JSONDecodeError:
            args = {}
        sides = max(2, int(args.get("sides") or 20))
        return {"result": random.randint(1, sides), "sides": sides}
    return {"error": f"unknown tool {call.get('name')}"}


def _num(x) -> float | None:
    """A game clock value from a WS payload, or None if absent/non-numeric."""
    return float(x) if isinstance(x, (int, float)) else None


async def _handle_remember(long_term, data: dict, emit_json, *, engine=None) -> None:
    """The memory-write seam over the WS: a game pushes a durable world event into the
    character's long-term memory. {type:"remember", fact, when?, kind?, importance?, player_role?}.
    When `engine` is given and `player_role` is set ("caused"/"benefited"), the event ALSO shifts
    the character's disposition toward the player (#12-A) — the engine judges the impact."""
    fact = (data.get("fact") or "").strip()
    if not fact:
        return
    try:
        importance = float(data.get("importance", 0.7))
    except (TypeError, ValueError):
        importance = 0.7
    raw_clock = data.get("clock", data.get("t"))  # numeric game clock -> temporal decay
    clock = float(raw_clock) if isinstance(raw_clock, (int, float)) else None
    kw = dict(when=(data.get("when") or ""), kind=(data.get("kind") or "world_event"),
              importance=importance, t=clock)
    player_role = (data.get("player_role") or "").strip() or None
    actor = (data.get("actor") or "player").strip() or "player"  # "self" = NPC's own change (#19)
    if engine is not None:
        await engine.remember(fact, player_role=player_role, actor=actor, **kw)
    else:
        await long_term.remember(fact, **kw)
    await emit_json({"type": "remembered", "fact": fact})


async def _speak_greeting_fullloop(character, emit_json, emit_audio) -> None:
    """Voice the authored greeting via Inworld TTS-2 in the character's own voice (the
    same voice the session uses), so the open matches the pipeline path."""
    text = (character.greeting or "").strip()
    if not text:
        return
    await emit_json({"type": "assistant_done", "text": text})
    started = False
    try:
        async for chunk in InworldTTS().stream_speech(text, character.voice_id):
            if not started:
                started = True
                await emit_json({"type": "audio_start"})
            await emit_audio(chunk)
    except Exception as exc:
        logger.exception("Full-loop greeting failed")
        await emit_json({"type": "error", "message": f"Greeting failed: {exc}"})
    if started:
        await emit_json({"type": "audio_end"})


async def run_full_loop(websocket: WebSocket, emit_json, emit_audio, character,
                        llm_override=None, delivery_override=None) -> None:
    """Drive one Inworld full-loop session, mapping its events onto the browser protocol.

    Per turn (§5.6): before the model responds, retrieve memories against the arena query
    and inject them via session.update — so the voice loop has the same relevance-realization
    recall as the modular pipeline. Voice turns retrieve after the input transcript arrives
    (on commit, before respond); typed turns retrieve immediately. Memory writes (salience-
    scored) happen in the background, flushed at the next turn."""
    settings = get_settings()
    active_model = llm_override or settings.realtime_llm_model
    _instructions = build_instructions(character, performance_provider="inworld")

    def make_session() -> InworldSession:
        return InworldSession(
            instructions=_instructions, voice_id=character.voice_id, tools=_REALTIME_TOOLS,
            llm_model=active_model, delivery_mode=delivery_override,
        )

    session = make_session()
    if llm_override or delivery_override:
        logger.info("Full-loop session overrides: llm=%s delivery=%s",
                    active_model, delivery_override or settings.realtime_delivery_mode)
    engine_cfg = (character.game_data or {}).get("engine", {})
    readonly = engine_cfg.get("memory_readonly", False) or settings.memory_readonly
    # The runtime-agnostic engine core owns the turn logic (prepare/reflect) + the stores; this
    # voice loop is just its Inworld wrapper (STT in, TTS out, barge-in, reconnect).
    engine = Engine(character, readonly=readonly)
    long_term = engine.long_term  # local aliases for the WS handlers + debug emit
    commitments = engine.commitments
    relationship_store = engine.relationship
    short_term = engine.short_term
    await session.connect()
    await emit_json(
        {
            "type": "ready",
            "character": character.public_dict(),
            "model": active_model,
            "streaming": True,
        }
    )
    await _speak_greeting_fullloop(character, emit_json, emit_audio)

    turn = {"user": None, "reply": [], "situation": None, "audio_open": False,
            "ctx_id": None, "seq": 0, "responding": False}
    writes: set = set()  # in-flight background memory-write tasks (GC guard)

    def flush_turn() -> None:
        """Close the previous turn: record it to short-term SYNCHRONOUSLY (so the next turn's
        arena query sees it), then reflect it (salience + relationship + long-term) in the
        background via the engine — never on the player's critical path."""
        reply = "".join(turn["reply"]).strip()
        if turn["user"] and reply:
            short_term.add_user(turn["user"])
            short_term.add_assistant(reply)
            if not long_term.readonly:
                task = asyncio.create_task(
                    engine.reflect(turn["user"], reply, turn["situation"], memories=turn.get("memories")))
                writes.add(task)
                task.add_done_callback(writes.discard)
        turn["user"], turn["reply"] = None, []

    async def retrieve_and_respond(user_text: str, situation) -> None:
        """Per turn: the engine prepares recall + the dynamic context (§5.6, commitments,
        relationship, decay); we inject it as a context item and let Inworld generate.
        Reflection runs in the background at the next flush."""
        _t0 = time.monotonic()
        flush_turn()  # close out the prior turn (-> short-term + background reflect)
        turn["user"], turn["situation"] = user_text, situation
        injected, dbg = await engine.prepare(RespondRequest(player_input=user_text, situation=situation))
        turn["memories"] = dbg["memories"]  # for the next flush's contradiction check (#10)
        if settings.memory_debug:
            await emit_json({"type": "memories", "query": dbg["query"],
                             "short_term": short_term.messages(),
                             "commitments": [{"text": c.text, "due": c.due, "importance": c.importance}
                                             for c in commitments.open_items()],
                             "relationship": relationship_store.get().to_dict(),
                             "intent": dbg["intent"],
                             "selected": dbg["memories"], "scored": dbg["scored"],
                             "embedder": dbg["embedder"]})
        _t_ret = time.monotonic()
        # #2: inject the dynamic per-turn context as a SYSTEM context item, leaving the base
        # instructions stable (cache-friendly). Delete the prior turn's item first so only the
        # current RR selection is live — no stale-memory accumulation.
        if turn["ctx_id"]:
            await session.delete_item(turn["ctx_id"])
            turn["ctx_id"] = None
        if injected:
            turn["seq"] += 1
            ctx_id = f"rr-ctx-{turn['seq']}"
            await session.add_context(injected, item_id=ctx_id)
            turn["ctx_id"] = ctx_id
        await session.respond()
        turn["responding"] = True
        logger.info("RR-latency: build+retrieve=%.0fms (mem=%d) before respond",
                    (_t_ret - _t0) * 1000, len(dbg["memories"]))

    async def pump() -> None:
        """Forward session events to the browser; on a voice transcript, retrieve+respond."""
        async for kind, data in session.events():
            if kind == "audio":
                if not turn["audio_open"]:
                    turn["audio_open"] = True
                    await emit_json({"type": "audio_start"})
                await emit_audio(data)
            elif kind == "partial_transcript":
                await emit_json({"type": "partial_transcript", "text": data})
            elif kind == "transcript":  # VOICE turn input (arrives on commit, before respond)
                await emit_json({"type": "transcript", "text": data})
                await retrieve_and_respond(data, None)
            elif kind == "assistant_delta":
                await emit_json({"type": "assistant_delta", "text": data})
            elif kind == "assistant_done":
                turn["responding"] = False
                if data:
                    turn["reply"].append(data)
                if turn["audio_open"]:
                    await emit_json({"type": "audio_end"})
                    turn["audio_open"] = False
                await emit_json({"type": "assistant_done", "text": data})
            elif kind == "tool_call":
                await session.send_tool_result(data["call_id"], _run_realtime_tool(data))
            elif kind == "error":
                await emit_json({"type": "error", "message": data})

    stop = asyncio.Event()

    async def reconnect() -> bool:
        """Rebuild the Inworld session after it drops, restoring recent dialogue so the
        character keeps the thread. Engine memory (short/long-term) persists across this;
        only the Inworld-side session is recreated."""
        nonlocal session
        for attempt in range(1, 4):
            await asyncio.sleep(min(2 * attempt, 6))  # backoff
            try:
                fresh = make_session()
                await fresh.connect()
                for m in short_term.messages():  # replay recent turns as history
                    if m["role"] == "user":
                        await fresh.add_text(m["content"])
                    else:
                        await fresh.add_assistant(m["content"])
                try:
                    await session.close()
                except Exception:
                    pass
                session = fresh
                turn["responding"] = False
                turn["ctx_id"] = None  # the prior turn's context item died with the session
                logger.info("Reconnected the Inworld session (attempt %d)", attempt)
                return True
            except Exception:
                logger.exception("Reconnect attempt %d failed", attempt)
        return False

    async def pump_supervisor() -> None:
        """Run the pump; if the session dies while the browser is still here, reconnect."""
        while not stop.is_set():
            try:
                await pump()
            except Exception:
                logger.exception("Full-loop pump error")
            if stop.is_set():
                break
            await emit_json({"type": "info", "message": "Reconnecting the voice…"})
            if await reconnect():
                await emit_json({"type": "info", "message": "Reconnected."})
            else:
                await emit_json(
                    {"type": "error", "message": "Lost the voice connection — please reconnect."}
                )
                break

    pump_task = asyncio.create_task(pump_supervisor())
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                await session.send_audio(message["bytes"])  # browser 16 kHz mic frame
            elif message.get("text") is not None:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                mtype = data.get("type")
                if mtype == "mic_start":
                    # Barge-in: the player started talking. If the character is mid-reply,
                    # cut it off (cancel the response + drop queued output) so they can
                    # interrupt naturally; the browser already stopped local playback.
                    if turn["responding"]:
                        await session.interrupt()
                        turn["responding"] = False
                        if turn["audio_open"]:
                            await emit_json({"type": "audio_end"})
                            turn["audio_open"] = False
                        logger.info("Barge-in: interrupted in-progress response")
                elif mtype == "mic_stop":
                    # Commit only; the transcript event drives retrieve+respond (pump).
                    await session.commit_audio()
                elif mtype == "text":
                    txt = (data.get("text") or "").strip()
                    if txt:
                        await emit_json({"type": "transcript", "text": txt})
                        await session.add_text(txt)
                        await retrieve_and_respond(txt, Situation.from_dict(data.get("situation")))
                elif mtype == "remember":
                    await _handle_remember(long_term, data, emit_json, engine=engine)
                elif mtype == "commit":
                    # The game declares an obligation the character has taken on.
                    c = commitments.add(
                        (data.get("text") or "").strip(),
                        made_t=_num(data.get("made_t", data.get("clock", data.get("t")))),
                        due_t=_num(data.get("due_t")), due=(data.get("due") or ""),
                        parties=data.get("parties") or [],
                        importance=float(data.get("importance", 0.5) or 0.5),
                    )
                    if c:
                        await emit_json({"type": "committed", "id": c.id, "text": c.text})
                elif mtype == "resolve_commitment":
                    # The game marks an obligation fulfilled/broken; it converts to a memory.
                    c = await engine.resolve_commitment(
                        (data.get("id") or "").strip(), (data.get("status") or "").strip(),
                        t=_num(data.get("clock", data.get("t"))))
                    await emit_json({"type": "commitment_resolved", "id": data.get("id"),
                                     "status": c.status if c else "unknown"})
    finally:
        stop.set()  # tell the supervisor not to reconnect during teardown
        flush_turn()
        pump_task.cancel()
        await session.close()

