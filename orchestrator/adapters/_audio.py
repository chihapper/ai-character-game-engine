"""Small audio helpers shared by TTS adapters."""
from __future__ import annotations

import struct
from array import array


def fade_pcm(
    pcm: bytes, sample_rate: int, *, fade_in: bool = False, fade_out: bool = False, ms: float = 8.0
) -> bytes:
    """Apply a short linear fade to the edges of 16-bit mono PCM so concatenated segments
    don't click. A few ms is inaudible as a fade but drives the boundary sample to zero,
    removing the amplitude step that pops when one TTS request butts against silence/another.
    (Host is little-endian, matching our s16le wire format.)

    Tolerates an odd byte count: provider chunks can split a 16-bit sample across a chunk
    boundary, so we fade whole samples and pass any trailing half-sample byte through."""
    if not pcm or not (fade_in or fade_out):
        return pcm
    trailing = b""
    if len(pcm) & 1:
        pcm, trailing = pcm[:-1], pcm[-1:]
    samples = array("h")
    samples.frombytes(pcm)
    n = len(samples)
    fn = min(int(sample_rate * ms / 1000), n)
    if fn <= 0:
        return pcm + trailing
    if fade_in:
        for i in range(fn):
            samples[i] = (samples[i] * i) // fn
    if fade_out:
        for i in range(fn):
            samples[n - 1 - i] = (samples[n - 1 - i] * i) // fn
    return samples.tobytes() + trailing


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
