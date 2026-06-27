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
    index: int  # monotonic insertion order — drives recency when there's no game clock
    importance: float = 0.5  # 0..1 salience captured at write time (goal/arena bearing)
    kind: str = "exchange"  # "exchange" | "world_event"
    when: str = ""  # game-supplied time tag; stored/displayed, never parsed by the engine
    # Temporal decay (issue #5). `t` is the GAME's clock value at creation — a single
    # monotonic number whose units the game owns (days/ticks/turns/seconds); the engine only
    # ever takes a difference. `last_t` is the clock at the most recent reinforcement (decay
    # is measured from there), and `reinforcement` counts how often the memory was re-met.
    t: float | None = None
    last_t: float | None = None
    reinforcement: int = 0


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
    spread: str = "zscore"  # similarity spreading across candidates: "zscore"|"minmax"|"none"
    spread_gain: float = 1.5  # zscore logistic steepness (higher = wider spread)
    # Temporal decay (issue #5). When a memory carries a game clock `t`, recency becomes a
    # STRENGTH that fades over game-time Δt with a half-life extended by salience and
    # reinforcement — so a one-off fades while an important/repeated memory persists. Units
    # are the GAME's; tune decay_half_life to the game's time scale (engine stays agnostic).
    decay_half_life: float = 30.0        # base half-life (importance 0) in the game's time units
    decay_importance_scale: float = 50.0  # half-life *= scale**importance — SUPER-linear, so a
                                          # truly significant memory (saving a life) becomes
                                          # near-permanent while a trivial one fades fast
    decay_reinforce_gain: float = 1.0     # n reinforcements multiply the half-life by (1+gain*n)


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


def _strength(record: "MemoryRecord", now_t: float | None, now_index: int,
              w: "RelevanceWeights") -> float:
    """Temporal salience as an opponent-processing pole. Over GAME-TIME when the memory and
    the query both carry a clock, else by insertion index (back-compat). The game-time
    half-life is stretched by importance and by reinforcement, so a trivial one-off fades
    over in-game time while an important or repeated memory survives (issue #5). `now_t` and
    `record.t` are in the GAME's own units — the engine only takes their difference."""
    if record.t is not None and now_t is not None:
        anchor = record.last_t if record.last_t is not None else record.t
        age = max(0.0, now_t - anchor)
        half_life = (
            w.decay_half_life
            * (w.decay_importance_scale ** record.importance)  # super-linear in significance
            * (1.0 + w.decay_reinforce_gain * record.reinforcement)
        )
        return 0.5 ** (age / max(1e-9, half_life))
    return _recency(record.index, now_index, w.recency_half_life)


def _spread_similarities(sims: list[float], method: str, gain: float) -> list[float]:
    """Re-spread per-candidate similarities to counter embedding *anisotropy* — real
    embedders bunch cosines into a narrow band, so a genuinely-relevant memory barely
    outscores noise and recency/importance drown it out (issue #3). This is monotonic
    (preserves ordering) but widens the dynamic range, computed *within the candidate set*.

    - "zscore" (default): standardize across the set, then a logistic squash — gentle,
      bounded, keeps relative magnitude. The set mean maps to 0.5.
    - "minmax": stretch to the full [0,1]. Aggressive — can crush low-similarity items
      (e.g. a high-importance off-topic world event), so prefer zscore unless you want a
      hard separation.
    - "none": passthrough (raw normalized cosine).

    Two heavier alternatives live at the EMBEDDER layer if spreading here isn't enough
    (see `memory/long_term.py`): whitening / mean-centering the stored embeddings (cancels
    the anisotropy cone at the source), or a less-anisotropic / larger model."""
    n = len(sims)
    if n <= 1 or method == "none":
        return list(sims)
    if method == "minmax":
        lo, hi = min(sims), max(sims)
        return [0.5] * n if hi - lo < 1e-9 else [(s - lo) / (hi - lo) for s in sims]
    mean = sum(sims) / n
    sd = (sum((s - mean) ** 2 for s in sims) / n) ** 0.5
    if sd < 1e-9:
        return [0.5] * n
    return [1.0 / (1.0 + math.exp(-gain * (s - mean) / sd)) for s in sims]


def realize_relevance(
    query_embedding: list[float],
    candidates: list[MemoryRecord],
    *,
    weights: RelevanceWeights | None = None,
    budget: int = 4,
    now_index: int | None = None,
    now_t: float | None = None,
    return_debug: bool = False,
):
    """Select up to `budget` memories by balancing similarity, recency, importance and
    diversity (see module docstring). Returns the chosen records, most-relevant first.

    With `return_debug=True`, returns `(selected, breakdown)` where breakdown is a list of
    per-candidate dicts (sim/recency/importance/base, selection order) — so the relevance
    realization is observable in a debug panel."""
    if not candidates or budget <= 0:
        return ([], []) if return_debug else []
    w = weights or RelevanceWeights()
    if now_index is None:
        now_index = max(c.index for c in candidates) + 1

    # Similarity: cosine (in [-1,1]) normalized to [0,1], then SPREAD across the candidate
    # set to counter embedding anisotropy (raw cosines bunch in a narrow band, so a
    # relevant memory barely outscores noise and recency wins — issue #3).
    raw_sims = [(cosine(query_embedding, c.embedding) + 1.0) / 2.0 for c in candidates]
    sims = _spread_similarities(raw_sims, w.spread, w.spread_gain)

    parts: dict[int, dict] = {}
    scored: list[tuple[MemoryRecord, float]] = []
    for c, sim_raw, sim in zip(candidates, raw_sims, sims):
        rec = _strength(c, now_t, now_index, w)  # game-time decay, or index recency
        base = w.similarity * sim + w.recency * rec + w.importance * c.importance
        # Cast to native floats so the debug breakdown is always JSON-serializable
        # (embeddings may be numpy float32). similarity = spread (drives base);
        # similarity_raw = the original cosine, so the anisotropy is visible.
        parts[id(c)] = {
            "similarity": float(sim), "similarity_raw": float(sim_raw),
            "recency": float(rec), "importance": float(c.importance), "base": float(base),
        }
        scored.append((c, base))

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

    if not return_debug:
        return selected
    order = {id(c): i for i, c in enumerate(selected)}
    breakdown = [
        {
            "text": c.text,
            "kind": c.kind,
            "when": c.when,
            **parts[id(c)],
            "selected": id(c) in order,
            "rank": order.get(id(c)),
        }
        for c, _ in sorted(scored, key=lambda cb: cb[1], reverse=True)
    ]
    return selected, breakdown
