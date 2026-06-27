"""Scenario sweep for commitment tracking (issue #4) across different timetables.

Drives the real CommitmentStore lifecycle (add -> open/injected -> resolve or expire ->
convert to memory) and then shows how vivid the resulting memory is as the game clock
advances. Covers kept / broken / expired outcomes, high vs low significance, near vs far
deadlines, and a standing constraint with no deadline. Pure computation; run with:
    python -m tools.commitment_scenarios
"""
from pathlib import Path

from orchestrator.config import get_settings
from orchestrator.memory.commitments import CommitmentStore, BROKEN, FULFILLED
from orchestrator.memory.relevance import MemoryRecord, RelevanceWeights, _strength

W = RelevanceWeights()
NS = "scenario-tmp"
CLOCKS = [1, 3, 5, 8, 50, 500, 2000]


def _store():
    p = Path(get_settings().memory_dir) / f"{NS}.commitments.jsonl"
    if p.exists():
        p.unlink()
    return CommitmentStore(NS), p


def mem_strength(importance, made_t, now_t):
    rec = MemoryRecord("m", [1.0], index=0, importance=importance, t=made_t, last_t=made_t)
    return _strength(rec, now_t, 0, W)


def scenario(title, text, *, sig, due_t, resolve_at=None, resolve_status=None):
    store, path = _store()
    c = store.add(text, made_t=0, due_t=due_t, importance=sig)
    closed = None  # (memory_importance, made_t)
    print(f"\n■ {title}   (significance {sig:.2f}, due {due_t if due_t is not None else '—'})")
    print(f'    "{text}"')
    for t in CLOCKS:
        # game resolves it explicitly at its scheduled clock...
        if resolve_at is not None and t >= resolve_at and store.open_items():
            rc = store.resolve(c.id, resolve_status)
            if rc:
                closed = (rc.memory_importance(), t)
        # ...otherwise it expires once the clock passes its due
        for ec in store.sweep_expired(t):
            closed = (ec.memory_importance(), t)
        if store.open_items():
            print(f"    t={t:>4}  OPEN — injected into the prompt (she honors it)")
        else:
            imp, made = closed
            s = mem_strength(imp, made, t)
            note = "vivid" if s > 0.4 else ("faint" if s > 0.05 else "≈forgotten")
            print(f"    t={t:>4}  closed → memory imp {imp:.2f} · strength {s:.3f} ({note})")
    if path.exists():
        path.unlink()


def main():
    print("Commitment lifecycle across timetables (status per game clock; once closed, the")
    print("converted-memory strength shows how long the outcome is remembered):")
    scenario("High-stakes betrayal (let lapse)", "pay off his debts so he isn't sent to debtor's prison",
             sig=0.90, due_t=5)
    scenario("High-stakes promise, KEPT in time", "walk her home safely through the bad part of town",
             sig=0.90, due_t=5, resolve_at=3, resolve_status=FULFILLED)
    scenario("Trivial promise, let lapse", "grab some milk on the way back",
             sig=0.20, due_t=5)
    scenario("Mid promise, BROKEN early", "split the heist take fifty-fifty",
             sig=0.55, due_t=8, resolve_at=2, resolve_status=BROKEN)
    scenario("Standing constraint, NO deadline", "never tell anyone the player's real name",
             sig=0.70, due_t=None)
    print("\nTakeaways: open commitments stay injected (honored) until they close; a closed one")
    print("becomes a memory whose persistence tracks its significance — the betrayal is still")
    print("vivid at t=2000, the milk is forgotten by t=50, and a deadline-less constraint never")
    print("lapses on its own.")


if __name__ == "__main__":
    main()
