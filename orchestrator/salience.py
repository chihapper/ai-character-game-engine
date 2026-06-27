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


# --- Post-turn reflection: one folded call (salience + #4-B detection + #6 relationship) ----

_IMPORTANCE_BLOCK = (
    "importance — how reliably THIS character would RECALL this moment later (memory, not "
    "drama). Take the higher of emotional/personal weight or role relevance; a competent "
    "professional recalls facts in their domain even when routine. Filler/greeting 0.0-0.1; a "
    "role-relevant fact 0.6-0.8; a personally pivotal moment 0.8-1.0."
)

_COMMITMENT_BLOCK = (
    "commitment — set ONLY if the CHARACTER (not the player) STATED a concrete, durable "
    "promise, obligation, deal, or constraint they could be held to (\"I'll meet you at dawn\", "
    "\"I won't tell anyone\"). Write `text` as the obligation from the character's POV (\"meet "
    "the player at dawn\"); extract it even if they may be lying — they still SAID it. "
    "`significance` is CHARACTER-AWARE: an honest character weighs a promise heavily; a "
    "deceptive one who won't keep it weighs it lightly. Be CONSERVATIVE: hedges, pleasantries, "
    "hypotheticals, and anything the PLAYER said are NOT commitments → null."
)


def _relationship_block(rel) -> str:
    return (
        "relationship — how THIS exchange moved the character's feelings toward the player, as "
        "signed deltas (range -0.30..0.30). MOST EXCHANGES ARE 0.00 — feelings move rarely. "
        "Magnitude is judged by THIS CHARACTER'S NATURE, not the surface niceness:\n"
        "- A guarded, cynical, jaded, or proud character: routine pleasantries, flattery, and "
        "nice talk roll off like WATER OFF A DUCK'S BACK — they've seen it all; move them 0.00. "
        "ONLY rare, proven, costly things shift them — genuine sacrifice, loyalty proven over "
        "real time, being truly SEEN, or a real betrayal — and even then slowly (±0.05-0.15). "
        "Very few people ever get close to such a character.\n"
        "- A warm, open, lonely, or impulsive character moves more readily to ordinary warmth.\n"
        "affection_delta (colder/fonder), trust_delta (warier/more trusting), respect_delta "
        "(contempt/admiration). `mood` = their acute feeling right now, 1-2 words. "
        f"(Current standing, 0.5=baseline — affection {rel.affection:.2f}, trust {rel.trust:.2f}, "
        f"respect {rel.respect:.2f}.)"
    )


def _intent_block(intent) -> str:
    cur = f' (their current aim: "{intent.intent}")' if intent and intent.intent else " (none set yet)"
    return (
        "intent — the character's IMMEDIATE short-term aim with the player right now, beyond "
        "their standing profile goals. A concrete agenda from their POV (\"find out who sent "
        "them\", \"keep them close tonight\", \"test if they can be trusted with the ledger\", "
        "\"get rid of them\"). It EVOLVES — it may continue, sharpen, or change with the scene "
        "and their feelings. CHARACTER-AWARE: a schemer probes and uses; a lonely flirt wants to "
        "be chosen; a guarded one wants distance until trust is earned. Empty string if they have "
        "no particular agenda." + cur
    )


def _parse_reflection(text: str, want_commit: bool, want_rel: bool, want_intent: bool):
    import json

    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return _parse_score(text), None, None, None
    try:
        d = json.loads(m.group())
    except (ValueError, TypeError):
        return _parse_score(text), None, None, None
    imp = d.get("importance")
    importance = max(0.0, min(1.0, float(imp))) if isinstance(imp, (int, float)) else NEUTRAL
    commitment = None
    if want_commit and isinstance(d.get("commitment"), dict):
        c = d["commitment"]
        if str(c.get("text") or "").strip():
            sig = c.get("significance")
            commitment = {
                "text": str(c["text"]).strip(),
                "significance": max(0.0, min(1.0, float(sig))) if isinstance(sig, (int, float)) else 0.5,
                "due": str(c.get("due") or "").strip(),
            }
    relationship = None
    if want_rel and isinstance(d.get("relationship"), dict):
        r = d["relationship"]
        clamp = lambda x: max(-0.3, min(0.3, float(x))) if isinstance(x, (int, float)) else 0.0
        relationship = {
            "d_affection": clamp(r.get("affection_delta")), "d_trust": clamp(r.get("trust_delta")),
            "d_respect": clamp(r.get("respect_delta")), "mood": str(r.get("mood") or "").strip() or None,
        }
    intent = None
    if want_intent and isinstance(d.get("intent"), str):
        intent = d["intent"].strip() or None
    return importance, commitment, relationship, intent


async def reflect_on_turn(
    character: Character, user_text: str, assistant_text: str, *,
    relationship=None, intent=None, model: str | None = None,
) -> tuple[float, dict | None, dict | None, str | None]:
    """ONE background LLM call: salience importance, plus — when enabled — any commitment the
    character made (#4-B), how the exchange moved their feelings (#6), and their updated
    short-term intent (#8). Folded into a single call (~0 player latency). Returns (importance,
    commitment|None, relationship_update|None, intent|None); fallbacks are all-None."""
    settings = get_settings()
    want_commit = settings.commitment_detection
    want_rel = settings.relationship_state and relationship is not None
    want_intent = settings.intent_state and intent is not None
    if not settings.salience_scoring and not want_commit and not want_rel and not want_intent:
        return NEUTRAL, None, None, None
    fields = ['"importance": <0.00-1.00>']
    blocks = [_IMPORTANCE_BLOCK]
    if want_commit:
        fields.append('"commitment": null | {"text": "...", "significance": <0.00-1.00>, "due": "..."}')
        blocks.append(_COMMITMENT_BLOCK)
    if want_rel:
        fields.append('"relationship": {"affection_delta": <-0.3..0.3>, "trust_delta": '
                      '<-0.3..0.3>, "respect_delta": <-0.3..0.3>, "mood": "<1-2 words>"}')
        blocks.append(_relationship_block(relationship))
    if want_intent:
        fields.append('"intent": "<short aim from their POV, or empty>"')
        blocks.append(_intent_block(intent))
    system = ("You analyze one exchange with a fictional character and return JSON ONLY — no "
              "prose.\nReturn: {" + ", ".join(fields) + "}\n\n" + "\n\n".join(blocks))
    prompt = (f"CHARACTER:\n{_character_summary(character)}\n\n"
              f"EXCHANGE:\nPlayer: {user_text}\n{character.name}: {assistant_text}\n\n"
              "Return the JSON described.")
    try:
        llm = AnthropicLLM(model=model or settings.salience_model, max_tokens=380)
        parts: list[str] = []
        async for delta in llm.stream_reply([{"role": "user", "content": prompt}], system):
            parts.append(delta)
        return _parse_reflection("".join(parts), want_commit, want_rel, want_intent)
    except Exception:
        logger.exception("Reflection (salience/detect/relationship/intent) failed; neutral fallback")
        return NEUTRAL, None, None, None


async def score_and_detect(
    character: Character, user_text: str, assistant_text: str, *, model: str | None = None
) -> tuple[float, dict | None]:
    """Back-compat: salience + commitment only (no relationship/intent)."""
    importance, commitment, _, _ = await reflect_on_turn(character, user_text, assistant_text, model=model)
    return importance, commitment
