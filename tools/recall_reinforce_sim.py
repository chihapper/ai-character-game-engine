"""Accelerated test of RECALL-AS-REINFORCEMENT (the open question on issue #5).

A live game would take in-game years to reveal whether "recalling a memory reinforces it"
helps or just inflates everything. So simulate it: compress a long game into a loop. A
player revisits some topics often and others never; each turn we retrieve (real RR scorer)
and — in the "ON" arm — reinforce whatever got recalled (bump count, refresh last-seen, so
its decay restarts). Then compare final memory STRENGTH with reinforcement-on-recall ON vs
OFF. Pure computation; run with:  python -m tools.recall_reinforce_sim

What we're looking for:
  * ON should keep FREQUENTLY-REVISITED memories vivid (rehearsal), even trivial ones.
  * ON should NOT keep NEVER-revisited memories alive (no blanket inflation).
  * A high-importance memory that's never revisited should still fade faster than one that is.
"""
from orchestrator.memory.relevance import (
    MemoryRecord, RelevanceWeights, realize_relevance, _strength,
)

W = RelevanceWeights()
TOPIC = {"A": [1.0, 0.0, 0.0], "B": [0.0, 1.0, 0.0], "C": [0.0, 0.0, 1.0]}
STEP, N_STEPS = 20, 100  # game-clock advances 20 per turn; 100 turns -> spans t=0..2000


def fresh_store():
    rows = [
        ("A_important  (revisited often)", 0.7, "A"),
        ("A_trivial    (revisited often)", 0.2, "A"),
        ("B_important  (mentioned once)",  0.7, "B"),
        ("C_trivial    (never revisited)", 0.2, "C"),
    ]
    return [MemoryRecord(text=t, embedding=TOPIC[top], index=i, importance=imp, t=0.0, last_t=0.0)
            for i, (t, imp, top) in enumerate(rows)]


def run(recall_reinforces: bool):
    mems = fresh_store()
    for step in range(N_STEPS):
        now_t = step * STEP
        # The player's pattern: topic A every turn; topic B only on turn 0; topic C never.
        topics = ["A"] + (["B"] if step == 0 else [])
        for topic in topics:
            recalled = realize_relevance(TOPIC[topic], mems, weights=W, budget=2,
                                         now_index=len(mems), now_t=now_t)
            if recall_reinforces:
                for m in recalled:
                    m.reinforcement += 1
                    m.last_t = now_t  # rehearsal: decay restarts from now
    end_t = N_STEPS * STEP
    return {m.text: _strength(m, end_t, len(mems), W) for m in mems}


def main():
    off = run(recall_reinforces=False)
    on = run(recall_reinforces=True)
    print(f"Final memory STRENGTH after a simulated game (t=0..{N_STEPS*STEP}):\n")
    print(f"  {'memory':34} | {'recall-reinf OFF':>16} | {'recall-reinf ON':>15}")
    print("  " + "-" * 72)
    for k in off:
        print(f"  {k:34} | {off[k]:>16.3f} | {on[k]:>15.3f}")
    print("\nReading:")
    print("  - revisited memories (A_*): ON keeps them vivid, OFF lets them fade.")
    print("  - never-revisited (C_trivial): ~0 under BOTH -> no blanket inflation.")
    print("  - B_important (one mention, high salience): fades without rehearsal even though")
    print("    it's 'important' -> rehearsal, not just salience, drives stickiness.")
    print("\n  Trade to judge: ON also keeps a TRIVIAL but oft-revisited memory alive")
    print("  (A_trivial) — realistic (you remember what you keep bringing up), but decide if")
    print("  that's wanted. Tune via how much a reinforcement extends the half-life.")


if __name__ == "__main__":
    main()
