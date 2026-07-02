"""Anthropic LLM adapter (streaming).

Concrete `LLMAdapter` backed by the Anthropic Messages API. We stream token deltas
so the pipeline can begin sentence-chunking (and therefore TTS) before the full
reply is generated.

Swapping the LLM provider is a one-file change: implement `LLMAdapter` elsewhere
and construct that instead in the pipeline.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

import anthropic

from ..config import get_settings
from .base import LLMAdapter

logger = logging.getLogger(__name__)

# ONE AsyncAnthropic client (HTTP connection pool) per api key per process. AnthropicLLM is
# constructed ad hoc throughout the engine (per background judgment, per engine, per DM);
# each instance building its own client wasted a connection pool per call (arch review theme C).
_CLIENTS: dict[str, anthropic.AsyncAnthropic] = {}


def _shared_client(api_key: str) -> anthropic.AsyncAnthropic:
    client = _CLIENTS.get(api_key)
    if client is None:
        client = _CLIENTS[api_key] = anthropic.AsyncAnthropic(api_key=api_key)
    return client


class AnthropicLLM(LLMAdapter):
    def __init__(self, model: str | None = None, max_tokens: int | None = None) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file."
            )
        self._model = model or settings.llm_model
        # Realtime replies stay short; one-shot authoring (drafting a character)
        # needs more room, so callers can raise the cap.
        self._max_tokens = max_tokens or settings.llm_max_tokens
        # We pass the key explicitly so a non-default key in .env is always honored.
        self._client = _shared_client(settings.anthropic_api_key)

    @staticmethod
    def _system_param(system):
        """PROMPT CACHING (no behavior change — the model sees the exact same concatenated text).
        A plain `str` is left uncached (its content may be dynamic, and caching a per-call-changing
        prefix only wastes cache writes). A `list[str]` is an explicit opt-in: the FIRST segment is
        the STABLE prefix (e.g. the character sheet / standing instructions) and gets a cache
        breakpoint; later segments (dynamic per-turn context) stay uncached. Concatenation of the
        blocks equals the original string, so generation is identical."""
        if isinstance(system, str):
            return system
        blocks = [{"type": "text", "text": s} for s in system if s]
        if blocks:
            blocks[0] = {**blocks[0], "cache_control": {"type": "ephemeral"}}
        return blocks or ""

    @staticmethod
    def _cache_messages(messages: list[dict]) -> list[dict]:
        """Mark the conversation HISTORY prefix cacheable — breakpoint on the last message BEFORE the
        current turn, not on the final message. The final user turn carries the per-turn dynamic
        context (unique every request), so a breakpoint there would write a cache entry that is never
        read; the history prefix, by contrast, is byte-identical and append-only across turns, so it
        accrues real read hits ("shared prefix, varying suffix" placement). Model input is unchanged
        (cache_control is metadata)."""
        if len(messages) < 2:
            return messages  # first turn: no reusable history yet — a write here would never be read
        out = [dict(m) for m in messages]
        content = out[-2].get("content")
        if isinstance(content, str):
            out[-2]["content"] = [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
        elif isinstance(content, list) and content and isinstance(content[-1], dict):
            blocks = [dict(b) for b in content]
            blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
            out[-2]["content"] = blocks
        return out

    async def stream_reply(
        self, messages: list[dict], system="", *, cache_messages: bool = False
    ) -> AsyncIterator[str]:
        # `messages.stream()` accumulates state and exposes a clean `text_stream` of deltas.
        # Prompt caching (system prefix + optionally the message history) is purely a cost/latency
        # optimization: cache_control is metadata, so the generated text is unaffected.
        msgs = self._cache_messages(messages) if cache_messages else messages
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=self._system_param(system),
            messages=msgs,
        ) as stream:
            async for text in stream.text_stream:
                yield text
            try:  # one-line cache telemetry (never breaks generation)
                u = (await stream.get_final_message()).usage
                cr = getattr(u, "cache_read_input_tokens", 0) or 0
                cc = getattr(u, "cache_creation_input_tokens", 0) or 0
                if cr or cc:
                    logger.debug("anthropic cache: read=%d create=%d fresh_input=%d",
                                 cr, cc, getattr(u, "input_tokens", 0) or 0)
            except Exception:  # noqa: BLE001
                pass
