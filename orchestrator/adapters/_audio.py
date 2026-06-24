"""Small audio helpers shared by TTS adapters."""
from __future__ import annotations


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
