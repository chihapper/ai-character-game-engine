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
    "You output a single number, 0.00–1.00: how reliably a specific fictional character "
    "would RECALL this moment later. This is about retrievable memory, not drama.\n"
    "Two things make a moment recallable — take the HIGHER:\n"
    "1) EMOTIONAL/PERSONAL weight — it touches their goals, values, relationships, or "
    "fears. A warm character: more; a cold or guarded one: less.\n"
    "2) ROLE RELEVANCE — assume the character is COMPETENT at their job and expertise "
    "unless the profile clearly says otherwise. A competent professional reliably recalls "
    "facts in their domain EVEN WHEN ROUTINE — routine-ness does NOT make something "
    "forgettable for them. A bartender recalls a patron's drink order; a guard a face; a "
    "merchant a deal; a detective a detail.\n"
    "Calibration: pure filler / greetings → 0.0–0.1. Pleasant but inconsequential chatter "
    "→ 0.1–0.25. A fact a competent character would track in their role (a customer's "
    "order, a client's request, a detail in their expertise) → 0.6–0.8. A personally "
    "pivotal moment → 0.8–1.0. Do NOT rate a role-relevant fact low just because it is "
    "ordinary. Reply with ONLY the number."
)


def _character_summary(character: Character) -> str:
    """A compact 'who they are, their role, and what they care about' for the rater — must
    include role + expertise so it can judge role/competence salience (not the full prompt)."""
    bits: list[str] = [f"Name: {character.name}"]
    if character.concept:
        bits.append(character.concept)
    if character.role:
        bits.append(f"Role / job: {character.role}")
    if character.temperament:
        bits.append(f"Temperament: {character.temperament}")
    if character.knows:
        bits.append("Competent in / knows: " + "; ".join(character.knows))
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
        f"How reliably would {character.name} RECALL this later? Weigh both personal/"
        f"emotional weight and role relevance — a competent professional recalls facts in "
        f"their domain even when routine. Reply with only a number from 0.00 to 1.00."
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


# --- Commitment detection (issue #4-B): folded into the salience call ----------------------

_DETECT_SYSTEM = (
    "You analyze one exchange with a fictional character and return JSON ONLY — no prose.\n"
    'Return exactly: {"importance": <0.00-1.00>, "commitment": null | '
    '{"text": "<obligation from the character\'s POV>", "significance": <0.00-1.00>, '
    '"due": "<deadline if stated, else empty>"}}\n\n'
    "importance — how reliably THIS character would RECALL this moment later (memory, not "
    "drama). Take the higher of emotional/personal weight or role relevance; a competent "
    "professional recalls facts in their domain even when routine. Filler/greeting 0.0-0.1; "
    "a role-relevant fact 0.6-0.8; a personally pivotal moment 0.8-1.0.\n\n"
    "commitment — set ONLY if the CHARACTER (not the player) made a CONCRETE, durable promise, "
    "obligation, deal, or constraint they could later be held to (\"I'll meet you at dawn\", "
    "\"I won't tell anyone\", \"I'll pay off your debt\"). Write `text` as the obligation from "
    "the character's POV (\"meet the player at dawn\"); `significance` = how much honoring it "
    "matters to this character. Be CONSERVATIVE: hedges (\"maybe\", \"I'll think about it\"), "
    "pleasantries, hypotheticals, and anything the PLAYER said are NOT commitments → null."
)


def _parse_score_and_commitment(text: str) -> tuple[float, dict | None]:
    import json

    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return _parse_score(text), None
    try:
        d = json.loads(m.group())
    except (ValueError, TypeError):
        return _parse_score(text), None
    imp = d.get("importance")
    importance = max(0.0, min(1.0, float(imp))) if isinstance(imp, (int, float)) else NEUTRAL
    c = d.get("commitment")
    commitment = None
    if isinstance(c, dict) and str(c.get("text") or "").strip():
        sig = c.get("significance")
        commitment = {
            "text": str(c["text"]).strip(),
            "significance": max(0.0, min(1.0, float(sig))) if isinstance(sig, (int, float)) else 0.5,
            "due": str(c.get("due") or "").strip(),
        }
    return importance, commitment


async def score_and_detect(
    character: Character, user_text: str, assistant_text: str, *, model: str | None = None
) -> tuple[float, dict | None]:
    """One LLM call returning BOTH the salience importance (0–1) and any commitment the
    character just MADE in this reply (or None) — folded together so detection adds a few
    output tokens, not a new round-trip. Returns (NEUTRAL, None) when off or on error."""
    settings = get_settings()
    if not settings.salience_scoring and not settings.commitment_detection:
        return NEUTRAL, None
    prompt = (
        f"CHARACTER:\n{_character_summary(character)}\n\n"
        f"EXCHANGE:\nPlayer: {user_text}\n{character.name}: {assistant_text}\n\n"
        "Return the JSON described."
    )
    try:
        llm = AnthropicLLM(model=model or settings.salience_model, max_tokens=220)
        parts: list[str] = []
        async for delta in llm.stream_reply([{"role": "user", "content": prompt}], _DETECT_SYSTEM):
            parts.append(delta)
        return _parse_score_and_commitment("".join(parts))
    except Exception:
        logger.exception("Salience+detection failed; using neutral importance, no commitment")
        return NEUTRAL, None
