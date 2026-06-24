"""Sanitize model text before it goes to the speech synthesizer.

LLMs sometimes emit things a *spoken* character shouldn't say out loud — asterisk
stage directions (`*pours a drink*`), markdown, emoji. Those get vocalized by TTS
and break the illusion. We strip them from the text sent to TTS while leaving the
on-screen transcript untouched (so you still see exactly what the model produced).
"""
from __future__ import annotations

import re

# *stage direction* or **bold** — remove the whole span, content included (for
# actions we don't want spoken; the occasional bolded word is acceptable collateral).
_ASTERISK_SPAN = re.compile(r"\*{1,3}[^*\n]+\*{1,3}")
# [bracketed stage direction]
_BRACKET_SPAN = re.compile(r"\[[^\]\n]*\]")
# Inline markdown punctuation that shouldn't be read aloud.
_MD_CHARS = re.compile(r"[`_#>~]")
# Emoji / pictographs / symbol & arrow blocks.
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff"
    "←-⇿⌀-⏿⬀-⯿]"
)
_WS = re.compile(r"\s+")


def clean_for_speech(text: str) -> str:
    """Return `text` with stage directions, markdown, and emoji removed."""
    if not text:
        return ""
    t = _ASTERISK_SPAN.sub(" ", text)
    t = _BRACKET_SPAN.sub(" ", t)
    t = t.replace("*", "")  # stray, unmatched asterisks
    t = _EMOJI.sub("", t)
    t = _MD_CHARS.sub("", t)
    t = _WS.sub(" ", t).strip()
    return t
