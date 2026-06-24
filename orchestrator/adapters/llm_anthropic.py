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


class AnthropicLLM(LLMAdapter):
    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file."
            )
        self._model = model or settings.llm_model
        self._max_tokens = settings.llm_max_tokens
        # AsyncAnthropic resolves the key from ANTHROPIC_API_KEY automatically, but
        # we pass it explicitly so a non-default key in .env is always honored.
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def stream_reply(
        self, messages: list[dict], system: str = ""
    ) -> AsyncIterator[str]:
        # haiku (the snappy default) does not use extended thinking; we simply
        # stream text. The `messages.stream()` helper accumulates state and exposes
        # a clean `text_stream` of deltas.
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
