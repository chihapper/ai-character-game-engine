"""Central settings + environment loading.

All configuration lives here so the rest of the codebase never reads `os.environ`
directly. Values come from `.env` (via pydantic-settings) with safe defaults.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = parent of the `orchestrator/` package.
ROOT_DIR = Path(__file__).resolve().parent.parent
CHARACTERS_DIR = Path(__file__).resolve().parent / "characters"
WEB_DIR = ROOT_DIR / "web"

# The single audio format we stream to the browser, everywhere in the app.
# Both TTS providers are asked to emit exactly this, so the frontend playback
# path never has to care which provider produced the audio.
AUDIO_SAMPLE_RATE = 24_000  # Hz
AUDIO_CHANNELS = 1
AUDIO_SAMPLE_WIDTH = 2  # bytes (16-bit signed little-endian PCM)

# Selectable LLMs, surfaced in the UI dropdown and validated server-side. Single
# source of truth for both the /api/models endpoint and the allow-list.
AVAILABLE_MODELS = [
    {"id": "claude-sonnet-4-6", "label": "Sonnet 4.6 — richer roleplay"},
    {"id": "claude-haiku-4-5", "label": "Haiku 4.5 — fastest"},
    {"id": "claude-opus-4-8", "label": "Opus 4.8 — most capable (slower)"},
]
ALLOWED_MODEL_IDS = {m["id"] for m in AVAILABLE_MODELS}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Secrets ---
    anthropic_api_key: str = ""
    inworld_api_key: str = ""
    cartesia_api_key: str = ""

    # --- LLM ---
    # Default model when the UI doesn't specify one. Sonnet 4.6 for richer
    # roleplay; the dropdown lets you switch to Haiku (faster) per session.
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 1024

    # --- TTS ---
    # "inworld" (default, leads on naturalness) or "cartesia".
    # This is the *fallback* provider; a character's YAML can override per-character.
    default_tts_provider: str = "inworld"
    inworld_model: str = "inworld-tts-2"
    cartesia_model: str = "sonic-3.5"
    # Voice stability for Inworld: STABLE delivery + lower temperature keeps the
    # timbre consistent across the separate per-sentence synthesis calls (default
    # temperature drifts the voice between sentences).
    inworld_delivery_mode: str = "STABLE"  # STABLE | BALANCED | CREATIVE
    inworld_temperature: float = 0.6

    # --- STT (step 2) ---
    # faster-whisper model size. "base.en" balances speed/accuracy on CPU.
    whisper_model: str = "base.en"
    whisper_device: str = "auto"  # "auto" | "cpu" | "cuda"
    whisper_compute_type: str = "default"

    # --- Long-term memory (step 4) ---
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_dir: str = str(ROOT_DIR / ".chroma")
    short_term_turns: int = 8  # rolling buffer: last N exchanges kept verbatim
    long_term_top_k: int = 4  # retrieved memories injected per turn

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so we parse `.env` exactly once."""
    return Settings()
