"""Relevance realization for memory recall — an opponent-processing scorer.

Inspired by Vervaeke et al.'s *relevance realization* (RR): a limited agent in a "large
world" faces limitless possible memories, so naive semantic top-k ("everything and
nothing is relevant at the same time") is the wrong model. RR frames relevance as a
**dialectical balance of competing pressures**, relative to the agent's goals and arena,
under a resource budget. We approximate that here — honestly an approximation, since a
real RR is non-computational; but it gives an authored-goal NPC a far better grip on what
matters than cosine alone.

Each term maps to an RR opponent-processing pole:

    base(m) = w_sim * similarity(arena_query, m)   # focusing / exploitation
            + w_rec * recency(m)                    # temporal salience ("hereness/nowness")
            + w_imp * importance(m)                 # goals/arena bearing (what matters to ME)

selection is greedy with a diversity penalty (generalized MMR):

    pick m maximizing  base(m) - w_div * max_similarity(m, already_picked)
                                  └─ diversifying / exploration (avoid redundant recall)

…bounded by `budget` memories (bioeconomics — not a fixed k) and a `floor` (drop weak
matches instead of always returning the nearest). The "arena query" is the caller's
business: it should fold in the live situation + the character's goals, not just the last
user line — that's how relevance becomes relative to goals-in-context.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class MemoryRecord:
    """One stored memory plus the metadata the scorer balances."""

    text: str
    embedding: list[float]
    index: int  # monotonic insertion order — drives recency without parsing game-time
    importance: float = 0.5  # 0..1 salience captured at write time (goal/arena bearing)
    kind: str = "exchange"  # "exchange" | "world_event"
    when: str = ""  # game-supplied time tag; stored/displayed, never parsed by the engine


@dataclass
class RelevanceWeights:
    """The opponent-processing dial. Tunable; defaults favor focus while keeping a real
    recency/importance voice and a modest diversity push."""

    similarity: float = 1.0
    recency: float = 0.35
    importance: float = 0.5
    diversity: float = 0.4  # strength of the redundancy penalty during selection
    recency_half_life: float = 20.0  # in "memories newer than this one"
    floor: float = 0.15  # minimum base score to be eligible (relevance threshold)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _recency(record_index: int, now_index: int, half_life: float) -> float:
    """Exponential decay by how many memories have been stored since this one (newer ->
    closer to 1). Avoids parsing game-time while still honoring 'recent weighs more'."""
    age = max(0, now_index - record_index)
    return 0.5 ** (age / max(1e-6, half_life))


def realize_relevance(
    query_embedding: list[float],
    candidates: list[MemoryRecord],
    *,
    weights: RelevanceWeights | None = None,
    budget: int = 4,
    now_index: int | None = None,
) -> list[MemoryRecord]:
    """Select up to `budget` memories by balancing similarity, recency, importance and
    diversity (see module docstring). Returns the chosen records, most-relevant first."""
    if not candidates or budget <= 0:
        return []
    w = weights or RelevanceWeights()
    if now_index is None:
        now_index = max(c.index for c in candidates) + 1

    # Normalize similarity (cosine in [-1,1]) into [0,1] so it composes with the others.
    def base(c: MemoryRecord) -> float:
        sim = (cosine(query_embedding, c.embedding) + 1.0) / 2.0
        rec = _recency(c.index, now_index, w.recency_half_life)
        return w.similarity * sim + w.recency * rec + w.importance * c.importance

    scored = [(c, base(c)) for c in candidates]
    max_base = w.similarity + w.recency + w.importance  # for normalizing the floor
    eligible = [(c, b) for c, b in scored if b >= w.floor * max_base]
    if not eligible:
        # Nothing clears the floor — fall back to the single best so a turn is never
        # left with zero context when something *could* be relevant.
        eligible = [max(scored, key=lambda cb: cb[1])]

    selected: list[MemoryRecord] = []
    remaining = list(eligible)
    while remaining and len(selected) < budget:
        best, best_val = None, None
        for c, b in remaining:
            penalty = 0.0
            if selected:
                penalty = w.diversity * max(
                    (cosine(c.embedding, s.embedding) + 1.0) / 2.0 for s in selected
                )
            val = b - penalty
            if best_val is None or val > best_val:
                best, best_val = (c, b), val
        selected.append(best[0])
        remaining.remove(best)
    return selected
