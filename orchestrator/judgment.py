"""The shared "focused judgment call" (arch review theme C): one place for the pattern every
cognitive faculty repeats — pick the model for a ROLE, stream a one-shot prompt, accumulate, parse
JSON, and SALVAGE what's recoverable when the output is truncated or malformed.

Before this module the call/parse/except block was copy-pasted 9× (salience ×4, agency ×3,
consolidation, consistency) and only `deliberate()` recovered anything from truncated JSON — the
other eight silently lost the whole judgment. Every faculty now gets client reuse (see
adapters.llm_anthropic._shared_client) and truncation salvage for free.

NOTE: the character MIND is deliberately Anthropic-backed (judgments are tuned on Claude); the
injected `Engine(llm=...)` adapter powers only the spoken reply. This module is that decision's
single home — swap the provider here, not in nine places.
"""
from __future__ import annotations

import json
import logging
import re

from .adapters.llm_anthropic import AnthropicLLM
from .config import get_settings

logger = logging.getLogger(__name__)

#: role -> Settings field holding the model id. One table, so "which model does the salience
#: judgment use?" has exactly one answer (previously: config fields read inside helpers, explicit
#: args, AND the sandbox mutating globals — three competing routes).
_ROLE_MODELS = {
    "salience": "salience_model",
    "deliberation": "deliberation_model",
    "reflection": "reflection_model",
}


def model_for(role: str, override: str | None = None) -> str:
    """Resolve the model id for a judgment role ('salience' | 'deliberation' | 'reflection')."""
    if override:
        return override
    return getattr(get_settings(), _ROLE_MODELS[role])


#: Reasoning allowance added to every judgment call's visible-output budget. Models that think
#: by default (sonnet-5+) spend thinking tokens INSIDE max_tokens; the callers' budgets are
#: sized for the JSON alone, so without headroom a hard moment's thinking can consume the whole
#: cap and the judgment arrives EMPTY — silently, at exactly the beats that matter most (found
#: 2026-07-16: the sonnet-5 lich rerun scored a witnessed total betrayal as a no-op this way).
#: Harmless for non-thinking models: max_tokens is a ceiling, not a target.
_THINKING_HEADROOM = 2048
#: One retry with this much extra room when a judgment still comes back empty.
_EMPTY_RETRY_BOOST = 4096


async def complete(system: str | list, prompt: str, *, role: str = "salience",
                   model: str | None = None, max_tokens: int = 240) -> str:
    """One-shot streamed completion with the role-resolved model and the shared client. `system`
    may be a list to opt its stable prefix into prompt caching (see AnthropicLLM._system_param).
    Raises on transport errors — the caller owns the fallback semantics. `max_tokens` is the
    VISIBLE-output budget; a thinking allowance is added on top (see _THINKING_HEADROOM).
    An empty completion is never returned silently: it is retried once with more room, then
    logged as a warning — a mute judge must be a visible event, not a neutral no-op."""
    resolved = model_for(role, model)

    async def _once(budget: int) -> str:
        llm = AnthropicLLM(model=resolved, max_tokens=budget)
        parts: list[str] = []
        async for delta in llm.stream_reply([{"role": "user", "content": prompt}], system):
            parts.append(delta)
        return "".join(parts)

    text = await _once(max_tokens + _THINKING_HEADROOM)
    if not text.strip():
        logger.warning("%s judgment returned NO text (model=%s, budget=%d) — likely thinking "
                       "consumed the cap; retrying with +%d",
                       role, resolved, max_tokens + _THINKING_HEADROOM, _EMPTY_RETRY_BOOST)
        text = await _once(max_tokens + _THINKING_HEADROOM + _EMPTY_RETRY_BOOST)
        if not text.strip():
            logger.warning("%s judgment EMPTY after retry (model=%s) — caller falls back neutral",
                           role, resolved)
    return text


def salvage_json(text: str) -> dict | None:
    """Best-effort recovery when a JSON object is truncated or malformed (e.g. a long field blew
    max_tokens and the object never closed): pull every COMPLETE top-level `"key": value` pair —
    strings, booleans, numbers, and flat string-arrays — rather than dropping the whole judgment.
    A field cut mid-string is simply absent. Generalized from agency's decision salvage."""
    out: dict = {}
    for m in re.finditer(r'"(\w+)"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL):
        try:
            out[m.group(1)] = json.loads(f'"{m.group(2)}"')  # unescape
        except ValueError:
            out[m.group(1)] = m.group(2)
    for m in re.finditer(r'"(\w+)"\s*:\s*(true|false)\b', text):
        out.setdefault(m.group(1), m.group(2) == "true")
    for m in re.finditer(r'"(\w+)"\s*:\s*(-?\d+(?:\.\d+)?)\s*[,}\n]', text):
        out.setdefault(m.group(1), float(m.group(2)))
    for m in re.finditer(r'"(\w+)"\s*:\s*\[((?:\s*"(?:[^"\\]|\\.)*"\s*,?)*)\]', text, re.DOTALL):
        out.setdefault(m.group(1), re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(2)))
    return out or None


def parse_json(text: str) -> dict | None:
    """Extract + parse the first JSON object in `text`; fall back to salvage on failure."""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if m:
        try:
            d = json.loads(m.group())
            if isinstance(d, dict):
                return d
        except (ValueError, TypeError):
            pass
    return salvage_json(text or "")


async def judgment(system: "str | list", prompt: str, *, role: str = "salience", model: str | None = None,
                   max_tokens: int = 240, what: str = "judgment") -> dict | None:
    """The full pattern: complete -> parse JSON -> salvage on truncation -> None on error (logged).
    `what` names the judgment in the failure log."""
    try:
        return parse_json(await complete(system, prompt, role=role, model=model,
                                         max_tokens=max_tokens))
    except Exception:
        logger.exception("%s failed; caller falls back", what)
        return None
