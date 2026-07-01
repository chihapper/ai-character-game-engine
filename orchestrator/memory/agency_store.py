"""Per-character AGENCY state (issue #20): the character's evolving standing GOALS (its life
direction — autonomous deliberation can change them, generalizing the static profile goals) and
the game-clock at the last deliberation (so the engine can tell what's accumulated since). Persisted
as JSON alongside the relationship / intent stores."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import get_settings
from .base_store import atomic_write_text, lock_for, quarantine
from .base_store import safe_name as _safe_name


class AgencyStore:
    def __init__(self, namespace: str, *, readonly: bool = False) -> None:
        s = get_settings()
        self.readonly = readonly
        self._path = Path(s.memory_dir) / f"{_safe_name(namespace)}.agency.json"
        self._lock = lock_for(self._path)
        self._goals: list[str] | None = None
        self._last_t: float | None = None
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        try:
            d = json.loads(self._path.read_text(encoding="utf-8"))
            g = d.get("goals")
            self._goals = [str(x).strip() for x in g if str(x).strip()] if isinstance(g, list) and g else None
            lt = d.get("last_deliberation_t")
            self._last_t = float(lt) if isinstance(lt, (int, float)) else None
        except Exception as e:  # noqa: BLE001
            quarantine(self._path, f"unreadable agency state ({type(e).__name__})")  # loud, never silent

    def goals(self) -> list[str] | None:
        """The character's CURRENT standing goals if deliberation has evolved them, else None
        (meaning: fall back to the static profile goals)."""
        self._load()
        return list(self._goals) if self._goals else None

    def last_t(self) -> float | None:
        self._load()
        return self._last_t

    def set_goals(self, goals: list[str] | None) -> None:
        if self.readonly:  # frozen: readonly state must not evolve even in memory
            return
        with self._lock:
            self._load()
            clean = [str(g).strip() for g in (goals or []) if str(g).strip()]
            if clean:
                self._goals = clean
                self._save()

    def mark_deliberated(self, t: float | None) -> None:
        if self.readonly:
            return
        with self._lock:
            self._load()
            if t is not None:
                self._last_t = float(t)
                self._save()

    def _save(self) -> None:
        if self.readonly:
            return
        atomic_write_text(self._path,
                          json.dumps({"goals": self._goals, "last_deliberation_t": self._last_t}))
