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

from .adapters._audio import fade_pcm
from .adapters.base import LLMAdapter, TTSAdapter
from .character_store import Character
from .config import AUDIO_SAMPLE_RATE
from .context import ENGINE_DIRECTION, RespondRequest, Situation, build_instructions
from .expressivity import (
    leading_tone,
    parse_pause,
    renders_tone,
    split_inline_tones,
    splits_mid_line,
)
from .latency import LatencyTracker
from .memory.long_term import LongTermMemory
from .memory.short_term import ShortTermMemory
from .sentence_chunker import Segment, SentenceChunker
from .text_cleanup import clean_for_speech
from .timing import GAP_MAX_MS, SENTENCE_GAP_MS, TONE_SHIFT_GAP_MS

logger = logging.getLogger(__name__)

EmitJson = Callable[[dict], Awaitable[None]]
EmitAudio = Callable[[bytes], Awaitable[None]]

# A breath between spoken sentences. TTS renders each sentence with no leading or
# trailing silence, so without this they butt straight up against each other and a
# multi-sentence reply sounds rushed ("...doesn't heal.You want the ale or not.").
# We inject a short run of silent PCM between sentences, sized by how the previous
# one ended. All durations live in timing.SENTENCE_GAP_MS — tune them there.


def _gap_after(sentence: str, para_break: bool = False) -> int:
    """How long a silence to leave after this sentence, by its ending and whether a
    paragraph break (a blank line in the reply) followed it. A paragraph break is a
    real beat, so it floors the gap regardless of how the sentence ended."""
    t = sentence.rstrip().rstrip('"\'”’)')
    if t.endswith(("…", "—")) or t.endswith("..."):
        base = SENTENCE_GAP_MS["trailing"]
    elif t.endswith(("?", "!")):
        base = SENTENCE_GAP_MS["emphatic"]
    elif t.endswith((",", ";", ":")):
        base = SENTENCE_GAP_MS["clause"]
    else:
        base = SENTENCE_GAP_MS["default"]
    return max(base, SENTENCE_GAP_MS["paragraph"]) if para_break else base


def _silence_pcm(ms: int) -> bytes:
    """`ms` of digital silence as signed-16 mono PCM at our playback rate."""
    samples = int(AUDIO_SAMPLE_RATE * ms / 1000)
    return b"\x00\x00" * samples

# Cap on how much same-tone text we fold into one Inworld request when batching for
# prosody (see consume). Bounds a single request's size so it streams promptly and a
# stall can't strand too much audio. ~2-3 sentences.
INWORLD_BATCH_MAX_CHARS = 300

# Each synthesized request is faded to/from zero over this many ms at its edges, so the
# silence stitched between requests can't click (a per-utterance TTS cuts each request off
# abruptly; the hard step onto silence pops, audibly, once per boundary). Inaudible as a fade.
_EDGE_FADE_MS = 8


async def _faded(chunks):
    """Wrap a request's PCM stream so its first and last _EDGE_FADE_MS fade to zero — the
    audio then starts and ends silent and can't click where it meets the inter-request
    silence. Holds back a tiny tail (~the fade length) to fade the true end; adds no real
    latency. Yields the same total audio, edges ramped, always sample-aligned (provider
    chunks can split a 16-bit sample, so a stray byte is carried forward, never emitted)."""
    fade_bytes = int(AUDIO_SAMPLE_RATE * _EDGE_FADE_MS / 1000) * 2  # even
    buf = b""
    faded_in = False
    async for chunk in chunks:
        buf += chunk
        if not faded_in and len(buf) >= fade_bytes:  # ramp the head once we have enough
            buf = fade_pcm(buf[:fade_bytes], AUDIO_SAMPLE_RATE, fade_in=True, ms=_EDGE_FADE_MS) + buf[fade_bytes:]
            faded_in = True
        # Emit everything except a held-back tail (>= fade_bytes, for the closing fade),
        # keeping the emitted run even-aligned and carrying any odd trailing byte forward.
        keep = fade_bytes + (len(buf) & 1)
        if len(buf) > keep:
            cut = len(buf) - keep
            yield buf[:cut]
            buf = buf[cut:]
    if buf:
        if not faded_in:  # whole request was shorter than the fade window
            buf = fade_pcm(buf, AUDIO_SAMPLE_RATE, fade_in=True, ms=_EDGE_FADE_MS)
        yield fade_pcm(buf, AUDIO_SAMPLE_RATE, fade_out=True, ms=_EDGE_FADE_MS)

# ENGINE_DIRECTION moved to context.py (shared by both runtimes); re-exported via the
# import above so `from .pipeline import ENGINE_DIRECTION` still resolves.


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

    def _build_system(self, memories: list[str], situation: Situation | None = None) -> str:
        # Shared assembly (context.build_instructions): static profile + per-provider
        # delivery directive + recalled memories + the game's transient "Current
        # situation". Same builder the full-loop runtime uses.
        return build_instructions(
            self.character,
            memories=memories,
            situation=situation,
            performance_provider=self.character.tts_provider,
        )

    # -------------------------------------------------------------------- turn

    async def run_turn(
        self,
        user_text: str,
        latency: LatencyTracker,
        emit_json: EmitJson,
        emit_audio: EmitAudio,
    ) -> None:
        """Chat-shaped entry point — a thin wrapper over `respond`. Kept so the typed/STT
        callers are unchanged while the engine's real unit becomes a `RespondRequest`."""
        await self.respond(
            RespondRequest(player_input=user_text), latency, emit_json, emit_audio
        )

    async def respond(
        self,
        request: RespondRequest,
        latency: LatencyTracker,
        emit_json: EmitJson,
        emit_audio: EmitAudio,
    ) -> None:
        """Handle one request end-to-end: retrieve -> generate -> speak -> remember.

        The unit of work is a `RespondRequest` (a player line and/or a game event, plus
        the game's transient `Situation`), not a bare chat message — so a game can drive
        the character with context, not just relay user text."""
        user_text = request.input_text()
        query = request.query()
        memories = await self.long_term.retrieve(query) if query else []
        system = self._build_system(memories, request.situation)
        messages = self.short_term.messages() + [
            {"role": "user", "content": user_text}
        ]

        await emit_json({"type": "assistant_start"})

        sentence_q: asyncio.Queue[Segment | None] = asyncio.Queue()
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
                    for seg in chunker.push(delta):
                        await sentence_q.put(seg)
                tail = chunker.flush()
                if tail:
                    await sentence_q.put(tail)
            finally:
                # Always signal end-of-stream so the consumer can drain and exit,
                # even if the LLM stream errored partway through.
                await sentence_q.put(None)  # sentinel: no more sentences

        async def consume() -> None:
            audio_started = False
            pending_gap_ms = 0  # silence owed before the NEXT batch's first audio
            last_tone: str | None = None  # carried across lines within this reply
            # Some providers can't shift tone within one utterance (Inworld), so we split
            # a line at any mid-line tone tag and synthesize each part separately (a tiny
            # beat "acts" the change). Providers that shift tone inline (ElevenLabs) don't.
            # The per-provider flag lives on its voice profile in expressivity.py.
            split_tones = splits_mid_line(self.character.tts_provider)
            # Inworld is per-utterance: it resets prosody on every request, so sentences
            # synthesized alone don't flow into each other. We BATCH a run of consecutive
            # SAME-TONE sentences into one request so intonation carries across them — but
            # only ones ALREADY queued (the empty() check below), so batching never waits.
            # This includes the FIRST request: the opening sentence flows into the batch
            # when more is ready, instead of standing out as a lone, differently-paced
            # utterance — while the empty() check still ships it promptly when it's alone.
            do_batch = self.character.tts_provider == "inworld"

            buf_text = ""           # accumulated spoken text of the pending batch
            buf_tone: str | None = None
            buf_unit = ""           # the batch's last unit (for its trailing gap)
            buf_para = False        # paragraph break trailing that last unit

            async def flush() -> None:
                """Synthesize and stream the pending batch, then clear it. Each request's
                edges are faded to zero (via _faded) so the silence stitched between requests
                can't click — a per-utterance TTS cuts each request off abruptly, and that
                hard edge against silence pops, once per boundary, on good speakers."""
                nonlocal buf_text, buf_tone, pending_gap_ms, audio_started
                if not buf_text:
                    return
                try:
                    has_audio = False
                    async for chunk in _faded(
                        self.tts.stream_speech(buf_text, self.character.voice_id)
                    ):
                        if not state["first_audio"]:
                            state["first_audio"] = True
                            latency.mark("first_audio")
                            await emit_json({"type": "audio_start"})
                            await emit_json({"type": "latency", "marks": latency.summary()})
                            audio_started = True
                        if not has_audio:
                            has_audio = True
                            # Owed breath right before this batch's first audio — never a
                            # trailing tail, so it adds no end-of-turn lag.
                            if pending_gap_ms:
                                await emit_audio(_silence_pcm(pending_gap_ms))
                                pending_gap_ms = 0
                        await emit_audio(chunk)
                    if has_audio:
                        pending_gap_ms = _gap_after(buf_unit, buf_para)
                except Exception as exc:
                    # One batch failing must not silence the rest of the reply: skip it and
                    # keep going. Surface the error only once per turn so a genuinely-down
                    # provider doesn't spam the user.
                    logger.exception("TTS failed on a sentence; skipping it")
                    if not state["tts_failed"]:
                        state["tts_failed"] = True  # "error already surfaced" flag
                        await emit_json(
                            {"type": "error", "message": f"Text-to-speech failed: {exc}"}
                        )
                finally:
                    buf_text = ""
                    buf_tone = None

            while True:
                # If a batch is pending and nothing else is queued yet, ship it now rather
                # than make the user wait — so we only ever batch sentences already in hand
                # (zero added latency; the opener batches only when sentence 2 is already
                # ready, else it ships alone to keep first audio prompt).
                if buf_text and sentence_q.empty():
                    await flush()
                seg = await sentence_q.get()
                if seg is None:
                    break
                units = split_inline_tones(seg.text) if split_tones else [seg.text]
                for unit_i, unit in enumerate(units):
                    pause_ms, rest = parse_pause(unit)  # dramatic lead-in silence, if cued
                    # Carry the active tone to an untagged line so delivery doesn't snap
                    # back to neutral after a pause or "..."; a new lead tone replaces it —
                    # but only if THIS voice can actually perform it, so a tone the model
                    # invents that we'd drop doesn't blank the carry and flatten what follows.
                    tone = leading_tone(rest)
                    if tone and renders_tone(rest, self.character.tts_provider):
                        last_tone = tone
                    elif last_tone:
                        rest = f"[{last_tone}] {rest}"
                    spoken = clean_for_speech(rest)
                    if not spoken:
                        continue  # pure stage direction / markup / punctuation
                    para = seg.para_break if unit_i == len(units) - 1 else False
                    tone_change = unit_i > 0  # a mid-line tone shift within this segment

                    # Can this sentence ride the pending batch? Same tone only, no forced
                    # break between, under the size cap — and never the first utterance.
                    can_join = (
                        do_batch
                        and buf_text != ""
                        and not tone_change
                        and pause_ms == 0
                        and last_tone == buf_tone
                        and not buf_para
                        and len(buf_text) + 1 + len(spoken) <= INWORLD_BATCH_MAX_CHARS
                    )
                    if can_join:
                        buf_text = f"{buf_text} {spoken}"
                        buf_unit, buf_para = unit, para
                        continue

                    # Can't join: ship the pending batch, then open a new one with this unit.
                    await flush()
                    if tone_change:  # a mid-sentence tone shift — a brief beat acts it
                        pending_gap_ms = min(pending_gap_ms + TONE_SHIFT_GAP_MS, GAP_MAX_MS)
                    if pause_ms:
                        pending_gap_ms = min(pending_gap_ms + pause_ms, GAP_MAX_MS)
                    buf_text, buf_tone, buf_unit, buf_para = spoken, last_tone, unit, para
                    # Non-batching providers synth every unit now. Inworld holds the unit so
                    # the next same-tone sentence can join it; the while-loop's empty() check
                    # ships it the moment nothing else is queued (so first audio stays prompt
                    # when the opener is alone, but flows into the batch when more is ready).
                    if not do_batch:
                        await flush()
            await flush()  # drain the final batch
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

        # Persist this exchange into both memory tiers. Tag it with the game-time from
        # the request's situation (if any) so recency-aware recall has a `when`.
        if full_reply:
            self.short_term.add_user(user_text)
            self.short_term.add_assistant(full_reply)
            when = request.situation.game_time if request.situation else ""
            await self.long_term.add_exchange(user_text, full_reply, when=when)

    # ---------------------------------------------------------------- greeting

    async def speak_greeting(self, emit_json: EmitJson, emit_audio: EmitAudio) -> None:
        """Speak the character's pre-authored greeting when a session opens."""
        text = (self.character.greeting or "").strip()
        if not text:
            return
        await emit_json({"type": "assistant_done", "text": text})
        audio_started = False
        chunker = SentenceChunker()
        segments = chunker.push(text)
        tail = chunker.flush()
        if tail:
            segments.append(tail)
        pending_gap_ms = 0
        last_tone: str | None = None
        try:
            for seg in segments:
                pause_ms, rest = parse_pause(seg.text)
                tone = leading_tone(rest)
                if tone and renders_tone(rest, self.character.tts_provider):
                    last_tone = tone
                elif last_tone:
                    rest = f"[{last_tone}] {rest}"
                spoken = clean_for_speech(rest)
                if not spoken:
                    continue
                if pause_ms:
                    pending_gap_ms = min(pending_gap_ms + pause_ms, GAP_MAX_MS)
                sentence_has_audio = False
                async for chunk in _faded(
                    self.tts.stream_speech(spoken, self.character.voice_id)
                ):
                    if not audio_started:
                        audio_started = True
                        await emit_json({"type": "audio_start"})
                    if not sentence_has_audio:
                        sentence_has_audio = True
                        if pending_gap_ms:
                            await emit_audio(_silence_pcm(pending_gap_ms))
                            pending_gap_ms = 0
                    await emit_audio(chunk)
                if sentence_has_audio:
                    pending_gap_ms = _gap_after(seg.text, seg.para_break)
        except Exception as exc:
            logger.exception("Greeting TTS failed")
            await emit_json({"type": "error", "message": f"Greeting failed: {exc}"})
        if audio_started:
            await emit_json({"type": "audio_end"})
        # Record the greeting as the assistant's opening line for context.
        self.short_term.add_assistant(text)
