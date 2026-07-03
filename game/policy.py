"""GAME-side policy shared by every embodiment surface (grid arena, Unity bridge) so the two
treatment arms can never drift apart. This is game policy, NOT engine behavior — the engine
appraises salience; what salience is WORTH (interrupt? speak?) and how names travel are the
game's calls (docs/engine-game-contract.md).

Pure functions + constants only: no I/O, no engine imports — trivially testable."""
from __future__ import annotations

import re

# ---- react recipe policy (calibrated live 2026-07-01; see game/arena/game.py history) --------
# Vigilant characters RECALL nearly everything a stranger does (~0.72 appraisal floor — that's
# character-true; recall is what salience measures), so the interrupt bar sits above the floor.
REACT_SALIENCE = 0.75   # below: noticed + remembered, but the scene isn't interrupted
SPEAK_SALIENCE = 0.9    # at/above: the reaction earns WORDS, not just a move

# The game's coarse OBJECTIVE scale per act kind — the #25 magnitude hint. Without it the
# appraiser rated even crossing a room at 0.7-0.8 for three of four NPCs.
OBJ_MAGNITUDE = {"move": 0.1, "approach": 0.1, "watch": 0.15, "use": 0.25}


def react_verdict(salience: float) -> str:
    """Map an NPC's own appraised salience to the game's reaction tier: '' | 'act' | 'speak'."""
    if salience >= SPEAK_SALIENCE:
        return "speak"
    if salience >= REACT_SALIENCE:
        return "act"
    return ""


def flinch(salience: float) -> bool:
    """The pre-deliberative orienting response: does the moment of WITNESSING itself register on
    the body (head turn, widened eyes) before any deliberation? Proportional to the witness's own
    appraised salience — the orienting reflex is near-universal; personality differentiates in the
    deliberate step that follows, not here."""
    return salience >= REACT_SALIENCE


def as_observed(conseq: str) -> str:
    """Third-person a consequence phrase for an onlooker ('stoke the peat fire' -> 'stokes the
    peat fire'); phrases already conjugated ('crosses to the bar') pass through."""
    w = conseq.split()
    if w and not w[0].endswith("s"):
        w[0] += "es" if w[0].endswith(("sh", "ch", "x", "o")) else "s"
    return " ".join(w)


# ---- name / acquaintance policy ---------------------------------------------------------------

def split_quotes(text: str) -> list[str]:
    """Alternating [narration, quoted, narration, ...] segments — odd indices are quoted speech
    (straight or smart quotes)."""
    return re.split(r'("[^"]*"|“[^”]*”)', text or "")


def learnable_forms(character_name: str) -> list[str]:
    """The forms an INTRODUCTION can teach: first name + quoted nickname — how people actually
    introduce themselves ('Name's Della', 'they call me Pockets'). Surnames are excluded because
    they double as common words ('\"Hale and hearty!\"' is capitalized at sentence start, so even
    case-sensitive matching would false-register Edwin \"Pockets\" Hale)."""
    raw = re.sub(r"\s*\([^)]*\)\s*$", "", character_name or "").strip()
    nicknames = re.findall(r'"([A-Za-z]{2,})"', raw)
    first = re.sub(r'"[^"]*"', " ", raw).split()
    return ([first[0]] if first else []) + nicknames


def spoken_name(character_name: str, text: str) -> str | None:
    """The name this reply just taught, or None: a learnable form of `character_name`, spoken
    aloud in QUOTED speech (an actual introduction — never a narration slip), case-sensitive."""
    spoken = " ".join(split_quotes(text)[1::2])
    if not spoken:
        return None
    for c in learnable_forms(character_name):
        if re.search(rf"\b{re.escape(c)}\b", spoken):
            return c
    return None


# ---- performance rules (how a character SPEAKS on an embodied surface) --------------------------
PERFORMANCE_RULES = (
    "Speak your words in the first person, in quotes. Write your OWN actions in the third person "
    "using a PRONOUN (he/she/they) — e.g. 'she brushes the rain off' — never the second person and "
    "NEVER your own name. Never narrate the player's actions, body, or feelings. The player's "
    "words are spoken TO YOU — a form of address like 'barkeep' or 'friend' means YOU, not a "
    "third person.")
