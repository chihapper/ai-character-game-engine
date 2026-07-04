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


def spoken_text(reply: str) -> str:
    """What the VOICE gets: only the quoted speech, with the surrounding third-person
    narration ('she leans forward...') silenced — stage business is for the body and the
    subtitle, never the mouth. Quotes are stripped (TTS reads bare text); inline [tags]
    inside quotes survive for the expressive providers. A reply with no quotes at all is
    treated as pure speech (some characters answer without stage business)."""
    parts = split_quotes(reply)
    quoted = [p[1:-1].strip() for p in parts[1::2] if len(p) >= 2]
    spoken = " ".join(q for q in quoted if q)
    return spoken if spoken else (reply or "").strip()


FACE_TAGS = {"happy", "sad", "angry", "fear", "surprise", "disgust"}


def parse_face_marks(postscript: str | None) -> list[dict]:
    """[[FACE happy@0 angry@0.6]] -> [{"frac": 0.0, "face": "happy"}, {"frac": 0.6, "face": "angry"}].
    Neutral, absent, or malformed -> [] (the face stays neutral — the default IS the design)."""
    if not postscript or not postscript.strip().lower().startswith("face"):
        return []
    marks = []
    for token in postscript.strip()[4:].replace(",", " ").split():
        tag, _, frac = token.partition("@")
        tag = tag.strip().lower()
        if tag not in FACE_TAGS:
            continue
        try:
            at = min(1.0, max(0.0, float(frac))) if frac else 0.0
        except ValueError:
            at = 0.0
        marks.append({"frac": at, "face": tag})
    marks.sort(key=lambda m: m["frac"])
    return marks


# ---- performance rules (how a character SPEAKS on an embodied surface) --------------------------
PERFORMANCE_RULES = (
    "Speak your words in the first person, in quotes. Write your OWN actions in the third person "
    "using a PRONOUN (he/she/they) — e.g. 'she brushes the rain off' — never the second person and "
    "NEVER your own name. Never narrate the player's actions, body, or feelings. The player's "
    "words are spoken TO YOU — a form of address like 'barkeep' or 'friend' means YOU, not a "
    "third person. "
    "End your reply with ONE line noting what shows on your face while you speak: [[FACE neutral]] "
    "for most lines — or, when the moment genuinely reaches you, a tag from happy/sad/angry/fear/"
    "surprise/disgust with the fraction of the line where it appears, e.g. [[FACE happy@0]] — and "
    "if your face TURNS mid-line, list the change: [[FACE happy@0 angry@0.6]]. What surfaces must "
    "fit WHO YOU ARE: some faces stay guarded even when moved; some people smile at the wrong "
    "things. This line is stage machinery — never spoken, never referenced.")
