"""Long-term memory: cross-session recall, scored by relevance realization.

Each completed exchange — and any durable world event the game pushes via `remember` —
is stored per character (one JSONL file per memory namespace) with the metadata the
relevance scorer needs: an `importance`/salience weight, a `kind`, and the game's
opaque `when` tag. On each turn, `retrieve` selects memories with
`memory.relevance.realize_relevance` — an opponent-processing balance of similarity,
recency, importance, and diversity under a budget — rather than a fixed semantic top-k.

**Always on.** Embeddings come from sentence-transformers when installed; otherwise a
dependency-free lexical fallback keeps recall working (degraded but functional) instead
of disabling memory entirely. Per-character stores are small (hundreds–low-thousands of
entries), so we keep the records in memory and brute-force the scoring — no native ANN
index to build (the Windows/Chroma pain point). Embeddings are derived from text at load
time, so the on-disk store stays human-readable and survives an embedder swap.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path

from ..config import get_settings
from .relevance import MemoryRecord, RelevanceWeights, realize_relevance

logger = logging.getLogger(__name__)

_LEXICAL_DIM = 256

# Shared embedder for the process: (embed_fn, dim, name). Built lazily.
_embedder = None


def _lexical_embed(text: str) -> list[float]:
    """Dependency-free fallback: a stable hashed bag-of-words, L2-normalized. Stable across
    runs (hashlib, not the salted builtin hash) so a query matches stored text."""
    vec = [0.0] * _LEXICAL_DIM
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16) % _LEXICAL_DIM
        vec[h] += 1.0
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec] if norm else vec


def _make_embedder():
    settings = get_settings()
    # Preferred: fastembed (ONNX, no torch, Windows-friendly — issue #1's pick).
    try:
        from fastembed import TextEmbedding

        model = TextEmbedding(model_name=settings.fastembed_model)
        dim = len(next(iter(model.embed(["probe"]))))
        logger.info(
            "Long-term memory embedder: fastembed '%s' (dim=%d)", settings.fastembed_model, dim
        )
        return (lambda t: list(next(iter(model.embed([t])))), dim, "fastembed")
    except Exception:
        pass
    # Next: sentence-transformers, if installed.
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(settings.embedding_model)
        dim = model.get_sentence_embedding_dimension()
        logger.info(
            "Long-term memory embedder: sentence-transformers '%s' (dim=%d)",
            settings.embedding_model, dim,
        )
        return (lambda t: model.encode(t).tolist(), dim, "sentence-transformers")
    except Exception:
        logger.warning(
            "Long-term memory embedder: lexical fallback (install fastembed for semantic "
            "embeddings; recall still works, just coarser)."
        )
        return (_lexical_embed, _LEXICAL_DIM, "lexical")


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = _make_embedder()
    return _embedder


def _safe_name(namespace: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", namespace).strip("-") or "default"


class LongTermMemory:
    def __init__(self, namespace: str) -> None:
        settings = get_settings()
        self._namespace = namespace
        self._budget = settings.long_term_top_k
        self._weights = RelevanceWeights(
            similarity=settings.rr_weight_similarity,
            recency=settings.rr_weight_recency,
            importance=settings.rr_weight_importance,
            diversity=settings.rr_weight_diversity,
            recency_half_life=settings.rr_recency_half_life,
            floor=settings.rr_relevance_floor,
        )
        self._path = Path(settings.memory_dir) / f"{_safe_name(namespace)}.jsonl"
        self._records: list[MemoryRecord] | None = None  # lazily loaded + cached

    # --- store ---

    def _all(self) -> list[MemoryRecord]:
        if self._records is None:
            self._records = self._load()
        return self._records

    def _load(self) -> list[MemoryRecord]:
        if not self._path.exists():
            return []
        embed, _, _ = _get_embedder()
        records: list[MemoryRecord] = []
        for i, line in enumerate(self._path.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = d.get("text") or ""
            if not text:
                continue
            records.append(
                MemoryRecord(
                    text=text,
                    embedding=embed(text),  # derived at load — survives embedder swaps
                    index=int(d.get("index", i)),
                    importance=float(d.get("importance", 0.5)),
                    kind=d.get("kind", "exchange"),
                    when=d.get("when", ""),
                )
            )
        return records

    def _add_sync(self, text: str, importance: float, kind: str, when: str) -> None:
        records = self._all()
        index = records[-1].index + 1 if records else 0
        embed, _, _ = _get_embedder()
        records.append(
            MemoryRecord(
                text=text, embedding=embed(text), index=index,
                importance=max(0.0, min(1.0, importance)), kind=kind, when=when,
            )
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"text": text, "importance": importance, "kind": kind, "when": when, "index": index},
                ensure_ascii=False,
            ) + "\n")

    # --- writes ---

    async def add_exchange(
        self, user_text: str, assistant_text: str, *, importance: float = 0.5, when: str = ""
    ) -> None:
        if not user_text or not assistant_text:
            return
        document = f"User: {user_text}\n{self._namespace}: {assistant_text}"
        await asyncio.to_thread(self._add_sync, document, importance, "exchange", when)

    async def remember(
        self, fact: str, *, when: str = "", kind: str = "world_event", importance: float = 0.7
    ) -> None:
        """Durable memory-write API for the GAME: persist a world event into a character's
        memory so retrieval can surface it later ("Player burned the bridge", when="day 3").
        World events default to a higher salience than ordinary exchanges. `when` is the
        game's opaque time tag; `kind` lets retrieval/decay treat events and dialogue alike."""
        fact = (fact or "").strip()
        if not fact:
            return
        await asyncio.to_thread(self._add_sync, fact, importance, kind, when)

    # --- reads ---

    def _retrieve_sync(self, query: str, k: int) -> list[str]:
        records = self._all()
        if not records:
            return []
        embed, _, _ = _get_embedder()
        selected = realize_relevance(
            embed(query), records, weights=self._weights, budget=k, now_index=len(records)
        )
        return [r.text for r in selected]

    async def retrieve(self, query: str, k: int | None = None) -> list[str]:
        if not query:
            return []
        return await asyncio.to_thread(self._retrieve_sync, query, k or self._budget)

    def _retrieve_scored_sync(self, query: str, k: int) -> dict:
        records = self._all()
        if not records:
            return {"selected": [], "scored": [], "embedder": _get_embedder()[2]}
        embed, _, name = _get_embedder()
        selected, breakdown = realize_relevance(
            embed(query), records, weights=self._weights, budget=k,
            now_index=len(records), return_debug=True,
        )
        return {"selected": [r.text for r in selected], "scored": breakdown, "embedder": name}

    async def retrieve_scored(self, query: str, k: int | None = None) -> dict:
        """Like `retrieve`, but also returns the per-candidate RR score breakdown (for the
        dev memory-debug panel). `{selected: [text], scored: [...], embedder: name}`."""
        if not query:
            return {"selected": [], "scored": [], "embedder": _get_embedder()[2]}
        return await asyncio.to_thread(self._retrieve_scored_sync, query, k or self._budget)
