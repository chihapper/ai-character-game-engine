"""NVIDIA Audio2Face-3D (remote NIM over gRPC) behind the FaceAnimAdapter seam.

Speech PCM in -> ARKit-52 blendshape frames out, solved by the NVCF-hosted
Audio2Face-3D NIM (a GTX 1080 Ti cannot run the models locally — Ampere+ only,
verified 2026-07). The engine's chosen emotion rides along as a2f's
"preferred emotion", overriding Audio2Emotion's audio-inferred mood: which face
a character makes is the ENGINE's call, the audio only times the mouth.

Env:
  GAME_NVIDIA_API_KEY   nvapi-... key from build.nvidia.com (required)
  GAME_A2F_TARGET       gRPC target, default grpc.nvcf.nvidia.com:443
  GAME_A2F_FUNCTION_ID  NVCF function id for the A2F-3D endpoint (required for NVCF)
  GAME_A2F_FUNCTION_VERSION  optional pinned function version
"""
from __future__ import annotations

import os

import grpc
from nvidia_ace import audio_pb2
from nvidia_audio2face_3d import audio2face_pb2_grpc, messages_pb2

from .base import FaceAnimAdapter, FaceAnimResult

# engine face tags (agency.choose_action / reactions) -> A2F emotion names
ENGINE_TO_A2F_EMOTION = {
    "happy": "joy",
    "sad": "sadness",
    "angry": "anger",
    "fear": "fear",
    "surprise": "amazement",
    "disgust": "disgust",
    "pain": "pain",
    "grief": "grief",
}


class A2FFaceAnim(FaceAnimAdapter):
    def __init__(self) -> None:
        self.api_key = (os.environ.get("GAME_NVIDIA_API_KEY") or "").strip()
        self.target = os.environ.get("GAME_A2F_TARGET", "grpc.nvcf.nvidia.com:443")
        self.function_id = (os.environ.get("GAME_A2F_FUNCTION_ID") or "").strip()
        self.function_version = (os.environ.get("GAME_A2F_FUNCTION_VERSION") or "").strip()

    def _metadata(self) -> list[tuple[str, str]]:
        md = [("authorization", f"Bearer {self.api_key}")]
        if self.function_id:
            md.append(("function-id", self.function_id))
        if self.function_version:
            md.append(("function-version", self.function_version))
        return md

    def _request_stream(self, pcm16: bytes, sample_rate: int,
                        emotion: str | None, emotion_strength: float):
        header = messages_pb2.AudioWithEmotionStreamHeader(
            audio_header=audio_pb2.AudioHeader(
                audio_format=audio_pb2.AudioHeader.AUDIO_FORMAT_PCM,
                channel_count=1,
                samples_per_second=sample_rate,
                bits_per_sample=16,
            ),
        )
        a2f_emotion = ENGINE_TO_A2F_EMOTION.get((emotion or "").lower())
        if a2f_emotion:
            # deterministic path: the engine's pick becomes the preferred emotion,
            # weighted in ahead of (not blended blindly with) audio inference
            pp = header.emotion_post_processing_params
            pp.enable_preferred_emotion = True
            pp.preferred_emotion_strength = max(0.0, min(1.0, emotion_strength))
        yield messages_pb2.AudioWithEmotionStream(audio_stream_header=header)

        chunk_bytes = sample_rate * 2 // 10  # 100 ms of PCM16 mono per message
        for off in range(0, len(pcm16), chunk_bytes):
            audio = messages_pb2.AudioWithEmotion(audio_buffer=pcm16[off:off + chunk_bytes])
            if a2f_emotion and off == 0:
                e = audio.emotions.add()
                e.time_code = 0.0
                e.emotion[a2f_emotion] = max(0.0, min(1.0, emotion_strength))
            yield messages_pb2.AudioWithEmotionStream(audio_with_emotion=audio)

        yield messages_pb2.AudioWithEmotionStream(
            end_of_audio=messages_pb2.AudioWithEmotionStream.EndOfAudio())

    async def animate(self, pcm16: bytes, sample_rate: int,
                      emotion: str | None = None, emotion_strength: float = 1.0) -> FaceAnimResult:
        if not self.api_key:
            raise RuntimeError("GAME_NVIDIA_API_KEY not set — cannot reach the hosted A2F-3D NIM")
        creds = grpc.ssl_channel_credentials()
        names: list[str] = []
        frames: list[tuple[float, list[float]]] = []
        emotions: list[tuple[float, dict[str, float]]] = []
        async with grpc.aio.secure_channel(self.target, creds) as channel:
            stub = audio2face_pb2_grpc.A2FControllerServiceStub(channel)
            call = stub.ProcessAudioStream(
                self._request_stream(pcm16, sample_rate, emotion, emotion_strength),
                metadata=self._metadata())
            async for msg in call:
                kind = msg.WhichOneof("stream_part")
                if kind == "animation_data_stream_header":
                    names = list(msg.animation_data_stream_header.skel_animation_header.blend_shapes)
                elif kind == "animation_data":
                    for bs in msg.animation_data.skel_animation.blend_shape_weights:
                        frames.append((bs.time_code, list(bs.values)))
                elif kind == "status" and msg.status.code != 0:
                    raise RuntimeError(f"A2F-3D error: {msg.status.message}")
        frames.sort(key=lambda f: f[0])
        return FaceAnimResult(names, frames, emotions)
