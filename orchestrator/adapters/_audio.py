"""Small audio helpers shared by TTS adapters."""
from __future__ import annotations

import struct


def pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, bits: int = 16) -> bytes:
    """Wrap raw PCM in a minimal RIFF/WAVE header so a browser <audio> can play it.
    Our TTS yields headerless PCM for the realtime player; this is for the rare case
    we need a standalone, downloadable/playable file (e.g. a voice preview)."""
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + len(pcm))
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits)
        + b"data"
        + struct.pack("<I", len(pcm))
    )
    return header + pcm


def strip_wav_header(data: bytes) -> bytes:
    """Return raw PCM samples, stripping a leading RIFF/WAVE header if present.

    We request headerless PCM from both providers (Inworld LINEAR16, Cartesia
    `container: "raw"`), but some provider responses still prepend a WAV header on
    the first chunk. This makes the first chunk safe to feed straight to the
    browser's PCM player. Assumes the full 44-ish-byte header fits in `data`.
    """
    if data[:4] == b"RIFF" and b"data" in data[:64]:
        idx = data.find(b"data")
        # Skip the 'data' tag (4 bytes) + the 4-byte chunk-size field.
        return data[idx + 8 :]
    return data
