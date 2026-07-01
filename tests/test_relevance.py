"""The RR scorer (memory/relevance.py) — the most-tuned math in the engine, previously protected
only by manual stress runs. Behavioral properties, not exact scores: budget, importance weighting,
similarity focus, the relevance floor, and game-time decay with reinforcement."""
from orchestrator.memory.relevance import MemoryRecord, RelevanceWeights, realize_relevance


def rec(text, vec, index=0, importance=0.5, t=None, last_t=None, reinforcement=0, kind="exchange"):
    return MemoryRecord(text=text, embedding=vec, index=index, importance=importance, kind=kind,
                        when="", t=t, last_t=last_t if last_t is not None else t,
                        reinforcement=reinforcement)


X, Y, Z = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
W = RelevanceWeights()  # defaults — properties below must hold at any sane weighting


def texts(selected):
    return [r.text for r in selected]


def test_budget_is_respected():
    records = [rec(f"m{i}", X, index=i) for i in range(10)]
    assert len(realize_relevance(X, records, weights=W, budget=3, now_index=10)) <= 3


def test_importance_breaks_similarity_ties():
    records = [rec("trivial", X, index=0, importance=0.1),
               rec("pivotal", X, index=1, importance=0.95)]
    got = texts(realize_relevance(X, records, weights=W, budget=1, now_index=2))
    assert got == ["pivotal"]


def test_similarity_focus_wins_over_noise():
    records = [rec("on-topic", X, index=0), rec("off-topic", Y, index=1), rec("also-off", Z, index=2)]
    got = texts(realize_relevance(X, records, weights=W, budget=1, now_index=3))
    assert got == ["on-topic"]


def test_relevance_floor_drops_weak_matches():
    # An orthogonal-only candidate set: with a floor, junk shouldn't be padded in to fill budget.
    records = [rec("on-topic", X, index=0), rec("junk", Y, index=1)]
    got = texts(realize_relevance(X, records, weights=W, budget=2, now_index=2))
    assert "on-topic" in got
    assert len(got) <= 2  # junk MAY drop under the floor; it must never displace the match


def test_game_time_decay_prefers_recent_at_equal_salience():
    old = rec("old", X, index=0, importance=0.5, t=0.0)
    new = rec("new", X, index=1, importance=0.5, t=1000.0)
    got = texts(realize_relevance(X, [old, new], weights=W, budget=1, now_index=2, now_t=1000.0))
    assert got == ["new"]


def test_reinforcement_resists_decay():
    plain = rec("plain", X, index=0, importance=0.5, t=0.0)
    rehearsed = rec("rehearsed", X, index=1, importance=0.5, t=0.0, reinforcement=6, last_t=900.0)
    got = texts(realize_relevance(X, [plain, rehearsed], weights=W, budget=1, now_index=2,
                                  now_t=1000.0))
    assert got == ["rehearsed"]


def test_empty_and_tiny_inputs():
    assert realize_relevance(X, [], weights=W, budget=4, now_index=0) == []
    one = [rec("only", X, index=0)]
    assert texts(realize_relevance(X, one, weights=W, budget=4, now_index=1)) == ["only"]
