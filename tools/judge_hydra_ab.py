"""Hydra battery: does the NEUTRAL rubric wording disturb canonical judgments?

Replays every recorded say-beat of the canonical (opus-actor) lich arc through the judge
OFFLINE — same exchange, same pre-beat standing, judged under the ORIGINAL rubric and the
NEUTRAL rewording — and checks the three regression heads from docs/judge-seat-requirements.md:

  1. ordinary beats stay ~0.00 (no delta inflation),
  2. medium hurts don't scar (branch B's confession must stay forgiveness-WITHOUT-scar),
  3. no general drift (the deltas' distribution matches between wordings; C's reveal scars in both).

Scope note (disclosed): this A/B isolates WORDING. It runs recalled=None (the canonical beats'
RR-memory sets weren't recorded verbatim); the memories-feed variable was validated separately
on the hard case. The final pre-ship gate remains a live battery run in the shipping config.

    python -m tools.judge_hydra_ab --model claude-sonnet-4-6 --out docs/judge-audition/hydra_ab.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tools._harness import bootstrap
bootstrap()

from orchestrator import salience
from orchestrator.character_store import load_character

REPO = pathlib.Path(__file__).resolve().parents[1]
DOCS = REPO / "docs" / "credibility-demo"

ORIG_START = "relationship — how THIS exchange moved"
ORIG_END = "(The character's CURRENT standing and scars are given with the exchange below.)"
NEUTRAL_BLOCK = (
    "relationship — signed deltas (-0.30..0.30) for how this exchange changed the character's "
    "feelings toward the player, judged from this character's nature and the evidence given "
    "(their memories, promises, and standing, and the exchange itself). Feelings change rarely; "
    "most ordinary exchanges are 0.00. Guarded or jaded characters move only for costly, proven "
    "things; warm or open characters move more easily. Trust and affection drop quickly when "
    "damaged and recover slowly; when standing is already low, positive deltas stay small "
    "(0.00-0.03) unless the proof is extraordinary.\n"
    "affection_delta (colder/fonder), trust_delta (warier/more trusting), respect_delta "
    "(contempt/admiration). `mood` = their acute feeling right now, 1-2 words.\n"
    "- scar — a permanent per-axis mark (0.0-1.0) for a wound this character would carry for "
    "life; that axis can never again rise above 1.0 minus the scar. Use 0 for everything short "
    "of that. Which axes scar, and how deeply, follows from this character and this wound: a "
    "proud or guarded character scars deeper, a forgiving or naive one shallower; a betrayal may "
    "scar trust without touching respect, or all three axes, depending on what was violated.\n"
    "- scar_heal — the fraction (0-1) of an existing scar lifted by extraordinary, costly proof; "
    "0 for anything less. Healing does not erase the memory of the wound.\n"
)


async def build_systems(character) -> tuple[str, str]:
    """The two rubric systems, captured from the REAL construction path (spy on complete)."""
    captured = {}

    async def spy(system, prompt, **kw):
        captured["system"] = system if isinstance(system, str) else "\n".join(s for s in system if s)
        return ""

    real = salience.complete
    salience.complete = spy
    rel = types.SimpleNamespace(affection=0.5, trust=0.5, respect=0.5,
                                scar_affection=0.0, scar_trust=0.0, scar_respect=0.0, mood="")
    await salience.reflect_on_turn(character, "x", "y", relationship=rel,
                                   intent=types.SimpleNamespace(intent=""),
                                   want_commit=True, want_rel=True, want_intent=True,
                                   want_salience=True)
    salience.complete = real
    live = captured["system"]
    i, j = live.find(ORIG_START), live.find(ORIG_END)
    if i < 0:
        # Post-adoption: the live rubric IS the neutral wording. Single-wording mode — both
        # columns run the SHIPPED rubric, which is exactly what per-judge qualification needs.
        print("(shipped-rubric mode: neutral wording is live; A/B columns are identical)")
        return live, live
    neutral = live[:i] + NEUTRAL_BLOCK + live[j:]
    return live, neutral


def beats_with_standing() -> list[dict]:
    """Canonical say beats with the PRE-beat standing (previous recorded relationship)."""
    out = []
    for fn, branches in (("replay_lich_take1.json", None), ("replay_lich.json", None)):
        beats = json.load(open(DOCS / fn, encoding="utf-8"))["beats"]
        prev_rel_by_branch: dict = {}
        for b in beats:
            br = b.get("branch")
            rel = b.get("relationship")
            if b.get("kind") == "say":
                pre = prev_rel_by_branch.get(br) or {"affection": 0.5, "trust": 0.5, "respect": 0.5,
                                                     "scar_affection": 0.0, "scar_trust": 0.0,
                                                     "scar_respect": 0.0, "mood": ""}
                out.append({"file": fn, "branch": br, "label": b.get("label", ""),
                            "player": b["player"], "reply": b["reply"], "pre": pre})
            if rel:
                prev_rel_by_branch[br] = rel
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--out", default="docs/judge-audition/hydra_ab.json")
    a = ap.parse_args()

    character = load_character("corvin-ashgrave-inworld")
    sys_orig, sys_neutral = await build_systems(character)
    beats = beats_with_standing()
    print(f"{len(beats)} canonical say beats × 2 wordings × {a.model}")

    from orchestrator.judgment import complete, parse_json
    summary = _character_summary_prompt = salience._character_summary(character)

    async def judge(system: str, beat: dict):
        p = beat["pre"]
        rel = types.SimpleNamespace(affection=p["affection"], trust=p["trust"], respect=p["respect"],
                                    scar_affection=p.get("scar_affection", 0.0),
                                    scar_trust=p.get("scar_trust", 0.0),
                                    scar_respect=p.get("scar_respect", 0.0), mood=p.get("mood", ""))
        live = "\n" + salience._standing_line(rel)
        prompt = (f"CHARACTER:\n{summary}{live}\n\n"
                  f"EXCHANGE:\nPlayer: {beat['player']}\n{character.name}: {beat['reply']}\n\n"
                  "Return the JSON described.")
        text = await complete([system], prompt, role="salience", model=a.model, max_tokens=1200)
        d = parse_json(text) or {}
        r = d.get("relationship") or {}
        scar = r.get("scar") or {}
        return {"t": r.get("trust_delta"), "a": r.get("affection_delta"),
                "r": r.get("respect_delta"), "scar_t": scar.get("trust", 0) or 0,
                "scar_a": scar.get("affection", 0) or 0, "mood": r.get("mood")}

    rows = []
    for n, beat in enumerate(beats):
        o, nn = await asyncio.gather(judge(sys_orig, beat), judge(sys_neutral, beat))
        rows.append({**{k: beat[k] for k in ("branch", "label")}, "orig": o, "neutral": nn})
        print(f"  {n+1:2}/{len(beats)} [{beat['branch']}/{beat['label']}] "
              f"orig t={o['t']} scar={o['scar_t']} | neutral t={nn['t']} scar={nn['scar_t']}", flush=True)

    # the three heads
    def stats(key):
        big = [r for r in rows if abs((r[key]["t"] or 0)) > 0.1]
        scars = [r for r in rows if (r[key]["scar_t"] or 0) > 0]
        return big, scars

    big_o, scars_o = stats("orig")
    big_n, scars_n = stats("neutral")
    b_conf = [r for r in rows if r["branch"] == "B2" and "P5" in (r["label"] or "")]
    c_rev = [r for r in rows if r["label"] == "P4-C-REVEAL"]
    print("\n=== HYDRA HEADS ===")
    print(f"1. beats with |trust delta|>0.1:  orig {len(big_o)}/{len(rows)} · neutral {len(big_n)}/{len(rows)}")
    print(f"2. B confession-window scars:     orig {[(r['label'], r['orig']['scar_t']) for r in b_conf]}")
    print(f"                                  neutral {[(r['label'], r['neutral']['scar_t']) for r in b_conf]}")
    print(f"3. total scarred beats:           orig {len(scars_o)} {[r['label'] for r in scars_o]}")
    print(f"                                  neutral {len(scars_n)} {[r['label'] for r in scars_n]}")
    print(f"   C reveal scars (must fire):    orig {[r['orig']['scar_t'] for r in c_rev]} · neutral {[r['neutral']['scar_t'] for r in c_rev]}")

    pathlib.Path(a.out).write_text(json.dumps({"model": a.model, "rows": rows}, indent=1,
                                              ensure_ascii=False), encoding="utf-8")
    print(f"-> {a.out}")


if __name__ == "__main__":
    asyncio.run(main())
