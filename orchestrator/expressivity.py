"""Emotional expressivity for spoken delivery.

The LLM tags each line with a bracketed emotion (e.g. "[angry] You think you can
walk in here?"). We parse that tag, map it to per-provider controls, and let each
TTS adapter render it its own way — Cartesia via `generation_config` (a parameter),
Inworld via natural-language `[steering]` (inline). The emotion words are chosen to
be valid Cartesia emotion-enum values so Cartesia can use them directly.

Also handles inline non-verbal sounds ([laugh], [sigh], ...): each adapter rewrites
them to the tokens its model supports and drops the ones it doesn't.

Kept deliberately small and game-agnostic; this is performance, not game logic.
"""
from __future__ import annotations

import re

from .timing import PAUSE_HINT_MS, PAUSE_TAG_MS

# emotion -> (speed mult, volume mult, Inworld steering phrase, ElevenLabs v3 tag).
# The key itself is the Cartesia `generation_config.emotion` value. Speed/volume
# stay within Cartesia's ranges (speed 0.6-1.5, volume 0.5-2.0). The ElevenLabs tag
# is wrapped in brackets and prepended ("" = no tag).
EMOTIONS: dict[str, tuple[float, float, str, str]] = {
    "neutral":      (1.00, 1.00, "speak in a level, neutral tone", ""),
    "happy":        (1.05, 1.10, "speak brightly and happily", "happily"),
    "excited":      (1.15, 1.20, "speak with bright, fast excitement", "excited"),
    "content":      (1.00, 1.00, "speak warmly and content", "warmly"),
    "calm":         (0.95, 0.95, "speak calmly and evenly", "calm"),
    "affectionate": (0.97, 1.00, "speak softly and tenderly", "tenderly"),
    "curious":      (1.03, 1.00, "speak with lively curiosity", "curious"),
    "sad":          (0.90, 0.85, "speak sadly, low and heavy", "sad"),
    "melancholic":  (0.90, 0.85, "speak wistfully and subdued", "sorrowful"),
    "disappointed": (0.95, 0.90, "speak with quiet disappointment", "disappointed"),
    "angry":        (1.08, 1.25, "speak with hard, simmering anger", "angry"),
    "frustrated":   (1.05, 1.15, "speak with tight frustration", "frustrated"),
    "sarcastic":    (1.00, 1.00, "speak with dry, cutting sarcasm", "sarcastic"),
    "scared":       (1.12, 0.90, "speak fearfully, voice tight", "fearful"),
    "anxious":      (1.10, 0.95, "speak anxiously and unsteadily", "nervous"),
    "surprised":    (1.08, 1.10, "speak with sudden surprise", "surprised"),
    "determined":   (1.00, 1.10, "speak with firm determination", "firm"),
    "confident":    (1.00, 1.10, "speak with calm confidence", "confident"),
}

# Non-verbal sound roots -> (Cartesia, Inworld, ElevenLabs) tokens. Matched by
# substring so a model's variant like "[nervous laugh]" or "[bitter chuckle]" still
# resolves to a laugh. None = the provider has no equivalent, so it's dropped there.
_NONVERBAL_ROOTS: dict[str, tuple[str | None, str | None, str | None]] = {
    "laugh":   ("[laughter]", "[laugh]", "[laughs]"),
    "chuckle": ("[laughter]", "[laugh]", "[laughs]"),
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

# A leading bracket whose FIRST word is an emotion — also matches when the model
# bundles a stage note in, e.g. "[Anxious, fingers drumming against the sill]".
_EMOTION_RE = re.compile(r"^\s*\[\s*([a-zA-Z]+)[^\]\n]*\]\s*")
# Any inline bracket tag (may contain commas / multiple words).
_BRACKET_RE = re.compile(r"\[([^\]\n]+)\]")


def parse_emotion(text: str) -> tuple[str | None, str]:
    """Pull a leading emotion off a line. Returns (emotion or None, rest). Matches
    the emotion even when it's the first word of a longer bracket (the rest, usually
    a stage direction, is consumed with it). A leading non-verbal like `[sigh]` or a
    non-emotion tag like `[whispering]` is left in place for the adapters."""
    m = _EMOTION_RE.match(text)
    if m:
        word = m.group(1).lower()
        if word in EMOTIONS:
            return word, text[m.end():]
    return None, text


# Dramatic pauses the engine renders as real silence before a line. Durations live
# in timing.py (PAUSE_TAG_MS / PAUSE_HINT_MS). A "pure" pause tag ([long pause]) is
# consumed and contributes its full gap; a pause-implying word inside a richer note
# ([final, quiet]) just adds a beat and the bracket stays put.
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


def controls_for(emotion: str | None) -> tuple[str | None, float | None, float | None]:
    """(cartesia_emotion, speed, volume) for an emotion, or (None, None, None)."""
    if not emotion or emotion not in EMOTIONS:
        return None, None, None
    speed, volume = EMOTIONS[emotion][0], EMOTIONS[emotion][1]
    return emotion, speed, volume


def steering_for(emotion: str | None) -> str | None:
    """The Inworld natural-language steering instruction for an emotion."""
    if not emotion or emotion not in EMOTIONS:
        return None
    return EMOTIONS[emotion][2]


def el_tag_for(emotion: str | None) -> str | None:
    """The ElevenLabs v3 audio tag for an emotion (without brackets), or None."""
    if not emotion or emotion not in EMOTIONS:
        return None
    return EMOTIONS[emotion][3] or None


_EMOTION_LIST = ", ".join(EMOTIONS)


def performance_directive(provider: str) -> str:
    """The how-to-perform instructions for the LLM, tailored to the character's voice
    provider so it only emits tags that voice can actually render (no mix-ups: a
    Cartesia character isn't told to whisper; an ElevenLabs one is told to go wild)."""
    header = "# Performance tags (spoken aloud; the bracketed tags are never read out)\n"
    emotion = (
        "Start MOST sentences with an EMOTION that fits the moment, from this list: "
        f"{_EMOTION_LIST}. Put it first, e.g. \"[angry] You think you can just walk in "
        "here?\" Let the emotion shift line to line as the scene moves; never stay flat."
    )
    pacing = (
        "\nFor dramatic timing, put [pause] or [long pause] on its own line before a "
        "weighty or final line — the engine holds a real beat of silence there."
    )
    if provider == "elevenlabs":
        return (
            header
            + "Your voice is highly expressive — direct it freely with bracketed tags:\n"
            + f"- {emotion}\n"
            + "- For nuance, add delivery tags inline where they fit: [whispering], "
            "[shouting], [breathless], [trembling], [low and menacing], [drawn out].\n"
            + "- Use natural sounds where they fit: [laughs], [sighs], [nervous laugh], "
            "[scoffs], [gasps], [exhales].\n"
            + "Match every tag to the words. Example: \"[whispering] I shouldn't even be "
            "telling you this... [nervous laugh] forget I said anything.\""
            + pacing
        )
    if provider == "inworld":
        return (
            header
            + emotion
            + "\nYou may also use natural sounds inline where they fit: [laughs], "
            "[sighs], [breathes], [coughs], [yawns], [clears throat]."
            + pacing
        )
    # cartesia and any default: categorical emotion + laughter only.
    return (
        header
        + emotion
        + "\nYou may use [laughs] where it genuinely fits. This voice can't whisper or "
        "perform other vocal directions, so don't use other delivery tags."
        + pacing
    )


def render_tags(text: str, provider: str) -> str:
    """Render inline bracket tags for a provider's TTS.

    - Known non-verbals (laugh, sigh, gasp, ...) map to that provider's token by
      substring, so "[nervous laugh]" still laughs and drops on providers without one.
    - Unknown free-form tags ([whispering], [menacing], [breathless]) are KEPT for
      ElevenLabs v3 — which interprets arbitrary audio tags — and dropped for the
      others (Cartesia/Inworld can't act on them)."""
    idx = _PROVIDER_IDX.get(provider, 0)

    def repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        low = inner.lower()
        for root, tokens in _NONVERBAL_ROOTS.items():
            if root in low:
                tok = tokens[idx]
                return tok if tok else ""
        # A comma or a long phrase = a stage direction, not a delivery tag; drop it
        # for every provider (don't speak it, don't feed it to v3 as an audio tag).
        if "," in inner or len(inner.split()) > 3:
            return ""
        # Short free-form delivery tag ([whispering], [low and menacing]) — kept for
        # ElevenLabs v3 (interprets arbitrary tags), dropped for the others.
        return m.group(0) if provider == "elevenlabs" else ""

    return _BRACKET_RE.sub(repl, text).strip()


def has_speakable(text: str) -> bool:
    """True if there's anything worth sending to TTS (a letter/digit somewhere)."""
    return any(ch.isalnum() for ch in text)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
