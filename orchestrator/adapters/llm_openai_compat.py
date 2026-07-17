"""OpenAI-compatible LLM adapter for LOCAL judgment models (llama.cpp `llama-server`, vLLM).

Purpose-built for the judge seat (see judgment.py — the single home for provider swap):
`CRED_ENGINE_MODEL="local/<name>"` routes the engine-process roles here. The surface mirrors
exactly what judgment.complete() uses from AnthropicLLM — constructor(model, max_tokens) +
stream_reply(messages, system) — nothing more; the spoken-reply path is untouched.

Sampling is deliberately NOT set per-request: the audition rule is "sampling per model card,
not per habit", and llama-server carries each model's card defaults via its launch flags
(--temp/--top-p/--top-k). This adapter sends only the prompt and the token budget.

Base URL from LOCAL_JUDGE_BASE_URL (default http://127.0.0.1:8080/v1 — llama-server's default
port). Optional LOCAL_JUDGE_API_KEY for vLLM-style deployments; llama-server ignores auth.
"""
from __future__ import annotations

import logging
import os
from typing import AsyncIterator

import httpx

from .base import LLMAdapter

logger = logging.getLogger(__name__)

#: local judgment calls are latency-tolerant background work, but a wedged server must not
#: hang the engine forever
_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)

_CLIENT: httpx.AsyncClient | None = None


def _shared_client() -> httpx.AsyncClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = httpx.AsyncClient(timeout=_TIMEOUT)
    return _CLIENT


class OpenAICompatLLM(LLMAdapter):
    def __init__(self, model: str, max_tokens: int = 1024,
                 reasoning_effort: str | None = None) -> None:
        """`reasoning_effort`: None = the server's default (thinking models think — right for
        the judge seat); "none" = suppress thinking (the ACTOR seat: dialogue is the fast
        System-1 role, ~1.5s vs ~30s on gemma-4 — deliberation belongs to the judge)."""
        self._model = model
        self._max_tokens = max_tokens
        self._reasoning = reasoning_effort
        self._base = os.environ.get("LOCAL_JUDGE_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
        self._key = os.environ.get("LOCAL_JUDGE_API_KEY", "")

    async def stream_reply(
        self, messages: list[dict], system="", *, cache_messages: bool = False
    ) -> AsyncIterator[str]:
        # `system` may be a list of cache-segmented blocks (Anthropic prompt-caching shape) —
        # concatenation equals the original string, so the local model sees identical text.
        sys_text = system if isinstance(system, str) else "\n".join(s for s in system if s)
        msgs = ([{"role": "system", "content": sys_text}] if sys_text else []) + messages
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        body = {"model": self._model, "messages": msgs, "max_tokens": self._max_tokens,
                "stream": False}
        if self._reasoning:
            body["reasoning_effort"] = self._reasoning
        r = await _shared_client().post(
            f"{self._base}/chat/completions", headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        if text:
            yield text
