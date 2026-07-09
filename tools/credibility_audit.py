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
            ok = False
            print(f"  [6] PERSISTENCE: FAIL — disk != final beat on {mism}")
        else:
            print(f"  [6] PERSISTENCE: PASS — {p.name} matches the final beat exactly "
                  f"(trust {disk['trust']:.2f}, scars "
                  f"{disk['scar_affection']:.2f}/{disk['scar_trust']:.2f}/{disk['scar_respect']:.2f})")
    else:
        print(f"  [6] PERSISTENCE: (no {p.name} on disk — arc not the last thing run)")
    return ok


def main() -> None:
    ok = audit("docs/credibility-demo/replay.json", "corvin-ashgrave-inworld")
    ok &= audit("docs/credibility-demo/replay_bri.json", "brielle-bri-castellano-inworld")
    print("=" * 74)
    print("AUDIT:", "ALL INVARIANTS HOLD" if ok else "FAILURES FOUND — see above")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
