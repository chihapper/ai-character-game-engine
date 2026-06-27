"""Demo + smoke test for temporal memory decay (issue #5).

Shows how a memory's STRENGTH (the temporal-salience pole of the RR scorer) fades over the
GAME's clock, with the half-life stretched by salience and reinforcement — so a trivial
one-off fades over in-game time while an important or repeated memory persists. Pure
computation; run with:  python -m tools.decay_demo
"""
from orchestrator.memory.relevance import (
    MemoryRecord, RelevanceWeights, realize_relevance, _strength,
)

W = RelevanceWeights()
EMB = [1.0, 0.0, 0.0]  # identical for every memory + the query, so similarity is neutral and
                       # we isolate the temporal-salience/importance behaviour.


def mem(text, importance, reinforcement, t, index):
    return MemoryRecord(text=text, embedding=EMB, index=index, importance=importance,
                        reinforcement=reinforcement, t=t, last_t=t)


def main():
    print("Memory STRENGTH as the game clock advances (all created at t=0):\n")
    print(f"  {'now_t':>6} | {'one-off (imp .3)':>16} | {'important (imp .9)':>18} | {'repeated x5':>12}")
    print("  " + "-" * 62)
    for now_t in (0, 10, 30, 100, 300, 1000):
        one = _strength(mem("x", 0.3, 0, 0, 0), now_t, 0, W)
        imp = _strength(mem("x", 0.9, 0, 0, 0), now_t, 0, W)
        rep = _strength(mem("x", 0.3, 5, 0, 0), now_t, 0, W)
        print(f"  {now_t:>6} | {one:>16.3f} | {imp:>18.3f} | {rep:>12.3f}")

    # Years later, which memories does the character still surface?
    mems = [
        mem("a trivial one-off from long ago", 0.3, 0, 0, 0),
        mem("you SAVED MY LIFE in the harbor fire", 0.9, 0, 0, 1),
        mem("our usual drink banter (shared many times)", 0.3, 5, 0, 2),
        mem("what you said just a moment ago", 0.3, 0, 900, 3),
    ]
    print("\nYears later (now_t = 1000) — top 2 recalled:")
    for m in realize_relevance(EMB, mems, weights=W, budget=2, now_index=4, now_t=1000):
        print("   -", m.text)

    # --- assertions ---
    s_oneoff = _strength(mem("x", 0.3, 0, 0, 0), 1000, 0, W)
    s_imp = _strength(mem("x", 0.9, 0, 0, 0), 1000, 0, W)
    s_rep = _strength(mem("x", 0.3, 5, 0, 0), 1000, 0, W)
    assert s_oneoff < s_imp, "important memory should outlast a one-off"
    assert s_oneoff < s_rep, "reinforced memory should outlast a one-off"
    assert s_oneoff < 0.01, "a trivial one-off should be all but forgotten years later"
    # No game clock -> falls back to index recency (back-compat), independent of now_t.
    no_clock = MemoryRecord("x", EMB, index=3, t=None)
    assert _strength(no_clock, None, 5, W) == _strength(no_clock, 999, 5, W)
    print("\nAll assertions passed.")


if __name__ == "__main__":
    main()
