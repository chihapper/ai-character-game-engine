"""NeuroSync (self-hosted, audio->ARKit) behind the FaceAnimAdapter seam.

Replaces the NVIDIA A2F path: A2F's models need Ampere+ (our dev GPU is a GTX 1080 Ti,
Pascal), so we self-host NeuroSync — an MIT/CC-BY-NC seq2seq transformer that runs in
fp32 on the 1080 Ti. It takes speech audio and returns 60fps facial frames.

Output layout (NeuroSync FaceBlendShape enum, verified against the Player source):
  0-51  ARKit-52 (EyeBlinkLeft ... TongueOut) — the canonical MetaHuman LiveLink set
  52-54 HeadYaw / HeadPitch / HeadRoll         — head MOTION (A2F had none: static-head mask)
  55-60 per-eye yaw/pitch/roll
  61-67 detected emotions (Angry..Surprised)   — NOT streamed to the face

Emotion note: NeuroSync is audio-ONLY (no preferred-emotion input like A2F). The engine's
chosen emotion still reaches the face — it rides IN the (already emotional) Hume voice, and
NeuroSync reads that. So `emotion` args are accepted and ignored here by design.

The local server (game/../neurosync-lab) is a Flask service: POST raw WAV bytes to
/audio_to_blendshapes -> {"blendshapes": [[68 floats], ...]}.  GAME_NEUROSYNC_URL overrides.
"""
from __future__ import annotations

import io
import os
import wave

import httpx

from .base import FaceAnimAdapter, FaceAnimResult

# indices 0-60: the face-relevant channels, in NeuroSync's output order (= ARKit LiveLink order)
NEUROSYNC_NAMES = [
    "EyeBlinkLeft", "EyeLookDownLeft", "EyeLookInLeft", "EyeLookOutLeft", "EyeLookUpLeft",
    "EyeSquintLeft", "EyeWideLeft", "EyeBlinkRight", "EyeLookDownRight", "EyeLookInRight",
    "EyeLookOutRight", "EyeLookUpRight", "EyeSquintRight", "EyeWideRight",
    "JawForward", "JawLeft", "JawRight", "JawOpen", "MouthClose", "MouthFunnel", "MouthPucker",
    "MouthLeft", "MouthRight", "MouthSmileLeft", "MouthSmileRight", "MouthFrownLeft",
    "MouthFrownRight", "MouthDimpleLeft", "MouthDimpleRight", "MouthStretchLeft",
    "MouthStretchRight", "MouthRollLower", "MouthRollUpper", "MouthShrugLower", "MouthShrugUpper",
    "MouthPressLeft", "MouthPressRight", "MouthLowerDownLeft", "MouthLowerDownRight",
    "MouthUpperUpLeft", "MouthUpperUpRight", "BrowDownLeft", "BrowDownRight", "BrowInnerUp",
    "BrowOuterUpLeft", "BrowOuterUpRight", "CheekPuff", "CheekSquintLeft", "CheekSquintRight",
    "NoseSneerLeft", "NoseSneerRight", "TongueOut",
    "HeadYaw", "HeadPitch", "HeadRoll",
    "LeftEyeYaw", "LeftEyePitch", "LeftEyeRoll", "RightEyeYaw", "RightEyePitch", "RightEyeRoll",
]
_FACE_CHANNELS = len(NEUROSYNC_NAMES)   # 61
_FPS = 60.0                              # NeuroSync frame_rate (config.py)


def _wav_bytes(pcm16: bytes, sample_rate: int) -> bytes:
    """Wrap headerless s16le mono PCM in a WAV container — NeuroSync loads audio via librosa,
    which wants a self-describing file, not raw samples."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm16)
    return buf.getvalue()


class NeuroSyncFaceAnim(FaceAnimAdapter):
    def __init__(self) -> None:
        self.url = os.environ.get("GAME_NEUROSYNC_URL", "http://127.0.0.1:5000").rstrip("/")

    async def animate(self, pcm16: bytes, sample_rate: int,
                      emotion: str | None = None, emotion_strength: float = 1.0,
                      emotion_timeline: list[tuple[float, str, float]] | None = None) -> FaceAnimResult:
        wav = _wav_bytes(pcm16, sample_rate)
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
            resp = await client.post(f"{self.url}/audio_to_blendshapes", content=wav,
                                     headers={"Content-Type": "application/octet-stream"})
            if resp.status_code != 200:
                raise RuntimeError(f"NeuroSync error {resp.status_code}: {resp.text[:200]}")
            rows = resp.json().get("blendshapes") or []
        if not rows:
            raise RuntimeError("NeuroSync returned no frames "
                               "(is the local server up and model.pth in place?)")
        frames: list[tuple[float, list[float]]] = []
        for i, row in enumerate(rows):
            frames.append((i / _FPS, [float(x) for x in row[:_FACE_CHANNELS]]))
        return FaceAnimResult(NEUROSYNC_NAMES, frames)
