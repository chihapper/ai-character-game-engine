"""Character-aware salience scoring — how memorable a moment is TO THIS character.

Relevance is relative to the agent (relevance realization): the same event is pivotal for
one character and forgettable for another. So when a memory is stored, we score its
`importance` from the character's own profile — a caring Bri holds onto the player's
brother's death; a cold, self-absorbed Corvin barely registers it. This is what lets
old-but-pivotal memories survive recency decay (GitHub issue #3).

A small LLM call rates the moment 0–1 against a compact character summary. It runs in the
background (off the critical path; see pipeline / main), so its latency never reaches the
user. Falls back to a neutral score on any error, so memory writes never fail because of it.
"""
from __future__ import annotations

import logging
import re

from .adapters.llm_anthropic import AnthropicLLM
from .character_store import Character
from .config import get_settings

logger = logging.getLogger(__name__)

NEUTRAL = 0.5  # fallback when scoring is off or fails

_SYSTEM = (
    "You rate how memorable a single moment is to a specific fictional character — how "
    "much THEY, given their personality and what they care about, would hold onto it. "
    "Not how dramatic it is in the abstract; how much it matters to THEM. A warm, caring "
    "character finds a lot salient; a cold, self-absorbed, or guarded one finds little "
    "salient unless it touches their own goals, fears, or interests. Reply with ONLY a "
    "number from 0.00 (instantly forgotten) to 1.00 (deeply significant, never forgotten)."
)


def _character_summary(character: Character) -> str:
    """A compact 'who they are and what they care about' for the rater (not the full prompt)."""
    bits: list[str] = [f"Name: {character.name}"]
    if character.concept:
        bits.append(character.concept)
    if character.temperament:
        bits.append(f"Temperament: {character.temperament}")
    if character.goals:
        bits.append("Cares about / wants: " + "; ".join(character.goals))
    if character.disposition:
        bits.append(f"Current stance toward the player: {character.disposition}")
    if character.relationships:
        rel = "; ".join(f"{who}: {how}" for who, how in character.relationships.items() if how)
        if rel:
            bits.append("Relationships: " + rel)
    return "\n".join(bits)


def _parse_score(text: str) -> float:
    m = re.search(r"\d*\.?\d+", text or "")
    if not m:
        return NEUTRAL
    try:
        return max(0.0, min(1.0, float(m.group())))
    except ValueError:
        return NEUTRAL


async def score_salience_text(
    character: Character, moment: str, *, model: str | None = None
) -> float:
    """Rate, 0–1, how memorable `moment` (any stored memory text) is to `character`.
    Returns NEUTRAL when scoring is disabled or on error."""
    settings = get_settings()
    if not settings.salience_scoring:
        return NEUTRAL
    prompt = (
        f"CHARACTER:\n{_character_summary(character)}\n\n"
        f"MOMENT:\n{moment}\n\n"
        f"How salient is this moment to {character.name}? Consider whether it touches "
        f"their goals, values, relationships, or fears, and whether they'd dwell on it or "
        f"forget it by tomorrow. Reply with only a number from 0.00 to 1.00."
    )
    try:
        llm = AnthropicLLM(model=model or settings.salience_model, max_tokens=16)
        parts: list[str] = []
        async for delta in llm.stream_reply([{"role": "user", "content": prompt}], _SYSTEM):
            parts.append(delta)
        return _parse_score("".join(parts))
    except Exception:
        logger.exception("Salience scoring failed; using neutral importance")
        return NEUTRAL


async def score_salience(
    character: Character, user_text: str, assistant_text: str, *, model: str | None = None
) -> float:
    """Rate, 0–1, how memorable this exchange is to `character`."""
    moment = f"Player: {user_text}\n{character.name}: {assistant_text}"
    return await score_salience_text(character, moment, model=model)
