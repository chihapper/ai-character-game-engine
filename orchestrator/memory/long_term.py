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
from .base_store import atomic_write_text, lock_for, safe_name
from .relevance import MemoryRecord, RelevanceWeights, cosine, realize_relevance

logger = logging.getLogger(__name__)

_LEXICAL_DIM = 256

# Shared embedder for the process: (embed_fn, embed_many_fn, dim, name). Built lazily.
_embedder = None

# ONE records list per store file, shared by every instance in the process (keyed by path).
# Two instances over the same namespace (a sandbox engine + a voice session, two tabs) otherwise
# each cache their own copy and a whole-store rewrite from the staler one erases the other's
# writes — silent memory loss. Guarded by base_store.lock_for(path).
_SHARED_RECORDS: dict[str, list[MemoryRecord]] = {}


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
        # Cast to native floats — fastembed yields numpy float32, which isn't JSON
        # serializable (the debug emit) and is best kept out of the rest of the engine.
        return (lambda t: [float(x) for x in next(iter(model.embed([t])))],
                lambda ts: [[float(x) for x in v] for v in model.embed(list(ts))],
                dim, "fastembed")
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
        return (lambda t: model.encode(t).tolist(),
                lambda ts: [v.tolist() for v in model.encode(list(ts))],
                dim, "sentence-transformers")
    except Exception:
        logger.warning(
            "Long-term memory embedder: lexical fallback (install fastembed for semantic "
            "embeddings; recall still works, just coarser)."
        )
        return (_lexical_embed, lambda ts: [_lexical_embed(t) for t in ts],
                _LEXICAL_DIM, "lexical")


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = _make_embedder()
    return _embedder


def warm_embedder() -> str:
    """Build + exercise the process embedder once, eagerly. The fastembed model loads
    lazily on first embed (~0.5s), which otherwise lands on the player's first turn; call
    this at startup so turn 1 pays the warm price (~ms) like every other turn. Returns the
    embedder name."""
    embed, _, _, name = _get_embedder()
    embed("warm")
    return name


_safe_name = safe_name  # canonical impl lives in base_store; alias kept for existing importers


class LongTermMemory:
    def __init__(self, namespace: str, *, readonly: bool = False, speaker: str = "Me") -> None:
        settings = get_settings()
        self._namespace = namespace
        # How the character's own past lines are labelled in stored exchange text (recalled
        # into the prompt). First-person "Me" by default — never the raw namespace slug.
        self._speaker = speaker or "Me"
        self.readonly = readonly  # if True, writes are no-ops (recall still works)
        self._budget = settings.long_term_top_k
        self._weights = RelevanceWeights(
            similarity=settings.rr_weight_similarity,
            recency=settings.rr_weight_recency,
            importance=settings.rr_weight_importance,
            diversity=settings.rr_weight_diversity,
            recency_half_life=settings.rr_recency_half_life,
            floor=settings.rr_relevance_floor,
            spread=settings.rr_similarity_spread,
            spread_gain=settings.rr_spread_gain,
            decay_half_life=settings.rr_decay_half_life,
            decay_importance_scale=settings.rr_decay_importance_scale,
            decay_reinforce_gain=settings.rr_decay_reinforce_gain,
            decay_reinforce_cap=settings.rr_decay_reinforce_cap,
        )
        self._dedup_threshold = settings.memory_dedup_threshold
        self._reinforce_on_recall = settings.reinforce_on_recall
        self._path = Path(settings.memory_dir) / f"{_safe_name(namespace)}.jsonl"
        self._lock = lock_for(self._path)  # shared by every instance over this store file

    # --- store ---

    def _all(self) -> list[MemoryRecord]:
        """The records list — ONE shared object per store file across all instances, so a rewrite
        from any instance is always from the current truth (no stale-copy clobbering)."""
        key = str(self._path)
        records = _SHARED_RECORDS.get(key)
        if records is None:
            with self._lock:
                records = _SHARED_RECORDS.get(key)
                if records is None:  # double-checked under the lock
                    records = _SHARED_RECORDS[key] = self._load()
        return records

    def _set_records(self, records: list[MemoryRecord]) -> None:
        """Rebind the shared list (belief supersede/evict rebuilds it) — through the registry, so
        every instance sees the new truth."""
        _SHARED_RECORDS[str(self._path)] = records

    @classmethod
    def invalidate(cls, namespace: str) -> None:
        """Drop the shared cache for a namespace after its files were deleted/replaced OUTSIDE the
        store (a sandbox reset, a save-game restore, a game-start wipe) — otherwise a live instance
        would resurrect the deleted state from memory on its next write."""
        path = Path(get_settings().memory_dir) / f"{_safe_name(namespace)}.jsonl"
        with lock_for(path):
            _SHARED_RECORDS.pop(str(path), None)

    @classmethod
    def invalidate_all(cls) -> None:
        """Drop every shared cache — for whole-directory operations (a save-game restore)."""
        _SHARED_RECORDS.clear()

    def beliefs(self, limit: int = 8) -> list[str]:
        """The character's consolidated BELIEFS (issue #9), most recent last — so a reflection
        cycle can deepen or revise the convictions already held, not just pile on new ones."""
        return [r.text for r in self._all() if r.kind == "belief"][-limit:]

    def _load(self) -> list[MemoryRecord]:
        if not self._path.exists():
            return []
        _, embed_many, _, _ = _get_embedder()
        rows: list[tuple[int, dict]] = []
        bad = 0
        for i, line in enumerate(self._path.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if d.get("text"):
                rows.append((i, d))
        if bad:
            # LOUD, not silent: skipped lines mean a past partial/interrupted write. The salvage is
            # right for an append-format store, but the operator must know memories were lost.
            logger.error("Memory store %s: skipped %d corrupt line(s) while loading — "
                         "some of this character's memories were lost to a past bad write.",
                         self._path.name, bad)
        # Batch-embed: one model call for the whole store instead of one per record (a full-history
        # per-record loop made every fresh instance pay seconds of embed time at load).
        vectors = embed_many([d["text"] for _, d in rows]) if rows else []
        return [
            MemoryRecord(
                text=d["text"],
                embedding=vec,  # derived at load — survives embedder swaps
                index=int(d.get("index", i)),
                importance=float(d.get("importance", 0.5)),
                kind=d.get("kind", "exchange"),
                when=d.get("when", ""),
                t=d.get("t"),  # game clock at creation (None on legacy records -> index recency)
                last_t=d.get("last_t", d.get("t")),
                reinforcement=int(d.get("reinforcement", 0)),
            )
            for (i, d), vec in zip(rows, vectors)
        ]

    @staticmethod
    def _to_json(r: MemoryRecord) -> str:
        """Serialize a record to a JSONL line — embeddings are derived at load, never stored.
        Decay fields are written only when set so legacy/clockless stores stay compact."""
        d = {"text": r.text, "importance": r.importance, "kind": r.kind,
             "when": r.when, "index": r.index}
        if r.t is not None:
            d["t"] = r.t
        if r.last_t is not None and r.last_t != r.t:
            d["last_t"] = r.last_t
        if r.reinforcement:
            d["reinforcement"] = r.reinforcement
        return json.dumps(d, ensure_ascii=False)

    def _rewrite(self, records: list[MemoryRecord]) -> None:
        """Rewrite the whole store (the JSONL is otherwise append-only). Used when an existing
        record is mutated in place — e.g. a reinforcement bump. Per-character stores are small,
        so a full rewrite on the occasional dedup-hit is cheap. ATOMIC (tmp + fsync + replace):
        a crash mid-rewrite can no longer truncate the character's memory."""
        atomic_write_text(self._path, "".join(self._to_json(r) + "\n" for r in records))

    def _add_sync(self, text: str, importance: float, kind: str, when: str,
                  t: float | None = None) -> None:
        if self.readonly:
            return
        embed, _, _, _ = _get_embedder()
        embedding = embed(text)
        importance = max(0.0, min(1.0, importance))
        with self._lock:
            records = self._all()
            # Write-time dedup. A re-encounter of an existing memory (exact or near-duplicate) is
            # REINFORCEMENT (issue #5), not a no-op: bump the count and refresh 'last seen' so its
            # decay restarts from now — repetition makes it stick. Keep the higher importance.
            norm = text.strip().lower()
            for r in records:
                if r.text.strip().lower() == norm or cosine(embedding, r.embedding) >= self._dedup_threshold:
                    r.reinforcement += 1
                    if t is not None:
                        r.last_t = t
                    if importance > r.importance:
                        r.importance = importance
                    self._rewrite(records)
                    logger.info("Reinforced memory (x%d): %r", r.reinforcement, text[:60])
                    return
            index = records[-1].index + 1 if records else 0
            record = MemoryRecord(
                text=text, embedding=embedding, index=index, importance=importance,
                kind=kind, when=when, t=t, last_t=t, reinforcement=0,
            )
            records.append(record)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(self._to_json(record) + "\n")

    # --- writes ---

    async def add_exchange(
        self, user_text: str, assistant_text: str, *, importance: float = 0.5,
        when: str = "", t: float | None = None
    ) -> None:
        if not user_text or not assistant_text:
            return
        document = f"User: {user_text}\n{self._speaker}: {assistant_text}"
        await asyncio.to_thread(self._add_sync, document, importance, "exchange", when, t)

    def _add_belief_sync(self, text: str, importance: float, t: float | None, threshold: float) -> None:
        if self.readonly:
            return
        embed, _, _, _ = _get_embedder()
        embedding = embed(text)
        importance = max(0.0, min(1.0, importance))
        with self._lock:
            records = self._all()
            # Supersede near-duplicate BELIEFS (issue #15): a reworded conviction REPLACES the old one
            # instead of piling up. (Episodic memories use the much higher exact-dup threshold + reinforce.)
            records = [r for r in records
                       if not (r.kind == "belief" and cosine(embedding, r.embedding) >= threshold)]
            index = max((r.index for r in records), default=-1) + 1
            records.append(MemoryRecord(text=text, embedding=embedding, index=index, importance=importance,
                                        kind="belief", when="", t=t, last_t=t, reinforcement=0))
            cap = get_settings().belief_max  # bound the set: evict the oldest beliefs past the cap (#15)
            belief_recs = [r for r in records if r.kind == "belief"]
            if len(belief_recs) > cap:
                drop = {id(r) for r in sorted(belief_recs, key=lambda r: r.index)[: len(belief_recs) - cap]}
                records = [r for r in records if id(r) not in drop]
            self._set_records(records)  # rebind through the registry — every instance sees the new list
            self._rewrite(records)

    async def add_belief(self, text: str, *, importance: float = 0.85, t: float | None = None,
                         threshold: float | None = None) -> None:
        """Store a consolidated belief (issue #9), superseding any near-duplicate belief already
        held so convictions stay a tight, evolving set rather than reworded copies (issue #15)."""
        if not text.strip():
            return
        thr = threshold if threshold is not None else get_settings().belief_dedup_threshold
        await asyncio.to_thread(self._add_belief_sync, text, importance, t, thr)

    async def remember(
        self, fact: str, *, when: str = "", kind: str = "world_event",
        importance: float = 0.7, t: float | None = None
    ) -> None:
        """Durable memory-write API for the GAME: persist a world event into a character's
        memory so retrieval can surface it later ("Player burned the bridge", when="day 3").
        World events default to a higher salience than ordinary exchanges. `when` is the
        game's opaque time tag; `kind` lets retrieval/decay treat events and dialogue alike."""
        fact = (fact or "").strip()
        if not fact:
            return
        await asyncio.to_thread(self._add_sync, fact, importance, kind, when, t)

    # --- reads ---

    def _reinforce_recalled(self, selected: list[MemoryRecord], now_t: float | None) -> None:
        """Recall-as-reinforcement (opt-in, issue #5): retrieving a memory rehearses it — bump
        its count and refresh 'last seen' so its decay restarts from now. Persisted, so a
        frequently-recalled memory resists decay. No-op when off or read-only."""
        if not self._reinforce_on_recall or self.readonly or not selected:
            return
        with self._lock:
            for m in selected:
                m.reinforcement += 1
                if now_t is not None:
                    m.last_t = now_t
            self._rewrite(self._all())

    def _retrieve_sync(self, query: str, k: int, now_t: float | None) -> list[str]:
        embed, _, _, _ = _get_embedder()
        qvec = embed(query)
        with self._lock:  # scan + possible reinforce-rewrite as one unit vs concurrent writers
            records = self._all()
            if not records:
                return []
            selected = realize_relevance(
                qvec, records, weights=self._weights, budget=k,
                now_index=len(records), now_t=now_t,
            )
            self._reinforce_recalled(selected, now_t)
            return [r.text for r in selected]

    async def retrieve(self, query: str, k: int | None = None, *, now_t: float | None = None) -> list[str]:
        if not query:
            return []
        return await asyncio.to_thread(self._retrieve_sync, query, k or self._budget, now_t)

    def _retrieve_scored_sync(self, query: str, k: int, now_t: float | None) -> dict:
        embed, _, _, name = _get_embedder()
        qvec = embed(query)
        with self._lock:
            records = self._all()
            if not records:
                return {"selected": [], "scored": [], "embedder": name}
            selected, breakdown = realize_relevance(
                qvec, records, weights=self._weights, budget=k,
                now_index=len(records), now_t=now_t, return_debug=True,
            )
            self._reinforce_recalled(selected, now_t)
            return {"selected": [r.text for r in selected], "scored": breakdown, "embedder": name}

    async def retrieve_scored(self, query: str, k: int | None = None, *, now_t: float | None = None) -> dict:
        """Like `retrieve`, but also returns the per-candidate RR score breakdown (for the
        dev memory-debug panel). `{selected: [text], scored: [...], embedder: name}`."""
        if not query:
            return {"selected": [], "scored": [], "embedder": _get_embedder()[3]}
        return await asyncio.to_thread(self._retrieve_scored_sync, query, k or self._budget, now_t)

    def _rank_window_sync(self, query, since_t, now_t, k, floor, exclude_kinds):
        with self._lock:
            records = list(self._all())  # stable snapshot for the scan below
        window = [r for r in records
                  if (since_t is None or (r.t is not None and r.t > since_t))
                  and r.kind not in exclude_kinds]
        if not window:
            return [], []
        embed, _, _, _ = _get_embedder()
        # RR-rank within the window with the SAME scorer the conversational path uses, so the
        # foreground is what's most relevant to who this character is + wants, with diversity — not
        # just the loudest by static importance.
        foreground = list(realize_relevance(
            embed(query), window, weights=self._weights,
            budget=min(k, len(window)), now_index=len(records), now_t=now_t,
        ))
        # Hard floor: a death/betrayal-grade event is never relegated to the background, even if the
        # ranker would (#24 guardrail against mis-ranking).
        for r in window:
            if r.importance >= floor and r not in foreground:
                foreground.append(r)
        tail = [r for r in window if r not in foreground]
        return foreground, tail

    async def rank_window(self, query: str, *, since_t: float | None, now_t: float | None = None,
                          k: int = 6, floor: float = 0.9, exclude_kinds: tuple = ()) -> tuple[list, list]:
        """RR-rank the memories in a time window (developments since `since_t`) and split them into
        (foreground, tail): the `k` most RELEVANT-to-`query` shown in full plus any importance>=floor
        force-kept, and the remainder as background. `exclude_kinds` drops kinds already rendered
        elsewhere (e.g. player exchanges). Lets the deliberation foreground what matters to who the NPC
        is becoming and acknowledge — never silently drop — a high volume of events (#24)."""
        if not query:
            return [], []
        return await asyncio.to_thread(self._rank_window_sync, query, since_t, now_t, k, floor, exclude_kinds)
