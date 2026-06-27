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
PROFILES_DIR = Path(__file__).resolve().parent / "profiles"  # per-speaker cadence
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

# Full-loop (Inworld-routed) LLMs surfaced in the conversation dropdown when
# VOICE_RUNTIME=inworld_fullloop. Provider/name ids; labels carry the Track V latency
# findings (first-audio is dominated by the routed LLM's TTFT, not TTS). Single source for
# the dropdown and the ?realtime_llm= allow-list.
REALTIME_MODELS = [
    {"id": "anthropic/claude-haiku-4-5", "label": "Haiku 4.5 — best character (~2.4s)"},
    {"id": "openai/gpt-4o", "label": "GPT-4o — fast & strong (~1.1s)"},
    {"id": "openai/gpt-4o-mini", "label": "GPT-4o mini — fastest (~1.1s)"},
    {"id": "openai/gpt-4.1-mini", "label": "GPT-4.1 mini — fast"},
    {"id": "anthropic/claude-sonnet-4-6", "label": "Sonnet 4.6 — richest, slowest"},
]
ALLOWED_REALTIME_MODEL_IDS = {m["id"] for m in REALTIME_MODELS}

# tts-2 delivery presets (stability vs expressiveness), surfaced in the full-loop UI.
DELIVERY_MODES = [
    {"id": "STABLE", "label": "Stable — most consistent"},
    {"id": "BALANCED", "label": "Balanced — middle"},
    {"id": "CREATIVE", "label": "Creative — most expressive"},
]
ALLOWED_DELIVERY_MODES = {m["id"] for m in DELIVERY_MODES}


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
    elevenlabs_api_key: str = ""
    assemblyai_api_key: str = ""

    # --- LLM ---
    # Default model when the UI doesn't specify one. Sonnet 4.6 for richer
    # roleplay; the dropdown lets you switch to Haiku (faster) per session.
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 1024

    # --- TTS ---
    # Default provider for new characters. "elevenlabs" leads on expressivity (the
    # bake-off winner); "inworld" is ~4-8x cheaper for scale; "cartesia" is fast but
    # flat. A character's YAML overrides this per-character (the engine is provider-
    # agnostic by design — that per-character field is the cost lever at scale).
    default_tts_provider: str = "elevenlabs"
    inworld_model: str = "inworld-tts-2"
    cartesia_model: str = "sonic-3.5"
    # Inworld voice consistency vs. emotional range across the separate per-sentence/
    # per-batch requests. STABLE = most consistent timbre; CREATIVE = widest range but the
    # voice drifts more between requests; BALANCED sits in between. Flip via
    # INWORLD_DELIVERY_MODE in .env — no code change, just restart.
    inworld_delivery_mode: str = "BALANCED"  # STABLE | BALANCED | CREATIVE
    inworld_temperature: float = 0.6  # ignored on inworld-tts-2 (kept for tts-1.5)
    # ElevenLabs — the expressive option. eleven_v3 is the only model that reads
    # inline audio tags ([whispers]/[laughs]/[angry]); it is alpha and NOT
    # low-latency. Low stability + non-zero style = the most emotional delivery.
    elevenlabs_model: str = "eleven_v3"
    elevenlabs_stability: float = 0.4  # 0-1; lower = broader emotional range
    elevenlabs_style: float = 0.6  # 0-1; higher = more expressive (adds latency)
    elevenlabs_ttv_model: str = "eleven_multilingual_ttv_v2"  # text-to-voice (design)
    # If the primary TTS provider fails/hangs during a conversation, fall back to
    # Cartesia (when its key is set) using this preset voice, so an outage on one
    # provider can't silence the whole app. Sticky for the rest of the session.
    cartesia_fallback_voice: str = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"

    # --- STT ---
    # "assemblyai" (cloud, no local deps — recommended for distribution) or
    # "whisper" (local faster-whisper).
    stt_provider: str = "whisper"
    # AssemblyAI streaming endpointing (ms). Defaults (100/1000) cut off slow or
    # disfluent speakers. min = dead-air after a complete sentence before the turn
    # ends (the only value that adds per-turn latency — kept snappy, ~natural human
    # turn-taking gap). max = how long it waits through a mid-thought pause / "umm"
    # before force-ending (near-free: complete sentences never wait this long).
    assemblyai_min_turn_silence: int = 300
    assemblyai_max_turn_silence: int = 1800
    # faster-whisper model size. "base.en" balances speed/accuracy on CPU.
    whisper_model: str = "base.en"
    # CPU is the portable default and needs no CUDA DLLs. Set WHISPER_DEVICE=cuda
    # only if you have a working CUDA 12 + cuBLAS install.
    whisper_device: str = "cpu"  # "cpu" | "cuda"
    whisper_compute_type: str = "int8"  # int8 is fast + accurate enough on CPU

    # --- Voice runtime (Track V) ---
    # "pipeline"          = the inherited modular STT -> LLM -> TTS overlap pipeline
    #                       (default / current code path).
    # "inworld_fullloop"  = drive Inworld's Realtime agent: ONE session owns
    #                       STT -> Claude -> Realtime TTS-2 with cross-turn voice
    #                       continuity. Phase-1 work behind this flag — see
    #                       docs/track-v-full-loop-plan.md.
    voice_runtime: str = "pipeline"
    # The LLM the Inworld Realtime session routes to (provider/name); billed via Inworld.
    # Haiku 4.5 over Sonnet 4.6: ~40% lower respond->first-audio (3.78s->2.29s in the
    # Track V A/B) with no measurable loss in character voice or memory grounding — and
    # first-audio latency is the whole game for the "real" feel. realtime_model_ab.py is
    # the harness; flip back with REALTIME_LLM_MODEL=anthropic/claude-sonnet-4-6.
    realtime_llm_model: str = "anthropic/claude-haiku-4-5"
    # The Realtime TTS model. inworld-tts-2 honors [bracket] steering tags (so the
    # character's expressivity carries) — verified in the Phase-0 spikes.
    realtime_tts_model: str = "inworld-tts-2"
    # tts-2 generation preset (providerData.tts.delivery_mode): STABLE | BALANCED | CREATIVE
    # — stability vs expressiveness. CREATIVE for the full loop: the single-session TTS
    # context keeps the voice coherent across turns, so we can afford the widest emotional
    # range (the per-turn drift that made us pick BALANCED on the modular path matters less
    # here). Per-session selectable in the UI; the modular path keeps its own delivery mode.
    realtime_delivery_mode: str = "CREATIVE"

    # --- Long-term memory ---
    # Embedder preference: fastembed (ONNX, light, Windows-friendly) -> sentence-transformers
    # -> dependency-free lexical fallback. fastembed is the issue-#1 recommendation.
    fastembed_model: str = "BAAI/bge-small-en-v1.5"  # preferred semantic embedder
    embedding_model: str = "all-MiniLM-L6-v2"  # sentence-transformers, if used
    memory_dir: str = str(ROOT_DIR / ".memory")  # per-character JSONL stores
    short_term_turns: int = 8  # rolling buffer: last N exchanges kept verbatim
    long_term_top_k: int = 6  # budget: max memories the relevance scorer injects per turn
    # (raised 4->6 after the engine stress test: a defining high-importance memory — e.g. a
    # betrayal — was edged out of the top-4 at long range by a query more *similar* to lesser
    # memories. The extra headroom lets the wound resurface on an off-topic reconciliation.)
    # Write-time dedup: skip storing a memory that's an exact or near-duplicate of an
    # existing one (raw-cosine >= this), so e.g. firing remember() twice doesn't store —
    # or inject — the same fact twice. High threshold to only catch true duplicates.
    memory_dedup_threshold: float = 0.97
    # Dev: emit the retrieved memories + their RR score breakdown to the browser each turn,
    # so the relevance realization is observable. Off in production.
    memory_debug: bool = False
    # Freeze ALL long-term stores (writes become no-ops, recall still works) for the whole
    # process. For controlled A/B runs: pre-seed a fixture, then no turn can mutate it, so
    # every model sees identical memory. Per-character game_data.engine.memory_readonly also
    # exists; this is the global override.
    memory_readonly: bool = False

    # --- Relevance realization (opponent-processing memory recall) ---
    # Each weight is a pole of the dialectic the scorer balances (see memory/relevance.py):
    #   similarity = focusing/exploitation   recency = temporal salience
    #   importance = goal/arena bearing      diversity = exploration (redundancy penalty)
    # Tune the balance per deployment; relevance_floor drops weak matches instead of
    # always returning the nearest k.
    rr_weight_similarity: float = 1.0
    rr_weight_recency: float = 0.35
    rr_weight_importance: float = 0.7  # raised 0.5->0.7 (stress test): a defining event should
    # intrude on recall even when the current query isn't on its topic — that's the goal/arena
    # bearing pole, and how a grudge or a pivotal moment actually resurfaces.
    rr_weight_diversity: float = 0.4
    rr_recency_half_life: float = 20.0
    rr_relevance_floor: float = 0.15
    # Similarity spreading to counter embedding anisotropy (issue #3): "zscore" (gentle,
    # default), "minmax" (aggressive), or "none". Computed within each turn's candidates.
    rr_similarity_spread: str = "zscore"
    rr_spread_gain: float = 1.5  # zscore logistic steepness (higher = wider spread)
    # Temporal decay (issue #5): when a memory carries a game clock, recency fades over
    # game-time with a half-life stretched by salience + reinforcement. Units are the GAME's
    # (engine is game-agnostic) — set rr_decay_half_life to the game's time scale.
    rr_decay_half_life: float = 30.0        # base half-life (importance 0) in the game's units
    rr_decay_importance_scale: float = 50.0  # half-life *= scale**importance (super-linear)
    rr_decay_reinforce_gain: float = 1.0     # small n -> half-life ~* (1+gain*n) (initial slope)
    rr_decay_reinforce_cap: float = 12.0     # ...with diminishing returns, asymptoting at (1+cap)x
                                             # so endless recall can't make a memory permanent
    # Recall-as-reinforcement (issue #5), OPT-IN: when on, retrieving a memory reinforces it
    # (rehearsal) so frequently-recalled memories resist decay. The simulation shows this is
    # selective (never-recalled memories still fade — no blanket inflation). Off by default;
    # writes the store on each retrieve, so leave off for read-only/throughput-sensitive runs.
    reinforce_on_recall: bool = False
    # Character-aware salience: at write time, an LLM rates how memorable an exchange is
    # TO THIS character (their goals/temperament), setting its memory `importance` — so
    # the brother's death is salient for a caring Bri but ~nil for a cold Corvin. Runs in
    # the background (off the critical path). Set false to store at a flat 0.5.
    salience_scoring: bool = True
    salience_model: str = "claude-sonnet-4-6"  # nuanced judgement; drop to haiku for cost
    # Commitment DETECTION (issue #4-B), OPT-IN: when on, the per-turn background salience
    # call ALSO extracts any concrete promise/obligation the character just made and creates
    # a commitment — no extra round-trip (folded into the salience call), ~0 player latency.
    # Off by default: it's fuzzy (false positives/misses), so toggle it on for beta A/B.
    commitment_detection: bool = False
    # Dynamic relationship state (issue #6), OPT-IN: when on, the per-turn background call
    # ALSO returns how the exchange moved the character's feelings toward the player
    # (affection/trust/respect deltas + mood), folded in (no extra round-trip). RR note: this
    # is the agent's CARING conditioning the relevance realizer, not just tone. Off by default.
    relationship_state: bool = False
    # Evolving intent / short-term goals (issue #8), OPT-IN: the same background call ALSO sets
    # the character's immediate aim with the player (a short agenda they pursue), folded in.
    # Injected so they act proactively, and folds into the arena query so recall serves the aim
    # (RR: relevance relative to the agent's goals). Off by default.
    intent_state: bool = False
    # Reflection / consolidation (issue #9), OPT-IN: periodically compress raw exchanges into
    # higher-level BELIEFS (through-lines) stored as high-importance memories that persist and
    # feed back into recall. Triggered when the importance accumulated since the last reflection
    # crosses the threshold (generative-agents style), so it's infrequent + off the critical path.
    reflection_enabled: bool = False
    reflection_importance_threshold: float = 3.0  # sum of exchange-importance that triggers a cycle
    reflection_max_inputs: int = 12               # most-recent exchanges fed to a reflection
    reflection_importance: float = 0.85           # beliefs are through-lines -> stored salient
    reflection_model: str = "claude-sonnet-4-6"   # synthesis needs nuance; matches salience_model
    # Arena query (Track E / issue #2): build the long-term retrieval query from the player
    # input + recent conversation + Situation + goals (not just the last line), so recall
    # resolves referents ("her" -> mom) and thin queries. False = search the last line only.
    arena_query: bool = True
    arena_query_recent_turns: int = 2

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so we parse `.env` exactly once."""
    return Settings()
