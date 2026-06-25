"""Sanitize model text before it goes to the speech synthesizer.

LLMs sometimes emit things a *spoken* character shouldn't say out loud — asterisk
stage directions (`*pours a drink*`), markdown, emoji. Those get vocalized by TTS
and break the illusion. We strip them from the text sent to TTS while leaving the
on-screen transcript untouched (so you still see exactly what the model produced).

Bracketed `[tags]` are deliberately LEFT IN place here — they're performance tags
(emotion / non-verbals / delivery) that each TTS adapter renders or drops for its
own provider (see expressivity.render_tags).
"""
from __future__ import annotations

import re

# *emphasis* / **bold** — the model uses asterisks to stress a word, so KEEP the
# inner text (just drop the asterisks) instead of deleting it. Physical actions are
# conveyed via [bracketed] tags, which the adapters handle separately.
_ASTERISK_SPAN = re.compile(r"\*{1,3}([^*\n]+)\*{1,3}")
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
    t = _ASTERISK_SPAN.sub(r"\1", text)  # keep the emphasized word, drop the *'s
    t = t.replace("*", "")  # stray, unmatched asterisks (brackets are kept for tags)
    t = _EMOJI.sub("", t)
    t = _MD_CHARS.sub("", t)
    t = _WS.sub(" ", t).strip()
    # If nothing speakable survived (e.g. just "." left after a stripped *action*),
    # return empty so the caller skips it — TTS rejects punctuation-only input
    # ("No valid transcripts passed.") and that error would abort the whole reply.
    if not any(ch.isalnum() for ch in t):
        return ""
    return t
