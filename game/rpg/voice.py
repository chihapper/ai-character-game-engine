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


async def synth_line(text: str, slug: str) -> tuple[bytes, int]:
    """PCM (s16le mono) for an NPC line in their cast voice. Returns (pcm, sample_rate); returns
    (b'', rate) on ANY failure (missing key, no credits, network) — voice is an enhancement and
    must never block or crash the reply."""
    from orchestrator.config import AUDIO_SAMPLE_RATE
    rate = AUDIO_SAMPLE_RATE
    if not (text or "").strip():
        return b"", rate
    try:
        from game import casting

        from orchestrator.adapters.tts_hume import HumeTTS
        vid = casting.hume_voice(slug)
        chunks: list[bytes] = []
        async for chunk in HumeTTS().stream_speech(text, vid):
            chunks.append(chunk)
        return b"".join(chunks), rate
    except Exception as exc:                       # noqa: BLE001 — voice is best-effort
        log.warning("voice synth failed for %s: %s", slug, exc)
        return b"", rate
