"""Smallest possible Audio2Face-3D round trip (Phase 5 precursor).

Usage:
    .venv\\Scripts\\python.exe scripts\\a2f_smoke.py [path\\to\\speech.wav] [emotion]

Sends one clip of speech PCM to the NVCF-hosted A2F-3D NIM and prints what came
back: blendshape names, frame count/rate, and whether the jaw actually moves.
Needs GAME_NVIDIA_API_KEY and GAME_A2F_FUNCTION_ID in .env (build.nvidia.com ->
Audio2Face-3D -> "Try API" shows both).
"""
import asyncio
import math
import struct
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from orchestrator.adapters.faceanim_a2f import A2FFaceAnim  # noqa: E402


def load_or_synthesize(path: str | None) -> tuple[bytes, int]:
    if path:
        with wave.open(path, "rb") as w:
            assert w.getsampwidth() == 2, "need PCM16"
            pcm = w.readframes(w.getnframes())
            if w.getnchannels() == 2:  # cheap mono mixdown
                mono = bytearray()
                for i in range(0, len(pcm), 4):
                    l, r = struct.unpack_from("<hh", pcm, i)
                    mono += struct.pack("<h", (l + r) // 2)
                pcm = bytes(mono)
            return pcm, w.getframerate()
    # fallback: 2s of syllable-ish amplitude-modulated tone (enough to move a jaw)
    rate, secs = 16000, 2.0
    out = bytearray()
    for n in range(int(rate * secs)):
        t = n / rate
        syl = max(0.0, math.sin(t * 2 * math.pi * 4.5))          # ~4.5 syllables/sec
        s = 0.5 * syl * math.sin(t * 2 * math.pi * 150) * 32767  # voiced-ish pitch
        out += struct.pack("<h", int(s))
    return bytes(out), rate


async def main() -> None:
    wav = sys.argv[1] if len(sys.argv) > 1 else None
    emotion = sys.argv[2] if len(sys.argv) > 2 else "happy"
    pcm, rate = load_or_synthesize(wav)
    dur = len(pcm) / 2 / rate
    print(f"sending {dur:.1f}s @ {rate}Hz, emotion={emotion}")

    t0 = time.perf_counter()
    result = await A2FFaceAnim().animate(pcm, rate, emotion=emotion)
    elapsed = time.perf_counter() - t0

    print(f"round trip: {elapsed:.2f}s for {dur:.1f}s of audio "
          f"({'FASTER' if elapsed < dur else 'slower'} than realtime)")
    print(f"blendshapes ({len(result.blendshape_names)}): {result.blendshape_names[:8]}...")
    print(f"frames: {len(result.frames)}"
          + (f" (~{len(result.frames) / dur:.0f} fps)" if result.frames else ""))
    if result.frames and result.blendshape_names:
        jaw_candidates = [i for i, n in enumerate(result.blendshape_names) if "jaw" in n.lower()]
        if jaw_candidates:
            j = jaw_candidates[0]
            peak = max(f[1][j] for f in result.frames)
            print(f"'{result.blendshape_names[j]}' peak: {peak:.3f} "
                  + ("— the mouth MOVES" if peak > 0.05 else "— suspiciously flat"))


if __name__ == "__main__":
    asyncio.run(main())
