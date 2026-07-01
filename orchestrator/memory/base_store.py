"""Shared persistence foundation for the per-namespace character stores (arch review theme A).

The five sibling stores (long-term memory, relationship, intent, agency, commitments) hold the
character's MIND on disk — the product's core asset. This module gives them the guarantees they
could not give individually:

- ATOMIC writes (tmp + fsync + os.replace): a crash mid-write can no longer truncate a store —
  the old file survives until the new one is fully on disk.
- ONE lock per store file, shared by every instance in the process: concurrent writers (two
  sessions on one character, a backgrounded reflect racing the next turn) can no longer clobber
  each other's rewrites.
- LOUD corruption handling: a damaged store is quarantined to `<file>.corrupt-<ts>` and logged at
  ERROR — never silently reset to a fresh default. (A betrayal scar quietly vanishing is the worst
  kind of bug for this engine: invisible AND thematic.)

The stores keep their domain logic; this owns only the persistence discipline.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def safe_name(namespace: str) -> str:
    """Filesystem-safe store name for a character namespace. NOTE: lossy — distinct namespaces can
    collide after sanitization; a hash-suffix migration is deferred (would orphan existing stores)."""
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", namespace).strip("-") or "default"


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def lock_for(path) -> threading.RLock:
    """The process-wide lock for a store file — every instance over the same path shares it."""
    key = str(path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = _LOCKS[key] = threading.RLock()
        return lock


def atomic_write_text(path, text: str) -> None:
    """Crash-safe whole-file write: temp file in the same directory, fsync, then an atomic
    os.replace. The previous version survives any crash before the replace lands."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def quarantine(path, reason: str) -> None:
    """Move a damaged store aside LOUDLY. The caller then starts from a fresh default — but the
    evidence is preserved and the operator is told, instead of silent permanent amnesia."""
    path = Path(path)
    try:
        dest = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
        os.replace(path, dest)
        logger.error(
            "CORRUPT store %s (%s) — quarantined to %s; state starts fresh. If this was real "
            "data, restore it from a save/backup.", path.name, reason, dest.name)
    except OSError:
        logger.error("CORRUPT store %s (%s) — and it could not be quarantined; leaving in place.",
                     path, reason)
