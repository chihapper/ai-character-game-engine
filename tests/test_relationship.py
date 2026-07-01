"""The affect curves (memory/relationship.py) — settled design principles (asymptotic ease, scars
deepen-to-worst, decisive-only healing, time-decay with bond resistance). A silent regression here
re-litigates decisions the project explicitly closed."""
from orchestrator.memory.relationship import _SCAR_HEAL_MIN, RelationshipState, _ease


def test_ease_is_asymptotic_with_diminishing_gains():
    # The design contract: extremes are HARD-WON — each step toward a rail buys less than the
    # last (geometric headroom), so a handful of big beats can't pin the score. (After dozens of
    # maximal deltas float precision may saturate; that's acceptable, "hard-won" is the property.)
    v, gains = 0.5, []
    for _ in range(10):
        nxt = _ease(v, 0.3)
        gains.append(nxt - v)
        v = nxt
    assert v < 1.0
    assert all(g2 < g1 for g1, g2 in zip(gains, gains[1:]))  # strictly diminishing
    v = 0.5
    for _ in range(10):
        v = _ease(v, -0.3)
    assert v > 0.0


def test_ease_leaving_an_extreme_is_a_big_move():
    # Severity is geometry: a betrayal from HIGH trust craters harder than from mid.
    assert (0.9 - _ease(0.9, -0.3)) > (0.2 - _ease(0.2, -0.3))


def test_scar_deepens_to_worst_never_shallows():
    s = RelationshipState()
    s.apply(scar={"trust": 0.6})
    s.apply(scar={"trust": 0.3})  # a later, lesser judgment must not shallow the wound
    assert s.scar_trust == 0.6
    s.apply(scar={"trust": 0.9})
    assert s.scar_trust == 0.9


def test_scar_heal_ignores_trivial_drips():
    s = RelationshipState()
    s.apply(scar={"trust": 0.5})
    s.apply(scar_heal={"trust": _SCAR_HEAL_MIN - 0.01})  # below the decisive floor: ignored
    assert s.scar_trust == 0.5
    s.apply(scar_heal={"trust": 0.5})  # decisive: asymptotic lift (scar *= 1 - heal)
    assert abs(s.scar_trust - 0.25) < 1e-9


def test_age_drifts_toward_baseline_and_updates_clock():
    s = RelationshipState()
    s.apply(d_trust=0.3)
    high = s.trust
    s.last_t = 0.0
    s.age(200.0, half_life=100.0)
    assert 0.5 < s.trust < high  # decayed toward the 0.5 baseline, not past it
    assert s.last_t == 200.0


def test_age_bond_resistance_slows_decay():
    a, b = RelationshipState(), RelationshipState()
    for s in (a, b):
        s.apply(d_trust=0.3)
        s.last_t = 0.0
    b.turns = 50  # a deep bond
    a.age(200.0, half_life=100.0, bond_resist=0.5)
    b.age(200.0, half_life=100.0, bond_resist=0.5)
    assert b.trust > a.trust  # the deep bond faded less


def test_age_noop_without_clock_or_elapsed():
    s = RelationshipState()
    s.apply(d_trust=0.3)
    v = s.trust
    s.age(None, half_life=100.0)
    assert s.trust == v
    s.last_t = 100.0
    s.age(100.0, half_life=100.0)  # zero elapsed
    assert s.trust == v
