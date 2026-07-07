"""Generate the RPG's ORIGINAL chip-style sound set — synthesized from scratch (stdlib only), so
every sample is our own work: no downloads, no attribution burden, and a lo-fi character that
matches the pixel art. Writes 16-bit mono 22050 Hz WAVs into godot/assets/sfx/.

    .venv/Scripts/python.exe tools/gen_rpg_sfx.py
"""
from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

SR = 22050
OUT = Path(__file__).resolve().parent.parent / "godot" / "assets" / "sfx"


def _write(name: str, samples: list[float]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    peak = max(1e-6, max(abs(s) for s in samples))
    norm = 0.85 / peak
    with wave.open(str(OUT / name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s * norm)) * 32767))
                               for s in samples))
    print(f"  {name}  ({len(samples) / SR:.2f}s)")


def _env(n: int, attack: float = 0.005, decay_pow: float = 2.0) -> list[float]:
    """Percussive envelope: fast attack, power-curve decay."""
    a = max(1, int(SR * attack))
    out = []
    for i in range(n):
        if i < a:
            out.append(i / a)
        else:
            t = (i - a) / max(1, n - a)
            out.append((1.0 - t) ** decay_pow)
    return out


def _noise(n: int, rng: random.Random, lp: float = 0.2) -> list[float]:
    """One-pole low-passed white noise (lp in (0,1]: 1 = white, small = dark rumble)."""
    out = []
    y = 0.0
    for _ in range(n):
        y += lp * (rng.uniform(-1, 1) - y)
        out.append(y)
    return out


def _tone(n: int, freq, shape: str = "square", sweep_to: float | None = None) -> list[float]:
    out = []
    phase = 0.0
    for i in range(n):
        f = freq if sweep_to is None else freq + (sweep_to - freq) * (i / n)
        phase += f / SR
        p = phase % 1.0
        if shape == "square":
            out.append(0.6 if p < 0.5 else -0.6)
        elif shape == "saw":
            out.append(2.0 * p - 1.0)
        elif shape == "tri":
            out.append(4.0 * abs(p - 0.5) - 1.0)
        else:
            out.append(math.sin(phase * math.tau))
    return out


def _mix(*layers: list[float]) -> list[float]:
    n = max(len(x) for x in layers)
    return [sum(x[i] if i < len(x) else 0.0 for x in layers) for i in range(n)]


def _gain(x: list[float], g: float) -> list[float]:
    return [s * g for s in x]


def _mul(x: list[float], env: list[float]) -> list[float]:
    return [s * (env[i] if i < len(env) else 0.0) for i, s in enumerate(x)]


def _notes(freqs: list[float], each_s: float, shape: str = "square") -> list[float]:
    out: list[float] = []
    n = int(SR * each_s)
    for f in freqs:
        out += _mul(_tone(n, f, shape), _env(n, 0.004, 1.5))
    return out


def main() -> None:
    rng = random.Random(7)
    print(f"writing to {OUT}")

    n = int(SR * 0.10)
    _write("hit.wav", _mix(_mul(_noise(n, rng, 0.5), _env(n, 0.002, 3)),
                           _gain(_mul(_tone(n, 90, "sine", 55), _env(n, 0.002, 2)), 1.2)))

    n = int(SR * 0.16)
    _write("crit.wav", _mix(_mul(_noise(n, rng, 0.7), _env(n, 0.002, 3)),
                            _gain(_mul(_tone(n, 110, "sine", 50), _env(n, 0.002, 2)), 1.3),
                            _gain(_mul(_tone(int(SR * 0.05), 1800, "tri", 900), _env(int(SR * 0.05), 0.001, 2)), 0.5)))

    n = int(SR * 0.15)
    _write("miss.wav", _mul(_noise(n, rng, 0.9), [math.sin(math.pi * i / n) * (1 - i / n * 0.4) for i in range(n)]))

    n = int(SR * 0.22)
    _write("down.wav", _mul(_tone(n, 70, "sine", 40), _env(n, 0.003, 2)))

    n = int(SR * 0.38)
    _write("dead.wav", _mix(_mul(_tone(n, 60, "sine", 32), _env(n, 0.003, 1.6)),
                            _gain(_mul(_noise(n, rng, 0.12), _env(n, 0.01, 2)), 0.6)))

    _write("victory.wav", _notes([392, 523, 659], 0.13))
    _write("levelup.wav", _notes([523, 659, 784, 1046], 0.11))
    _write("loot.wav", _notes([1318, 1760], 0.07, "tri"))

    n = int(SR * 0.09)
    glug = []
    for k in (300, 220, 260):
        glug += _mul(_tone(n, k, "sine", k * 0.7), _env(n, 0.01, 1.5))
    _write("drink.wav", glug)

    n = int(SR * 0.4)
    _write("door.wav", _mix(_mul(_tone(n, 85, "saw", 48), _env(n, 0.02, 1.2)),
                            _gain(_mul(_noise(n, rng, 0.25), _env(n, 0.02, 1.5)), 0.5)))

    n = int(SR * 0.3)
    _write("alarm.wav", _mix(_mul(_tone(n, 220, "square"), _env(n, 0.004, 1.2)),
                             _gain(_mul(_tone(n, 233, "square"), _env(n, 0.004, 1.2)), 0.9)))

    n = int(SR * 0.08)
    _write("save.wav", _mul(_tone(n, 880, "tri"), _env(n, 0.002, 2.5)))

    # --- ambience loops (12s, loop-friendly: the tail crossfades into the head) ---
    def ambience(name: str, lp: float, base_gain: float, crackle: bool) -> None:
        n = int(SR * 12)
        rumble = _noise(n, rng, lp)
        lfo = [0.75 + 0.25 * math.sin(math.tau * i / SR / 7.0) for i in range(n)]
        amb = [rumble[i] * lfo[i] * base_gain for i in range(n)]
        if crackle:
            for _ in range(90):                    # ember ticks
                at = rng.randrange(0, n - 400)
                for j in range(rng.randrange(60, 240)):
                    amb[at + j] += rng.uniform(-0.25, 0.25) * (1 - j / 240)
        fade = int(SR * 0.8)                       # crossfade tail -> head for a clean loop
        for i in range(fade):
            t = i / fade
            amb[n - fade + i] = amb[n - fade + i] * (1 - t) + amb[i] * t
        _write(name, amb)

    ambience("amb_vault.wav", 0.045, 1.0, crackle=False)
    ambience("amb_emberdeep.wav", 0.09, 1.0, crackle=True)
    print("done.")


if __name__ == "__main__":
    main()
