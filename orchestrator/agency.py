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
        "GROUND YOURSELF IN THE RECORD: base anything you say about the player ONLY on what the "
        "record below shows they actually did. You may interpret real events naturally — a person "
        "misremembers and conflates, that's human — but do NOT invent contact, words, or actions "
        "from the player that never happened. Before you decide, REGISTER in your reflection the most "
        "significant thing(s) that have happened to you recently — name them, even if they don't "
        "change your goals. Do NOT tunnel on one thread (like the player) and ignore a major event "
        "(a death, a betrayal, a loss, a real opportunity).\n"
        "Return JSON ONLY:\n"
        "{\"reflection\": \"<their first-person reasoning, 1-2 sentences>\", "
        "\"changed\": <true|false>, "
        "\"internal\": \"<a shift in how they regard the PLAYER that they genuinely arrive at. It must "
        "be COHERENT and grounded — a real reckoning, never random noise that swings up one week and "
        "down the next. WEIGH ANY PLAYER ABSENCE through THIS character and what was actually "
        "established: passing contact with no real promise -> absence is just drifting to neutral over "
        "time, leave empty (decay handles it); but promises this character took to heart — or warmth "
        "they reasonably read AS a promise (people do this, especially when they fear being left) — "
        "mean the player's silence can genuinely sting, cool, or wound. Conversely, a player who keeps "
        "SHOWING UP — loyalty demonstrated over time, not merely promised — can let even a guarded "
        "character finally warm and trust them; that trust is earned, not given. People aren't always "
        "rational; judge it as THEY would, not as a fair arbiter would. Often empty.>\", "
        "\"new_intent\": \"<their updated near-term aim, or empty>\", "
        "\"new_goals\": [<their updated STANDING life-goals if their direction has shifted, or empty>], "
        "\"world_action\": \"<an outward action for the GAME to enact, e.g. 'leaves the harbor for the "
        "cliff abbey' — or empty>\"}\n"
        "`internal` is a rare, decisive change of heart toward the player (the engine applies it — it "
        "can heal or deepen a scar); `world_action` is something the GAME makes happen in its world. "
        "When changed=false, leave the change fields empty."
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
