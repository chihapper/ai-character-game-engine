"""Performance tags for spoken delivery — tone, vocal delivery, non-verbals, pauses.

The LLM directs its own performance with bracketed tags ([sarcastic], [whispering],
[laughs], [pause]). We deliberately DO NOT normalize these to a fixed vocabulary —
that only existed to feed Cartesia's categorical emotion enum, which we've dropped.
Instead the model's own directions pass through to the instruction-following voices
with maximal fidelity:

  * ElevenLabs v3 — inline audio tags, anywhere in the line.
  * Inworld TTS-2 — a LEADING bracket is read as natural-language steering; a bare
    adjective is wrapped into an instruction ("[sound cold]") for best effect.
  * Cartesia (deprecated) — categorical only; it just renders [laughter] and drops
    the rest. No emotion control without the old vocab.

Physical stage directions ([glares], [sits back]) are dropped everywhere; non-verbal
sounds map to each provider's token; dramatic pauses become real engine silence
(durations in timing.py). Game-agnostic — this is performance, not game logic.
"""
from __future__ import annotations

import re

from .timing import PAUSE_HINT_MS, PAUSE_TAG_MS

# Non-verbal sound roots -> (Cartesia, Inworld, ElevenLabs) tokens. Substring match,
# so "[nervous laugh]" / "[bitter chuckle]" still resolve. None = no equivalent.
_NONVERBAL_ROOTS: dict[str, tuple[str | None, str | None, str | None]] = {
    "laugh":   ("[laughter]", "[laugh]", "[laughs]"),
    "chuckle": ("[laughter]", "[laugh]", "[laughs]"),
    "giggle":  ("[laughter]", "[laugh]", "[giggles]"),
    "snicker": ("[laughter]", "[laugh]", "[laughs]"),
    "scoff":   (None, None, "[scoffs]"),
    "sigh":    (None, "[sigh]", "[sighs]"),
    "breath":  (None, "[breathe]", "[exhales]"),
    "exhale":  (None, "[breathe]", "[exhales]"),
    "gasp":    (None, None, "[gasps]"),
    "cough":   (None, "[cough]", None),
    "yawn":    (None, "[yawn]", None),
    "throat":  (None, "[clear throat]", "[clears throat]"),
    "cry":     (None, None, "[crying]"),
    "sob":     (None, None, "[crying]"),
}
_PROVIDER_IDX = {"cartesia": 0, "inworld": 1, "elevenlabs": 2}

# Physical-action verbs that mark a bracket as a STAGE DIRECTION (something the
# character does, not how they sound), so we drop it. Ambiguous vocal verbs like
# "lowers"/"raises" (the voice) are intentionally excluded so vocal directions survive.
_ACTION_WORDS = frozenset(
    """sits sit sat leans lean leaned leaning glares glare glared glaring drums
    drumming taps tapping turns turn turned turning steps step stepped walks walk
    walked crosses cross crossed slams slam slammed nods nod nodded shrugs shrug
    points pointing gestures gesturing paces pacing stands stood reaches reaching
    grabs grabbing folds folded stares staring rises rose glances glance smirks smirk
    frowns frown scowls winks wipes rubs clenches grips throws tosses pours slides
    picks shoulders pushes pulls reclines flops slumps stiffens""".split()
)

# Verbs that already make a bracket an instruction for Inworld (so we don't re-wrap).
_STEER_VERBS = frozenset(
    """say says speak speaks sound sounds whisper whispers whispering shout shouts
    shouting lower lowers lowered raise raises sing sings singing give gives talk
    talks growl growls hiss hisses murmur murmurs drawl drawls snarl snarls purr
    purrs mutter mutters yell yells hush soften softens""".split()
)

_BRACKET_RE = re.compile(r"\[([^\]\n]+)\]")
_LEAD_BRACKET_RE = re.compile(r"^\s*\[([^\]\n]+)\]\s*")


def parse_pause(text: str) -> tuple[int, str]:
    """Extra silence (ms) to hold BEFORE this line, for dramatic pacing, read from a
    leading bracket. Returns (extra_ms, rest). A pure pause tag is consumed; a
    pause-implying word inside a richer note adds a beat but is left in place."""
    m = _LEAD_BRACKET_RE.match(text)
    if not m:
        return 0, text
    inner = m.group(1).strip().lower()
    if inner in PAUSE_TAG_MS:
        return PAUSE_TAG_MS[inner], text[m.end():]
    extra = 0
    for hint, ms in PAUSE_HINT_MS.items():
        if hint in inner:
            extra = max(extra, ms)
    return extra, text


def _inworld_steer(direction: str) -> str:
    """Format a delivery direction as an Inworld steering instruction. A bare adjective
    ([cold]) becomes an instruction ([sound cold]); something already imperative
    ([lowers her voice to a whisper]) is kept as-is."""
    d = direction.strip().lower()
    head = d.split()[0] if d.split() else ""
    return f"[{d}]" if head in _STEER_VERBS else f"[sound {d}]"


def render_tags(text: str, provider: str) -> str:
    """Convert the model's bracket tags to what a provider can act on. Each bracket is
    split on commas and handled part by part:
    - non-verbal sounds (laugh, sigh, giggle, ...) -> the provider's token (or dropped)
    - physical stage directions ([glares at you]) -> dropped everywhere
    - delivery/emotion directions -> kept inline for ElevenLabs v3, and — when they
      LEAD the line — turned into steering for Inworld; dropped for Cartesia."""
    idx = _PROVIDER_IDX.get(provider, 0)

    def repl(m: re.Match) -> str:
        leading = text[: m.start()].strip() == ""
        sounds: list[str] = []
        directions: list[str] = []
        for raw in m.group(1).split(","):
            part = raw.strip()
            if not part:
                continue
            low = part.lower()
            matched_sound = False
            for root, tokens in _NONVERBAL_ROOTS.items():
                if root in low:
                    matched_sound = True
                    if tokens[idx]:
                        sounds.append(tokens[idx])
                    break
            if matched_sound:
                continue
            if set(low.split()) & _ACTION_WORDS:
                continue  # physical stage direction — never spoken or voiced
            directions.append(low)

        out: list[str] = []
        if directions:
            tone = ", ".join(directions)  # recombine a multi-word tone into one tag
            if provider == "elevenlabs":
                out.append(f"[{tone}]")  # v3 acts on inline tags anywhere
            elif provider == "inworld" and leading:
                out.append(_inworld_steer(tone))  # leading bracket = steering
            # cartesia: drop (categorical model, no free-form direction)
        out.extend(sounds)  # tone first, then the sound (e.g. "[sarcastic] [laughs]")
        return " ".join(out)

    return _BRACKET_RE.sub(repl, text).strip()


def has_speakable(text: str) -> bool:
    """True if there's anything worth sending to TTS (a letter/digit somewhere)."""
    return any(ch.isalnum() for ch in text)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def performance_directive(provider: str) -> str:
    """How-to-perform instructions for the LLM, tailored to the character's voice. The
    expressive providers get free rein; Cartesia (categorical) gets a simple set."""
    header = "# Performance tags (spoken aloud; the bracketed tags are never read out)\n"
    if provider == "cartesia":
        return (
            header
            + "Lead most lines with a simple one-word emotion ([angry], [sad], [excited]); "
            "you may use [laughs] where it fits. This voice can't whisper or perform other "
            "vocal directions, so keep tags simple."
        )
    return (
        header
        + "Direct your own delivery with bracketed tags, placed exactly where they apply:\n"
        + "- Lead most lines with a TONE/EMOTION — any word that fits the moment: "
        "[sarcastic], [cold], [tender], [playful but firm], [wry], [grave], [giddy], [defeated].\n"
        + "- Add DELIVERY where it sharpens things: [whispering], [shouting], [breathless], "
        "[low and menacing], [trembling], [drawn out], [clipped].\n"
        + "- Drop in SOUNDS where natural: [laughs], [giggles], [sighs], [scoffs], [gasps], [exhales].\n"
        + "- TIMING: put [pause] or [long pause] on its own line before a weighty or final "
        "line — the engine holds a real beat of silence there.\n"
        + "Let the tone shift line to line; match every tag to the words; never stay flat. "
        "Do NOT narrate physical actions (no [sits back], [glares]) — you are only a voice."
    )
