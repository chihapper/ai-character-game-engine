"""Reflection / consolidation (issue #9): periodically compress raw exchanges into higher-level
BELIEFS — the through-lines a character forms from experience ("the player keeps choosing me
over the easy score; I think they're actually loyal", "no one down here is what they seem").
Generative-agents style.

Why this is RR-core, not a feature bolt-on: forming higher-order abstractions IS relevance
realization. A pile of episodic exchanges is low-level; the agent's job is to compress them into
convictions that bear on its goals far more directly than any single line — and those convictions
then condition what it later finds relevant and how it behaves. See [[relevance-realization-design]].

A belief is stored as an ordinary memory (kind="belief") with high importance, so it (a) persists
with a long decay half-life — beliefs are through-lines, not trivia — and (b) surfaces through the
normal arena query like anything else, competing for relevance. No separate retrieval path.

One background LLM call, fired only when enough has happened (importance-accumulation trigger), so
it's off the player's critical path and infrequent. Falls back to no beliefs on any error.
"""
from __future__ import annotations

import json
import logging
import re

from .character_store import Character
from .config import get_settings
from .judgment import complete
from .salience import _character_summary

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are the private, reflective inner voice of a fictional character. You are handed the "
    "recent things that have happened to them and, standing back, you name the DURABLE BELIEFS "
    "that have formed — the through-lines, not a recap.\n"
    "Each belief is ONE first-person sentence, in the character's own voice, that:\n"
    "- is bigger than any single event — a conviction, suspicion, realization, or resolve;\n"
    "- is grounded in the events given (no inventing facts);\n"
    "- is shaped by WHO THIS CHARACTER IS — their values and fears decide what they take from "
    "the same events (a trusting soul concludes warmth where a cynic concludes leverage).\n"
    "Return JSON ONLY: {\"beliefs\": [\"...\", ...]} with 1-3 of them, or {\"beliefs\": []} if "
    "nothing has risen above ordinary noise yet. Prefer few, real beliefs over many shallow ones."
)


def _parse_beliefs(text: str) -> list[str]:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group())
    except (ValueError, TypeError):
        return []
    out: list[str] = []
    for b in data.get("beliefs", []) if isinstance(data, dict) else []:
        s = str(b).strip()
        if s:
            out.append(s)
    return out[:3]


async def consolidate_beliefs(
    character: Character, recent: list[str], *, existing: list[str] | None = None,
    model: str | None = None,
) -> list[str]:
    """Synthesize 1-3 durable beliefs from `recent` events (and, if given, the beliefs already
    held, so convictions can deepen or shift). Returns [] when nothing rises above the noise or
    on any error — so consolidation never breaks a turn."""
    if not recent:
        return []
    settings = get_settings()
    prompt = (
        f"WHO YOU ARE:\n{_character_summary(character)}\n\n"
        "RECENT EVENTS (oldest first):\n" + "\n".join(f"- {m}" for m in recent) +
        (("\n\nBELIEFS YOU ALREADY HOLD (deepen, revise, or leave them):\n"
          + "\n".join(f"- {b}" for b in existing)) if existing else "") +
        "\n\nWhat do you now believe? JSON only."
    )
    try:
        return _parse_beliefs(await complete(_SYSTEM, prompt, role="reflection", model=model,
                                             max_tokens=320))
    except Exception:
        logger.exception("Belief consolidation failed; no beliefs formed this cycle")
        return []
