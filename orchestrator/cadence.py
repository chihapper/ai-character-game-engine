"""Per-speaker cadence analysis for adaptive endpointing.

During a short calibration we stream the speaker's voice to AssemblyAI with a
deliberately wide end-of-turn window, so it does NOT chop them up — letting us
observe their natural pauses from the word-level timestamps. From the distribution
of inter-word gaps we estimate how long this person tends to pause mid-thought, and
derive end-of-turn silence thresholds tuned to them:

  * max_turn_silence — must exceed their typical deliberate pause, or they get cut
    off mid-thought. Set from a high percentile of their pauses + a margin.
  * min_turn_silence — dead-air after a finished sentence. Snappier for fluent
    speakers (small median gap), a bit longer for choppy ones.

The formula is intentionally simple and transparent (stats are saved on the
profile); it can be refined as we gather real usage.
"""
from __future__ import annotations


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


# Safety rails so a noisy calibration can never produce absurd values.
_MIN_FLOOR, _MIN_CEIL = 200, 500
_MAX_FLOOR, _MAX_CEIL = 1200, 3000
_PAUSE_THRESHOLD = 250  # ms; gaps above this count as deliberate pauses


def analyze_cadence(word_gaps_ms: list[float]) -> dict:
    """`word_gaps_ms`: inter-word silence gaps (ms) seen during calibration.
    Returns suggested min/max turn silence (ms) plus the stats they came from."""
    gaps = [g for g in word_gaps_ms if 0 <= g <= 5000]
    deliberate = [g for g in gaps if g >= _PAUSE_THRESHOLD]

    p50 = _percentile(gaps, 50)
    # Default to a middle-of-the-road pause if the speaker barely paused at all.
    p85_pause = _percentile(deliberate, 85) if deliberate else 600.0

    max_silence = int(min(_MAX_CEIL, max(_MAX_FLOOR, p85_pause + 400)))
    min_silence = int(min(_MIN_CEIL, max(_MIN_FLOOR, 150 + p50)))

    return {
        "min_turn_silence": min_silence,
        "max_turn_silence": max_silence,
        "samples": len(gaps),
        "median_gap_ms": round(p50),
        "p85_pause_ms": round(p85_pause),
    }
