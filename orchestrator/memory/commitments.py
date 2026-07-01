"""Commitment tracking (issue #4): durable obligations a character has made.

A commitment — a promise, deal, or constraint ("meet at dawn", "don't tell anyone the
player's name", "you owe me a favor") — is a STANDING CONCERN, not a decaying recollection.
While OPEN it is always injected into the prompt, so it never falls out of context or
competes in the relevance top-k, and it does not decay. When it CLOSES (the game marks it
fulfilled/broken, or it expires past its due clock) the engine converts it into an ordinary
long-term memory — the character remembers the outcome, but it's no longer an active duty.

The GAME owns creation/resolution (the `commit` / `resolve_commitment` WS seam, siblings of
`remember`). Game-time is the game's own monotonic clock (same one decay uses).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings
from .base_store import atomic_write_text, lock_for
from .base_store import safe_name as _safe_name

OPEN, FULFILLED, BROKEN, EXPIRED = "open", "fulfilled", "broken", "expired"
_TERMINAL = {FULFILLED, BROKEN, EXPIRED}


@dataclass
class Commitment:
    text: str                                   # "meet the player at the harbor at dawn"
    id: str                                     # stable id, for resolve
    status: str = OPEN                          # open | fulfilled | broken | expired
    made_t: float | None = None                 # game clock when made
    due_t: float | None = None                  # numeric clock for expiry (optional)
    due: str = ""                               # human-readable deadline, for display (optional)
    parties: list[str] = field(default_factory=list)  # who it's to, e.g. ["the player"]
    importance: float = 0.5                     # how SIGNIFICANT this obligation is to the NPC
                                                # (0-1) — drives how strongly the eventual
                                                # memory of keeping/breaking it persists

    def render(self) -> str:
        # Parties stay metadata (often the text already names them); only the deadline is
        # worth surfacing inline, and only when the game gave a human-readable one.
        by = f" (due {self.due})" if self.due else ""
        return f"- {self.text}{by}"

    def memory_text(self) -> str:
        """How a closed commitment reads once it becomes an ordinary memory."""
        verb = {FULFILLED: "kept", BROKEN: "broke", EXPIRED: "let lapse"}.get(self.status, "closed")
        who = (" to " + ", ".join(self.parties)) if self.parties else ""
        return f"I {verb} my promise{who}: {self.text}"

    def memory_importance(self) -> float:
        """How significant the *resulting memory* is — it inherits the commitment's own
        significance to the NPC, and an UNKEPT promise (broken/expired) stings a little
        more. So a high-stakes betrayal (let someone go to debtor's prison) stays vivid for
        in-game years via the super-linear decay, while a trivial broken promise still fades."""
        if self.status in (BROKEN, EXPIRED):
            return min(1.0, self.importance + 0.1)
        return self.importance  # fulfilled/kept: as significant as the promise was


def render_commitments(items: list[Commitment]) -> str:
    """Render the OPEN commitments into an always-injected prompt section, or "" if none."""
    if not items:
        return ""
    lines = "\n".join(c.render() for c in items)
    return (
        "# Open commitments you've made\n"
        "Promises, deals, and constraints you have stated to others and not yet resolved. You "
        "KNOW you made each of these. Whether you keep, bend, or break one is up to WHO YOU "
        "ARE — an honest character honors their word; a cunning or self-serving one may exploit "
        "or abandon a promise the moment it no longer suits them. Stay in character.\n" + lines
    )


class CommitmentStore:
    """Per-character commitments, persisted alongside long-term memory. Small (a handful of
    open obligations), so we keep them in memory and rewrite the file on each change."""

    def __init__(self, namespace: str, *, readonly: bool = False) -> None:
        settings = get_settings()
        self.readonly = readonly
        self._path = Path(settings.memory_dir) / f"{_safe_name(namespace)}.commitments.jsonl"
        self._lock = lock_for(self._path)
        self._items: list[Commitment] | None = None

    def _all(self) -> list[Commitment]:
        if self._items is None:
            self._items = self._load()
        return self._items

    def _load(self) -> list[Commitment]:
        if not self._path.exists():
            return []
        out: list[Commitment] = []
        bad = 0
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if d.get("text") and d.get("id"):
                out.append(Commitment(
                    text=d["text"], id=d["id"], status=d.get("status", OPEN),
                    made_t=d.get("made_t"), due_t=d.get("due_t"), due=d.get("due", ""),
                    parties=list(d.get("parties") or []),
                    importance=float(d.get("importance", 0.5)),
                ))
        if bad:
            import logging
            logging.getLogger(__name__).error(
                "Commitment store %s: skipped %d corrupt line(s) at load — obligations were lost "
                "to a past bad write.", self._path.name, bad)
        return out

    def _save(self) -> None:
        if self.readonly:
            return
        atomic_write_text(self._path, "".join(
            json.dumps({
                "text": c.text, "id": c.id, "status": c.status, "made_t": c.made_t,
                "due_t": c.due_t, "due": c.due, "parties": c.parties,
                "importance": c.importance,
            }, ensure_ascii=False) + "\n"
            for c in self._all()))

    # --- writes (game-owned) ---

    def add(self, text: str, *, made_t: float | None = None, due_t: float | None = None,
            due: str = "", parties: list[str] | None = None,
            importance: float = 0.5) -> Commitment | None:
        text = (text or "").strip()
        if not text or self.readonly:
            return None
        with self._lock:
            c = Commitment(text=text, id=uuid.uuid4().hex[:12], made_t=made_t, due_t=due_t,
                           due=(due or "").strip(), parties=parties or [],
                           importance=max(0.0, min(1.0, importance)))
            self._all().append(c)
            self._save()
            return c

    def resolve(self, commitment_id: str, status: str) -> Commitment | None:
        """Close a commitment (fulfilled/broken). Returns it so the engine can convert it
        into an ordinary memory; returns None if it's unknown or already closed."""
        if status not in (FULFILLED, BROKEN) or self.readonly:  # frozen under readonly
            return None
        with self._lock:
            for c in self._all():
                if c.id == commitment_id and c.status == OPEN:
                    c.status = status
                    self._save()
                    return c
            return None

    def sweep_expired(self, now_t: float | None) -> list[Commitment]:
        """Mark open commitments whose due clock has PASSED as EXPIRED. Strictly past
        (now_t > due_t), so a commitment 'due by day 2' stays open *during* day 2 and only
        lapses once the clock moves beyond it — the actor gets the whole due window. Returns
        the expired ones so the engine can convert each to a memory. No-op without a clock
        and FROZEN under readonly (an eval/replay arm must not flip statuses even in memory)."""
        if now_t is None or self.readonly:
            return []
        with self._lock:
            expired = [c for c in self._all()
                       if c.status == OPEN and c.due_t is not None and now_t > c.due_t]
            for c in expired:
                c.status = EXPIRED
            if expired:
                self._save()
            return expired

    # --- reads ---

    def open_items(self) -> list[Commitment]:
        return [c for c in self._all() if c.status == OPEN]
