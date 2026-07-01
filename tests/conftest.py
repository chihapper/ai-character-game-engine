"""Test bootstrap: point the engine's stores at a throwaway MEMORY_DIR *before* any orchestrator
import caches settings, and make the repo root importable. All tests here are PURE — no LLM calls,
no network — per the arch-review test seam (docs/architecture-review-2026-07.md theme F)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="engine-tests-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


@pytest.fixture
def mem_dir():
    """The throwaway memory dir the whole test session runs against."""
    return Path(os.environ["MEMORY_DIR"])
