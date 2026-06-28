"""Autonomous agency / deliberation (issue #20): the GENERATOR half of a living NPC. Between
scenes — the player NOT present — the character decides, on its own, what (if anything) it does or
how it changes, grounded in everything that has accumulated (memory, beliefs, relationship, scars,
intent, goals, time). The ENGINE applies the inner half through the seams already built (the #19
self-change path, intent, goals) and hands the outward `world_action` back to the game to enact.

People don't transform on a whim: in the default GATED mode most deliberations return
`changed=false` (the character continues as they are) and a real change needs accumulated CAUSE.
FREE mode lowers that bar for emergence-friendly games. The grounding IS the guardrail — a decision
must be true to this character. One LLM call, only when the game asks. Returns None on error.
"""
from __future__ import annotations

import json
import logging
import re

from .adapters.llm_anthropic import AnthropicLLM
from .character_store import Character
from .config import get_settings

logger = logging.getLogger(__name__)


def _parse_decision(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group())
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    goals = d.get("new_goals")
    return {
        "reflection": str(d.get("reflection") or "").strip(),
        "changed": bool(d.get("changed")),
        "internal": str(d.get("internal") or "").strip(),
        "new_intent": str(d.get("new_intent") or "").strip(),
        "new_goals": [str(g).strip() for g in goals if str(g).strip()] if isinstance(goals, list) else [],
        "world_action": str(d.get("world_action") or "").strip(),
    }


async def deliberate(
    character: Character, *, grounding: str, mode: str = "gated", model: str | None = None,
) -> dict | None:
    """Decide what this character does/becomes on its own. `grounding` is the assembled state the
    engine passes; `mode` is 'gated' (default) or 'free'. Returns a Decision dict or None."""
    settings = get_settings()
    bar = (
        "Most of the time return changed=false — people don't transform on a whim; a real change "
        "needs accumulated CAUSE (weariness, beliefs that have drifted, an unresolved wound, time)."
        if mode != "free" else
        "FREE mode: the character may change more readily and follow emergent impulses — but it must "
        "still be plausible for who they are."
    )
    system = (
        "You are the autonomous inner life of a fictional character BETWEEN scenes — the player is "
        "NOT present. From who they are and everything that has accumulated, decide what, if "
        f"anything, they choose to do or how they change ON THEIR OWN. {bar} Any change must be TRUE "
        "to this character and grounded in what's given — never arbitrary.\n"
        "Return JSON ONLY:\n"
        "{\"reflection\": \"<their first-person reasoning, 1-2 sentences>\", "
        "\"changed\": <true|false>, "
        "\"internal\": \"<a change of heart toward the player they reach on their own — letting go "
        "of a grudge, warming, hardening — or empty>\", "
        "\"new_intent\": \"<their updated near-term aim, or empty>\", "
        "\"new_goals\": [<their updated STANDING life-goals if their direction has shifted, or empty>], "
        "\"world_action\": \"<an outward action for the GAME to enact, e.g. 'leaves the harbor for the "
        "cliff abbey' — or empty>\"}\n"
        "`internal` is forgiveness/warming/hardening the character arrives at themselves (the engine "
        "applies it — it can heal or deepen a scar); `world_action` is something the GAME makes "
        "happen in its world. When changed=false, leave the change fields empty."
    )
    prompt = (f"WHO YOU ARE + WHAT HAS ACCUMULATED:\n{grounding}\n\n"
              "What, if anything, do you do or become now? JSON only.")
    try:
        llm = AnthropicLLM(model=model or settings.deliberation_model, max_tokens=400)
        parts: list[str] = []
        async for delta in llm.stream_reply([{"role": "user", "content": prompt}], system):
            parts.append(delta)
        return _parse_decision("".join(parts))
    except Exception:
        logger.exception("Deliberation failed; no decision this cycle")
        return None
