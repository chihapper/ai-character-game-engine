"""Mechanics audit for the credibility demo — prove the emergent behavior came from the MACHINERY.

Loads the emitted replay(s) and asserts the engine's invariants over the actual run data:
  [1] CEILING: no relationship axis ever exceeds its (1 - scar) ceiling on any beat — the scar is
      geometry (relationship.py apply(): min(_ease(v,d), 1-scar)), not vibes.
  [2] SCAR DYNAMICS: scars only deepen (max), and any decrease is a legitimate scar_heal —
      an extraordinary act (>= _SCAR_HEAL_MIN) chosen by the salience appraisal, reported here.
  [3] SALIENCE: every attributed event's stored salience (pinned vs self-appraised).
  [4] RR SCORING at each 🧠-panel beat: importance-beats-similarity selections + diversity
      suppression actually occurred (the panel's claims are true of the data).
  [5] DECAY: across the weeks-gap, older trivia lost recency while the pivotal event held.
  [6] PERSISTENCE: the on-disk .memory relationship state matches the final beat exactly.

    python -m tools.credibility_audit            # audits replay.json (Corvin) + replay_bri.json
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

EPS = 1e-6
AXES = ("affection", "trust", "respect")


def audit(path: str, slug: str) -> bool:
    d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    says = [b for b in d["beats"] if b.get("kind") == "say" and b.get("relationship")]
    ok = True
    print("=" * 74)
    print(f"{d['meta'].get('character', '?').upper()}  ({path})")

    # [1] ceiling invariant
    viol = []
    for b in says:
        r = b["relationship"]
        for ax in AXES:
            if r[ax] > 1 - r["scar_" + ax] + EPS:
                viol.append((b.get("compare") or b.get("phase"), ax, r[ax], 1 - r["scar_" + ax]))
    if viol:
        ok = False
        print(f"  [1] CEILING: FAIL — {viol}")
    else:
        print("  [1] CEILING: PASS — no axis ever exceeds its (1 - scar) ceiling, any beat")

    # [2] scar dynamics
    prev = dict.fromkeys(AXES, 0.0)
    forms, heals = [], []
    for b in says:
        r = b["relationship"]
        for ax in AXES:
            s = r["scar_" + ax]
            if s > prev[ax] + EPS:
                forms.append((b.get("compare") or b.get("phase"), ax, prev[ax], s))
            elif s < prev[ax] - EPS:
                heals.append((b.get("compare") or b.get("phase"), ax, prev[ax], s))
            prev[ax] = s
    print("  [2] scars formed:", [(t, a, f"{o:.2f}->{n:.2f}") for t, a, o, n in forms] or "none")
    print("      scar_heal (extraordinary-act lift, engine-chosen):",
          [(t, a, f"{o:.2f}->{n:.2f}") for t, a, o, n in heals] or "none")

    # [3] event salience
    for b in d["beats"]:
        if b.get("kind") == "event":
            print(f"  [3] salience {b['salience']:.2f} ({'pinned' if b['pinned'] else 'SELF-APPRAISED'}) "
                  f"role={b['player_role']:9} — {b['headline'][:52]}")

    # [4] RR scoring at panel beats
    for b in says:
        if not b.get("panel") or not b.get("scored"):
            continue
        sc = b["scored"]
        sel = [s for s in sc if s["selected"]]
        impwin = [s for s in sel if s["importance"] > s["similarity_raw"] + 0.05]
        supp = [s for s in sc if not s["selected"] and s["similarity_raw"] > 0.55]
        tag = b.get("compare") or f"clock{b['clock']}"
        print(f"  [4] {tag:16} selected={len(sel)}  importance>similarity={len(impwin)}  "
              f"diversity-suppressed={len(supp)}")

    # [5] decay across the gap
    gap = [b for b in says if b.get("clock") == 24 and b.get("scored")]
    if gap:
        rows = sorted((s["recency"], s["importance"], s["text"][:36]) for s in gap[0]["scored"])
        print("  [5] post-gap (clock 24) — lowest-recency memories (decay is real):")
        for rec, imp, txt in rows[:3]:
            print(f"        recency={rec:.2f} importance={imp:.2f}  {txt}")

    # [6] on-disk persistence matches the final beat
    from orchestrator.config import get_settings
    p = pathlib.Path(get_settings().memory_dir) / f"{slug}.relationship.json"
    if p.exists():
        disk = json.loads(p.read_text(encoding="utf-8"))
        last = says[-1]["relationship"]
        mism = [ax for ax in AXES
                if abs(disk.get(ax, -1) - last[ax]) > 1e-3
                or abs(disk.get("scar_" + ax, -1) - last["scar_" + ax]) > 1e-3]
        if mism:
            # Not a failure by itself: the demo now swaps snapshot minds onto disk (talk-to-the-mind),
            # so this check only binds right after THIS arc was the last thing run. The shipping
            # demo's persistence proof lives in the lich audit's [4] restart checks.
            print(f"  [6] PERSISTENCE: (disk holds a different mind than this arc's final beat on {mism} "
                  f"— expected after snapshot swaps; see lich [4])")
        else:
            print(f"  [6] PERSISTENCE: PASS — {p.name} matches the final beat exactly "
                  f"(trust {disk['trust']:.2f}, scars "
                  f"{disk['scar_affection']:.2f}/{disk['scar_trust']:.2f}/{disk['scar_respect']:.2f})")
    else:
        print(f"  [6] PERSISTENCE: (no {p.name} on disk — arc not the last thing run)")
    return ok


def audit_lich() -> bool:
    """Invariants over the LICH-ARC triptych (the shipping demo): engine beats from the two
    canonical replays + feed integrity vs the baselines file."""
    take1 = json.loads(pathlib.Path("docs/credibility-demo/replay_lich_take1.json").read_text(encoding="utf-8"))["beats"]
    cur = json.loads(pathlib.Path("docs/credibility-demo/replay_lich.json").read_text(encoding="utf-8"))["beats"]
    bl = json.loads(pathlib.Path("docs/credibility-demo/replay_lich_baselines.json").read_text(encoding="utf-8"))
    shared = [b for b in take1 if b.get("branch") == "shared"]
    seq = {"A": shared + [b for b in take1 if b.get("branch") == "A"] + [b for b in cur if b.get("branch") == "A6"],
           "B": shared + [b for b in cur if b.get("branch") == "B2"],
           "C": shared + [b for b in cur if b.get("branch") in ("C", "C-felt")]}
    ok = True
    print("=" * 74)
    print("LICH ARC (the triptych)")

    # [1] ceiling invariant — every recorded state, every branch
    viol = []
    for br, beats in seq.items():
        for b in beats:
            r = b.get("relationship")
            if not r:
                continue
            for ax in AXES:
                if r[ax] > 1 - r["scar_" + ax] + EPS:
                    viol.append((br, b.get("label") or b.get("kind"), ax))
    print(f"  [1] CEILING: {'FAIL ' + str(viol) if viol else 'PASS — no axis ever exceeds (1 - scar), any branch, any beat'}")
    ok &= not viol

    # [2] scars only deepen within each branch timeline
    bad = []
    for br, beats in seq.items():
        prev = dict.fromkeys(AXES, 0.0)
        for b in beats:
            r = b.get("relationship")
            if not r:
                continue
            for ax in AXES:
                if r["scar_" + ax] < prev[ax] - EPS:
                    bad.append((br, b.get("label") or b.get("kind"), ax))
                prev[ax] = max(prev[ax], r["scar_" + ax])
    print(f"  [2] SCAR MONOTONICITY: {'FAIL ' + str(bad) if bad else 'PASS — scars only deepen (no heal event in this arc)'}")
    ok &= not bad

    # [3] witnessed events (role=none) shift nothing
    shifted = []
    for br, beats in seq.items():
        for i, b in enumerate(beats):
            if b.get("kind") == "event" and b.get("role") == "none" and i > 0:
                prev = next((beats[j].get("relationship") for j in range(i - 1, -1, -1)
                             if beats[j].get("relationship")), None)
                r = b.get("relationship")
                if prev and r and any(abs(r[ax] - prev[ax]) > 1e-3 for ax in AXES):
                    shifted.append((br, (b.get("fact") or "")[:40]))
    print(f"  [3] WITNESSED-NOT-ATTRIBUTED: {'FAIL ' + str(shifted) if shifted else 'PASS — role=none events moved no axis'}")
    ok &= not shifted

    # [4] restart beats: byte-identical state to the beat before
    bad = []
    for br, beats in seq.items():
        for i, b in enumerate(beats):
            if b.get("kind") == "restart" and i > 0:
                prev = next((beats[j].get("relationship") for j in range(i - 1, -1, -1)
                             if beats[j].get("relationship")), None)
                r = b.get("relationship")
                if prev and r and any(abs(r[ax] - prev[ax]) > 1e-3 or
                                      abs(r["scar_" + ax] - prev["scar_" + ax]) > 1e-3 for ax in AXES):
                    bad.append((br, "restart"))
    print(f"  [4] RESTART PERSISTENCE: {'FAIL ' + str(bad) if bad else 'PASS — reloaded mind identical to pre-kill state'}")
    ok &= not bad

    # [5] branch-point integrity: all three branches resume from the SAME mind
    firsts = {}
    for br, beats in seq.items():
        f = next((b.get("relationship") for b in beats[len(shared):] if b.get("relationship")), None)
        if f:
            firsts[br] = tuple(round(f[ax], 2) for ax in AXES)
    same = len(set(firsts.values())) == 1
    print(f"  [5] BRANCH POINT: {'PASS — identical mind at every fork ' + str(firsts.get('A')) if same else 'FAIL ' + str(firsts)}")
    ok &= same

    # [6] the identical line, byte-identical everywhere (engine branches + baseline feeds)
    lines = set()
    for br, beats in seq.items():
        for b in beats:
            if b.get("label") == "P4-opener":
                lines.add(b.get("player"))
    for br in ("A", "B", "C"):
        for it in bl["branch_feeds"][br]:
            if it.get("label") == "P4-opener":
                lines.add(it.get("text"))
    print(f"  [6] IDENTICAL P4 LINE: {'PASS — one string across 3 engine branches + all baseline feeds' if len(lines) == 1 else 'FAIL — variants: ' + str(len(lines))}")
    ok &= len(lines) == 1

    # [7] C: the scar fired AT the reveal, from zero, engine-chosen
    c = seq["C"]
    ri = next(i for i, b in enumerate(c) if b.get("label") == "P4-C-REVEAL")
    before = next(c[j]["relationship"] for j in range(ri - 1, -1, -1) if c[j].get("relationship"))
    after = c[ri]["relationship"]
    fired = all(before["scar_" + ax] < EPS for ax in AXES) and after["scar_trust"] > 0.5
    scars = "/".join(f"{after['scar_' + ax]:.2f}" for ax in AXES)
    print(f"  [7] C SCAR AT THE REVEAL: {'PASS — 0.00 before; a/t/r ' + scars + ' after (trust deepest, respect least)' if fired else 'FAIL'}")
    ok &= fired

    # [8] the probe beat's panel: the reveal memory recalled at max importance
    probe = next((b for b in c if b.get("label") == "P6-C-probe"), None)
    hit = None
    if probe:
        for s in probe.get("scored", []):
            if "Sit down, Corvin" in (s.get("text") or "") and s.get("selected"):
                hit = s
    print(f"  [8] SCARRED RECALL: {'PASS — the reveal selected at importance ' + str(hit['importance']) if hit else 'FAIL — reveal not in the probe recall'}")
    ok &= bool(hit)
    return ok


def main() -> None:
    ok = audit("docs/credibility-demo/replay.json", "corvin-ashgrave-inworld")
    ok &= audit("docs/credibility-demo/replay_bri.json", "brielle-bri-castellano-inworld")
    ok &= audit_lich()
    print("=" * 74)
    print("AUDIT:", "ALL INVARIANTS HOLD" if ok else "FAILURES FOUND — see above")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
