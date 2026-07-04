"""Track V TTS bake-off harness.

Runs the same emotionally-demanding lines through every provider with credentials,
writes listenable WAVs, measures latency, and (--a2f) scores each clip's FACIAL LIFE
by running it through Audio2Face — how much expression the audio actually carries
(flat voice -> flat face; this is the dual test).

    .venv\\Scripts\\python.exe scripts\\tts_bakeoff.py [--a2f] [--providers hume,fish,...]

Voices: provider defaults unless overridden below — the bake-off compares PERFORMANCE,
casting comes after a winner is picked. Output: tts_bakeoff_out/<provider>/<line>.wav
+ report.md with the numbers side by side.
"""
import argparse
import asyncio
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from orchestrator.config import AUDIO_SAMPLE_RATE  # noqa: E402

# The gauntlet: the exact registers Inworld tts-2 failed (high arousal) plus range.
LINES = {
    "neutral":  "Room's four coppers a night, meals are extra. Storm like this, you'll want the stew.",
    "rage":     "[furious, shouting] GET OUT! Get out of my inn RIGHT NOW, and don't you DARE come back!",
    "grief":    "[quiet, voice breaking] He was on the ferry when it went down. I keep... I keep setting his place at the table.",
    "joy":      "[laughing, delighted] You actually did it! Ha! I never doubted you — all right, I doubted you a LITTLE.",
    "fear":     "[whispering, terrified] Don't turn around. There's something at the window. It's been watching us for an hour.",
    "flirt":    "[warm, teasing] Well now. The storm blows in all kinds of trouble, but you... you might be my favorite kind.",
}

# provider -> (adapter factory, default voice for the test)
def _providers():
    out = {}
    try:
        from orchestrator.adapters.tts_inworld import InworldTTS
        out["inworld"] = (InworldTTS, "Ashley")
    except Exception:
        pass
    try:
        from orchestrator.adapters.tts_elevenlabs import ElevenLabsTTS
        out["elevenlabs"] = (ElevenLabsTTS, "21m00Tcm4TlvDq8ikWAM")  # Rachel (premade)
    except Exception:
        pass
    from orchestrator.adapters.tts_hume import HumeTTS
    out["hume"] = (HumeTTS, "Female English Actor")
    from orchestrator.adapters.tts_fish import FishTTS
    out["fish"] = (FishTTS, "")  # default voice
    from orchestrator.adapters.tts_chatterbox import ChatterboxTTS
    out["chatterbox"] = (ChatterboxTTS, "")  # builtin voice (no reference clip)
    return out


async def run_one(name, factory, voice, key, text, outdir, use_a2f):
    row = {"provider": name, "line": key}
    try:
        tts = factory()
        t0 = time.perf_counter()
        first = None
        chunks = []
        async for chunk in tts.stream_speech(text, voice):
            if first is None:
                first = time.perf_counter() - t0
            chunks.append(chunk)
        total = time.perf_counter() - t0
        pcm = b"".join(chunks)
        if not pcm:
            row["error"] = "no audio"
            return row
        dur = len(pcm) / 2 / AUDIO_SAMPLE_RATE
        path = outdir / name / f"{key}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(AUDIO_SAMPLE_RATE)
            w.writeframes(pcm)
        row.update(first_audio_s=round(first, 2), total_s=round(total, 2), clip_s=round(dur, 1))
        if use_a2f:
            from orchestrator.adapters.faceanim_a2f import A2FFaceAnim
            r = await A2FFaceAnim().animate(pcm, AUDIO_SAMPLE_RATE)
            names = r.blendshape_names
            def peak(n):
                i = [k for k, x in enumerate(names) if x.lower() == n.lower()]
                return round(max(f[1][i[0]] for f in r.frames), 2) if i and r.frames else 0.0
            # facial life = articulation + how far the expressive channels move
            row.update(jaw=peak("JawOpen"), smile=peak("MouthSmileLeft"),
                       frown=peak("MouthFrownLeft"), brow=peak("BrowDownLeft"),
                       wide=peak("EyeWideLeft"))
    except Exception as exc:
        row["error"] = str(exc)[:140]
    return row


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a2f", action="store_true", help="score facial life via Audio2Face")
    ap.add_argument("--providers", default="", help="comma list; default = all available")
    args = ap.parse_args()

    outdir = ROOT / "tts_bakeoff_out"
    provs = _providers()
    if args.providers:
        want = {p.strip() for p in args.providers.split(",")}
        provs = {k: v for k, v in provs.items() if k in want}

    rows = []
    for name, (factory, voice) in provs.items():
        print(f"== {name}")
        for key, text in LINES.items():
            row = await run_one(name, factory, voice, key, text, outdir, args.a2f)
            rows.append(row)
            print("  ", row)

    cols = ["provider", "line", "first_audio_s", "total_s", "clip_s",
            "jaw", "smile", "frown", "brow", "wide", "error"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    (outdir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWAVs + report.md in {outdir}")


if __name__ == "__main__":
    asyncio.run(main())
