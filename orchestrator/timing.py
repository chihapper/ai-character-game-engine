"""Speech pacing — every inter-line silence duration, in one place.

The engine inserts real silence between spoken lines to give a reply natural rhythm
and dramatic timing. ALL durations live here (milliseconds) so there's a single,
obvious place to tune them — and so a future game layer can override these or drive
pauses from animation / character state (e.g. hold until a "sits down" animation
finishes) without hunting through the pipeline.

Used by pipeline._gap_after (rhythm between sentences) and
expressivity.parse_pause (dramatic pauses the model directs).
"""
from __future__ import annotations

# Gap after a sentence, by how it ended. The natural rhythm, shortest to longest:
# comma < sentence < question/exclaim < trailing-off < paragraph break.
SENTENCE_GAP_MS = {
    "clause": 130,     # , ; :  — barely a hitch, mid-thought
    "default": 260,    # . or a plain ending — a normal sentence beat
    "emphatic": 330,   # ? or !  — let it land
    "trailing": 400,   # … or —  — the thought hangs
    "paragraph": 650,  # a blank line in the reply — a real beat / topic shift
}

# Pure pause tags the model can place on their own line for deliberate timing,
# e.g. "[long pause]" before a final line. Consumed (never spoken).
PAUSE_TAG_MS = {
    "long pause": 1000,
    "longer pause": 1000,
    "pause": 700,
    "beat": 400,
}

# Pause-implying words inside a richer note (e.g. "[final, quiet]") — add a beat
# without consuming the note.
PAUSE_HINT_MS = {
    "final": 500,
    "slowly": 350,
    "deliberate": 350,
    "after a moment": 550,
    "after a beat": 450,
    "trails off": 500,
}

# Ceiling on any single inter-line silence, even when cues stack, so it never drags.
GAP_MAX_MS = 2200
