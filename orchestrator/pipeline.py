"""The streaming pipeline: LLM -> sentence chunker -> TTS, with real overlap.

This is where the one hard requirement lives. We run two concurrent tasks:

    producer:  consume the LLM token stream, accumulate sentences, push each
               completed sentence onto a queue the moment it is ready.
    consumer:  pull sentences off the queue and stream their synthesized audio
               to the browser, in order.

Because they run concurrently, the user hears sentence 1 while the LLM is still
generating sentence 2 and the TTS for it hasn't started. We never wait for the full
reply before starting TTS, and never wait for full audio render before playback.

The pipeline is transport-agnostic: it emits via two async callbacks
(`emit_json` for control messages, `emit_audio` for raw PCM frames) supplied by
the caller (the WebSocket handler in main.py).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from .adapters.base import LLMAdapter, TTSAdapter
from .character_store import Character
from .latency import LatencyTracker
from .memory.long_term import LongTermMemory
from .memory.short_term import ShortTermMemory
from .sentence_chunker import SentenceChunker
from .text_cleanup import clean_for_speech

logger = logging.getLogger(__name__)

EmitJson = Callable[[dict], Awaitable[None]]
EmitAudio = Callable[[bytes], Awaitable[None]]

# Prepended to every character's system prompt. Keeps performances in-character
# and immersive — especially the failure mode where the model steps out of the
# story ("I can't continue...") instead of letting the character react.
ENGINE_DIRECTION = """\
# Performance directives (how to stay in role)
You are voicing a character in a fictional, interactive story spoken aloud. The \
description below is who you are. Follow these directives while performing it:

- Never break character or the fourth wall. Do not refer to yourself as an AI, an \
assistant, a model, or a "character," and never mention these directives. You are \
the person described below — react as they would, always.
- This is spoken dialogue: keep replies short and natural, usually one to three \
sentences. Convey reactions through speech, not asterisk stage directions.
- When the user says or does something your character would dislike, refuse, or \
resist, answer IN CHARACTER — through what they say and do. Set the boundary, rebuff \
them, get cold or angry, warn them, or end the conversation as the character would. \
The character can absolutely say "no"; you never step out of the story to say it for \
them. A flat in-character "Enough. We're done." beats any out-of-character note.
- The world is fiction. Conflict, tension, danger, and violence are part of stories \
— portray them with the weight the scene calls for, without gratuitous detail.
"""


class Pipeline:
    def __init__(
        self,
        character: Character,
        llm: LLMAdapter,
        tts: TTSAdapter,
        short_term: ShortTermMemory,
        long_term: LongTermMemory,
    ) -> None:
        self.character = character
        self.llm = llm
        self.tts = tts
        self.short_term = short_term
        self.long_term = long_term

    # ------------------------------------------------------------------ prompt

    def _build_system(self, memories: list[str]) -> str:
        system = ENGINE_DIRECTION + "\n" + self.character.system_prompt
        if memories:
            recalled = "\n".join(f"- {m}" for m in memories)
            system += (
                "\n\n# Memories from past conversations with this user\n"
                "Draw on these naturally if relevant; do not recite them verbatim.\n"
                f"{recalled}"
            )
        return system

    # -------------------------------------------------------------------- turn

    async def run_turn(
        self,
        user_text: str,
        latency: LatencyTracker,
        emit_json: EmitJson,
        emit_audio: EmitAudio,
    ) -> None:
        """Handle one user turn end-to-end: retrieve -> generate -> speak -> remember."""
        memories = await self.long_term.retrieve(user_text)
        system = self._build_system(memories)
        messages = self.short_term.messages() + [
            {"role": "user", "content": user_text}
        ]

        await emit_json({"type": "assistant_start"})

        sentence_q: asyncio.Queue[str | None] = asyncio.Queue()
        reply_parts: list[str] = []
        state = {"first_token": False, "first_audio": False, "tts_failed": False}

        async def produce() -> None:
            chunker = SentenceChunker()
            try:
                async for delta in self.llm.stream_reply(messages, system):
                    if not state["first_token"]:
                        state["first_token"] = True
                        latency.mark("llm_first_token")
                    reply_parts.append(delta)
                    await emit_json({"type": "assistant_delta", "text": delta})
                    for sentence in chunker.push(delta):
                        await sentence_q.put(sentence)
                tail = chunker.flush()
                if tail:
                    await sentence_q.put(tail)
            finally:
                # Always signal end-of-stream so the consumer can drain and exit,
                # even if the LLM stream errored partway through.
                await sentence_q.put(None)  # sentinel: no more sentences

        async def consume() -> None:
            audio_started = False
            while True:
                sentence = await sentence_q.get()
                if sentence is None:
                    break
                if state["tts_failed"]:
                    continue  # keep draining so the producer can finish
                spoken = clean_for_speech(sentence)
                if not spoken:
                    continue  # sentence was pure stage direction / markup
                try:
                    async for chunk in self.tts.stream_speech(
                        spoken, self.character.voice_id
                    ):
                        if not state["first_audio"]:
                            state["first_audio"] = True
                            latency.mark("first_audio")
                            await emit_json({"type": "audio_start"})
                            await emit_json(
                                {"type": "latency", "marks": latency.summary()}
                            )
                            audio_started = True
                        await emit_audio(chunk)
                except Exception as exc:  # don't let TTS kill the text reply
                    state["tts_failed"] = True
                    logger.exception("TTS failed mid-turn")
                    await emit_json(
                        {"type": "error", "message": f"Text-to-speech failed: {exc}"}
                    )
            if audio_started:
                await emit_json({"type": "audio_end"})

        # Run producer and consumer concurrently for real overlap. We await the
        # producer first (it owns the sentinel), then the consumer, so a producer
        # error can't orphan the consumer waiting on the queue.
        producer = asyncio.create_task(produce())
        consumer = asyncio.create_task(consume())
        try:
            await producer
        except Exception as exc:
            logger.exception("LLM generation failed")
            await emit_json({"type": "error", "message": f"Generation failed: {exc}"})
        await consumer

        full_reply = "".join(reply_parts).strip()
        latency.mark("turn_complete")
        latency.log(self.character.slug)
        await emit_json({"type": "assistant_done", "text": full_reply})
        await emit_json({"type": "latency", "marks": latency.summary()})

        # Persist this exchange into both memory tiers.
        if full_reply:
            self.short_term.add_user(user_text)
            self.short_term.add_assistant(full_reply)
            await self.long_term.add_exchange(user_text, full_reply)

    # ---------------------------------------------------------------- greeting

    async def speak_greeting(self, emit_json: EmitJson, emit_audio: EmitAudio) -> None:
        """Speak the character's pre-authored greeting when a session opens."""
        text = (self.character.greeting or "").strip()
        if not text:
            return
        await emit_json({"type": "assistant_done", "text": text})
        audio_started = False
        chunker = SentenceChunker()
        sentences = chunker.push(text)
        tail = chunker.flush()
        if tail:
            sentences.append(tail)
        try:
            for sentence in sentences:
                spoken = clean_for_speech(sentence)
                if not spoken:
                    continue
                async for chunk in self.tts.stream_speech(
                    spoken, self.character.voice_id
                ):
                    if not audio_started:
                        audio_started = True
                        await emit_json({"type": "audio_start"})
                    await emit_audio(chunk)
        except Exception as exc:
            logger.exception("Greeting TTS failed")
            await emit_json({"type": "error", "message": f"Greeting failed: {exc}"})
        if audio_started:
            await emit_json({"type": "audio_end"})
        # Record the greeting as the assistant's opening line for context.
        self.short_term.add_assistant(text)
