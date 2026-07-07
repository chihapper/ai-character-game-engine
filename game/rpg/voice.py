"""Optional NPC voice for the RPG server — synthesize an NPC's line via Hume Octave.

Presentation-layer ONLY: the game-core stays audio-free (the tcod dev view has no sound), and the
WebSocket server calls this for dialogue events when voice is enabled, streaming the PCM to the
Godot client. Mirrors the mind server (game/bridge/mind_api.py): feed Hume the FULL reply — its
adapter voices only the quoted speech and turns the stage directions into acting instructions — and
resolve the character's voice from the cast map (game/casting.py).
"""
from __future__ import annotations

import logging

log = logging.getLogger("rpg.voice")


def wire_rate() -> int:
    """The PCM sample rate everything on the wire uses (s16le mono)."""
    from orchestrator.config import AUDIO_SAMPLE_RATE
    return AUDIO_SAMPLE_RATE


async def stream_line(text: str, slug: str):
    """STREAM the PCM (s16le mono) for an NPC line in their cast voice, chunk by chunk as Hume
    produces it — the caller can put the first sentence on the wire while the rest is still
    synthesizing. Yields raw PCM chunks; raises on failure (the caller treats voice as
    best-effort). The adapter feeds Hume the FULL reply: it voices only the quoted speech and
    turns stage directions into acting instructions."""
    if not (text or "").strip():
        return
    from game import casting

    from orchestrator.adapters.tts_hume import HumeTTS
    vid = casting.hume_voice(slug)
    async for chunk in HumeTTS().stream_speech(text, vid):
        yield chunk


async def synth_line(text: str, slug: str) -> tuple[bytes, int]:
    """The whole line's PCM in one buffer — the non-streaming convenience over `stream_line`.
    Returns (b'', rate) on ANY failure (missing key, no credits, network) — voice is an
    enhancement and must never block or crash the reply."""
    rate = wire_rate()
    try:
        chunks: list[bytes] = []
        async for chunk in stream_line(text, slug):
            chunks.append(chunk)
        return b"".join(chunks), rate
    except Exception as exc:                       # noqa: BLE001 — voice is best-effort
        log.warning("voice synth failed for %s: %s", slug, exc)
        return b"", rate
