"""Shared harness for the tools/ stress + demo scripts (arch review theme F): the env-flag
preamble, .memory wipe helper, and engine construction that ~17 scripts each re-implemented.

    from tools._harness import bootstrap, make_engine, set_flags, wipe

    bootstrap()                       # sys.path + .env + stdout encoding
    set_flags(relationship_state=True, reflection_enabled=True)
    wipe("corvin-ashgrave-inworld")
    eng = make_engine("corvin-ashgrave-inworld", model="claude-sonnet-4-6")

Flags are applied as EngineCaps overrides at make_engine() time (per-engine, per the arch review —
NOT by mutating the global settings), so two harness engines can run different capability sets.
"""
from __future__ import annotations

import glob
import os
import pathlib
import sys

_FLAGS: dict = {}


def bootstrap() -> None:
    """Repo-on-path + .env + UTF-8-safe stdout. Call first, before engine imports if possible."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from dotenv import load_dotenv
    load_dotenv(".env")


def set_flags(**flags) -> None:
    """Capability overrides for subsequently-constructed harness engines (EngineCaps fields:
    relationship_state, reflection_enabled, intent_state, salience_scoring, ...)."""
    _FLAGS.update(flags)


def wipe(*slugs: str) -> None:
    """Delete the persisted stores for these character slugs (and invalidate live caches)."""
    from orchestrator.character_store import load_character
    from orchestrator.config import get_settings
    from orchestrator.memory.long_term import LongTermMemory
    mem = pathlib.Path(get_settings().memory_dir)
    for slug in slugs:
        ns = load_character(slug).memory_namespace
        for f in glob.glob(str(mem / f"{ns}.*")):
            os.remove(f)
        LongTermMemory.invalidate(ns)


def make_engine(slug: str, *, model: str | None = None, max_tokens: int | None = None,
                readonly: bool = False, **cap_overrides):
    """An Engine for `slug` with the harness flags (+ per-call overrides) as its capability set."""
    from orchestrator.adapters.llm_anthropic import AnthropicLLM
    from orchestrator.character_store import load_character
    from orchestrator.config import EngineCaps, get_settings
    from orchestrator.engine import Engine
    caps = EngineCaps.from_settings(get_settings(), **{**_FLAGS, **cap_overrides})
    if model and model.startswith("local/"):
        # same routing rule as judgment.py: "local/<name>" = the actor seat on a self-hosted
        # OpenAI-compatible endpoint (Ollama / llama-server; base via LOCAL_JUDGE_BASE_URL)
        from orchestrator.adapters.llm_openai_compat import OpenAICompatLLM
        llm: object = OpenAICompatLLM(model=model[len("local/"):], max_tokens=max_tokens or 1024,
                                      reasoning_effort=os.environ.get("LOCAL_ACTOR_REASONING", "none"))
    else:
        llm = AnthropicLLM(model=model, max_tokens=max_tokens) if (model or max_tokens) else AnthropicLLM()
    return Engine(load_character(slug), llm, readonly=readonly, caps=caps)
