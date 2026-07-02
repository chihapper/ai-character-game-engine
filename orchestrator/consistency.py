"""Contradiction detection (issue #10). The performance directive already makes a character
NOTICE and react to contradictions in the moment (the LLM does this well once the relevant
memories are injected). This is the other half: a background check that RECORDS when the player
asserted something that clashes with what the character established earlier — so a caught lie or
inconsistency becomes a salient memory the character carries forward (and that recall + the
relationship can react to later). RR-aligned: a contradiction is high-relevance to a wary agent.

Runs off the critical path (in the post-turn reflect), opt-in, and only when there are memories
to contradict — so it costs nothing on a fresh slate. Returns None on no contradiction or error.
"""
from __future__ import annotations

import json
import logging
import re

from .character_store import Character
from .judgment import complete

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You check ONE thing: did the PLAYER's latest line assert a FACT that directly CONTRADICTS "
    "what the character already established (their memories below) or plainly knows — something "
    "that CANNOT BOTH BE TRUE (a changed name, a denied past event, an incompatible fact)?\n"
    "A claim the character merely DISTRUSTS or finds self-serving is NOT a contradiction unless it "
    "factually clashes with an established fact. In particular, 'I've changed', 'I did X for you', "
    "apologies, promises, and assertions of feeling or intent are NOT contradictions — even from "
    "someone the character has every reason to doubt. New information, vagueness, opinions, and "
    "harmless embellishment are NOT contradictions either.\n"
    "Return JSON ONLY: {\"contradiction\": null} if there is none, else "
    "{\"contradiction\": {\"claimed\": \"<what the player now asserts>\", "
    "\"remembered\": \"<the established fact it clashes with>\"}}. Be conservative — when unsure, null."
)


def _parse(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group())
    except (ValueError, TypeError):
        return None
    c = data.get("contradiction") if isinstance(data, dict) else None
    if not isinstance(c, dict):
        return None
    claimed, remembered = str(c.get("claimed") or "").strip(), str(c.get("remembered") or "").strip()
    return {"claimed": claimed, "remembered": remembered} if claimed and remembered else None


async def detect_contradiction(
    character: Character, user_text: str, memories: list[str], *, model: str | None = None,
) -> dict | None:
    """Does `user_text` contradict any of the established `memories`? Returns
    {"claimed", "remembered"} or None (also None when there's nothing to check or on error)."""
    if not user_text or not memories:
        return None
    prompt = (
        f"CHARACTER: {character.name}\n\n"
        "WHAT THE CHARACTER HAS ESTABLISHED:\n" + "\n".join(f"- {m}" for m in memories) +
        f"\n\nPLAYER'S LATEST LINE:\n{user_text}\n\nIs there a contradiction? JSON only."
    )
    try:
        return _parse(await complete(_SYSTEM, prompt, role="salience", model=model, max_tokens=160))
    except Exception:
        logger.exception("Contradiction detection failed; skipping")
        return None
