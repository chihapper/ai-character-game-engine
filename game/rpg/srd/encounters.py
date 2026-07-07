"""Encounter building + difficulty scaling — an ORIGINAL budget model over SRD-style CRs.

The published encounter-difficulty threshold tables are NOT part of the SRD, so this game's
budget curve uses its OWN constants — deliberately distinct from every published row (an
earlier draft accidentally landed on published level-1 thresholds and the published pack
multiplier ladder; both were re-tuned away). The model, in full:

- Every creature has a point cost by CR (`CR_COST`) — anchored to the SRD 5.1 XP-per-CR
  values (SRD material; attributed in LICENSE-SRD.md) so CR intuition carries over, continued
  as our own curve above the SRD anchor points. Unlisted CRs resolve to the nearest LOWER
  table key; CRs above the table clamp to its top entry.
- The party's budget is linear: ``base_points(difficulty) * party_level * party_size`` with
  base points easy 30 / medium 55 / hard 85 / deadly 115. Anchor: a lone even-CR-for-level foe
  (CR 1/4 at level 1, CR 1 at level 2, ...) prices out around a solo "medium"-to-"hard" fight.
  Linear-in-level is a deliberate simplification — character power really grows faster than
  linear, but our content lives at low levels where linear tracks well and stays legible.
- Action economy is priced by a pack-size pressure multiplier applied to the pack's SUMMED
  cost: 1 foe x1.0, 2 x1.4, 3-5 x1.9, 6+ x2.4 — many weak foes threaten more than their raw
  sum, because they get more turns and split less damage.

Pure + deterministic: all randomness comes from the injected ``rng`` (a `random.Random`) — no
module-level random, no I/O. Deliberately DECOUPLED from the bestiary: the caller passes a
``palette`` of ``(slug, cr)`` pairs (e.g. zipped from ``bestiary.slugs(...)`` and
``bestiary.cr(...)``), so this module imports nothing content-shaped.
"""
from __future__ import annotations

import random

# CR -> point cost. Monotone; the CR 0-5 anchor values ARE the SRD 5.1 XP-per-CR figures
# (SRD material — attributed in LICENSE-SRD.md) so CR intuition carries over; the entries above
# CR 5 continue as our own curve. Nearest-lower lookup handles unlisted fractional CRs
# (e.g. CR 0.75 prices as CR 0.5).
CR_COST: dict[float, int] = {
    0.0: 10,
    0.125: 25,
    0.25: 50,
    0.5: 100,
    1.0: 200,
    2.0: 450,
    3.0: 700,
    4.0: 1100,
    5.0: 1800,
    6.0: 2300,
    7.0: 2900,
    8.0: 3900,
    9.0: 5000,
    10.0: 5900,
}

_CR_KEYS: tuple[float, ...] = tuple(sorted(CR_COST))

# Per-character-per-level budget points — OUR constants, deliberately distinct from every
# published threshold row (see the module docstring).
BASE_POINTS: dict[str, int] = {"easy": 30, "medium": 55, "hard": 85, "deadly": 115}

# Rating ladder, weakest first — `rate_encounter` returns the highest rung reached ("trivial"
# = under the easy threshold).
_RATINGS: tuple[str, ...] = ("easy", "medium", "hard", "deadly")

# `build_encounter` aims the pack's effective cost into [floor * budget, budget].
_WINDOW_FLOOR = 0.70

# "Prefer 2-4 creatures over a single big one" applies at party levels up to this.
_LOW_LEVEL_MAX = 4


def _cr_cost(cr: float) -> int:
    """Point cost for a CR — nearest LOWER table key (below the table -> the bottom entry,
    above it -> the top entry)."""
    best = _CR_KEYS[0]
    for k in _CR_KEYS:
        if k <= cr:
            best = k
        else:
            break
    return CR_COST[best]


def _pack_multiplier(count: int) -> float:
    """Action-economy pressure by pack size: 1 foe x1.0, 2 x1.4, 3-5 x1.9, 6+ x2.4 — our own
    ladder (values AND breakpoints deliberately distinct from the published one)."""
    if count <= 1:
        return 1.0
    if count == 2:
        return 1.4
    if count <= 5:
        return 1.9
    return 2.4


def encounter_cost(crs: list[float]) -> int:
    """Effective cost of a pack: summed `CR_COST` x the pack-size multiplier (0 for no foes).

    Rounds half-up so the result is a stable int (the multiplier can land on exact halves).
    """
    if not crs:
        return 0
    base = sum(_cr_cost(cr) for cr in crs)
    return int(base * _pack_multiplier(len(crs)) + 0.5)


def party_budget(party_level: int, party_size: int, difficulty: str) -> int:
    """Point budget for a party: ``BASE_POINTS[difficulty] * party_level * party_size``.

    Raises ValueError on an unknown difficulty; level/size are clamped to at least 1.
    """
    base = BASE_POINTS.get(str(difficulty).strip().lower())
    if base is None:
        raise ValueError(f"unknown difficulty {difficulty!r}; known: {', '.join(BASE_POINTS)}")
    return base * max(1, int(party_level)) * max(1, int(party_size))


def _mixed_fill(pool: list[tuple[str, float]], n: int, budget: int) -> list[tuple[str, float]]:
    """Greedily assemble a MIXED pack of exactly `n` creatures within `budget`, cycling the
    (already shuffled) pool for variety. A creature is taken only if the remaining slots can
    still be filled by the pool's cheapest creature without busting the budget. Returns [] if
    `n` can't be reached."""
    cap = budget / _pack_multiplier(n)          # the summed BASE cost the pack may reach
    cheapest = min(_cr_cost(cr) for _, cr in pool)
    pack: list[tuple[str, float]] = []
    total = 0
    for step in range(n * len(pool)):           # bounded walk; deterministic in pool order
        slug, cr = pool[step % len(pool)]
        cost = _cr_cost(cr)
        reserve = (n - len(pack) - 1) * cheapest
        if total + cost + reserve <= cap:
            pack.append((slug, cr))
            total += cost
            if len(pack) == n:
                return pack
    return []


def build_encounter(*, party_level: int, party_size: int, difficulty: str,
                    palette: list[tuple[str, float]], rng: random.Random,
                    max_count: int = 6, min_count: int = 1) -> list[str]:
    """Pick creature slugs from `palette` whose pack cost lands in ~[70%, 100%] of the budget.

    Seeded + deterministic: the same `rng` state yields the same pack (the only randomness is
    one `rng.shuffle` of the candidate pool, which orders every tie-break downstream).

    Strategy — greedy with variety:
    - Enumerate homogeneous packs ("3 of slug X") for every palette creature at every count in
      [min_count, max_count], plus one greedy MIXED pack per count, all capped at the budget.
    - Score: in-window beats under-window; at party levels <= 4 a 2-4 creature pack beats a
      single big foe; then highest cost (closest to the budget) wins. Ties resolve in shuffle
      order.
    - The budget is NEVER exceeded. If no pack of >= min_count creatures fits, fall back to the
      single cheapest affordable creature (min_count is a preference, not a hard promise); only
      when even the cheapest creature alone busts the budget is [] returned.

    Raises ValueError on an unknown difficulty or an empty palette.
    """
    budget = party_budget(party_level, party_size, difficulty)   # validates difficulty
    if not palette:
        raise ValueError("empty palette: pass candidate (slug, cr) pairs")
    floor = budget * _WINDOW_FLOOR
    lo = max(1, int(min_count))
    hi = max(lo, int(max_count))

    pool = [(str(slug), float(cr)) for slug, cr in palette]
    rng.shuffle(pool)

    candidates: list[list[tuple[str, float]]] = []
    for slug, cr in pool:                        # homogeneous packs
        for n in range(lo, hi + 1):
            if encounter_cost([cr] * n) <= budget:
                candidates.append([(slug, cr)] * n)
            else:
                break                            # cost is monotone in n for a fixed CR
    for n in range(max(2, lo), hi + 1):          # one mixed pack per size, for variety
        pack = _mixed_fill(pool, n, budget)
        if pack:
            candidates.append(pack)

    if candidates:
        def score(pack: list[tuple[str, float]]) -> tuple[bool, bool, int]:
            cost = encounter_cost([cr for _, cr in pack])        # <= budget by construction
            in_window = cost >= floor
            small_pack = party_level <= _LOW_LEVEL_MAX and 2 <= len(pack) <= 4
            return (in_window, small_pack, cost)
        best = max(candidates, key=score)        # first max wins -> deterministic
        return [slug for slug, _ in best]

    # No pack of >= min_count creatures fits the budget: single cheapest affordable creature.
    slug, cr = min(pool, key=lambda t: _cr_cost(t[1]))
    if _cr_cost(cr) <= budget:
        return [slug]
    return []                                    # degenerate: nothing in the palette is affordable


def rate_encounter(crs: list[float], *, party_level: int, party_size: int) -> str:
    """Inverse of the budget: rate an EXISTING pack against this party.

    Returns 'trivial' | 'easy' | 'medium' | 'hard' | 'deadly' — the highest difficulty whose
    budget the pack's effective cost meets ('trivial' = under the easy threshold; an empty
    pack rates 'trivial')."""
    cost = encounter_cost(list(crs))
    rating = "trivial"
    for name in _RATINGS:
        if cost >= party_budget(party_level, party_size, name):
            rating = name
    return rating
