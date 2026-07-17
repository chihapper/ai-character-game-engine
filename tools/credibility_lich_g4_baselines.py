"""Baselines for the FULLY-LOCAL (Gemma) demo — replay the g4 engine's realized lines through
the RAG and tracker baselines, on the SAME local model, so the comparison stays same-model /
different-architecture.

The g4 rerun records every branch to ONE file (replay_lich_g4.json): shared, A, A6, B2, C,
C-felt, C-rescue. This tool replays those realized player-lines/events byte-identical through
RagBaselineCharacter + TrackerRagCharacter (model = CRED_MODEL, i.e. local/gemma4-12b) and
writes the three baseline artifacts the assembler consumes:

    replay_lich_g4_baselines.json   — main branches A / B / C  (shape: {"results": {...}})
    felt_test_g4_baselines.json     — the 5 felt probes on scarred C  ({"rag": [...], "tracker": [...]})
    rescue_test_g4_baselines.json   — the rescue event + 2 probes    (same shape)

The felt/rescue characters accumulate the FULL prior lineage first (shared + C for felt;
shared + C + felt for rescue) so the baseline mind is scarred exactly as the engine's was,
then only the probe beats are recorded. Beat labels are preserved verbatim (the assembler
matches felt/rescue by label, incl. "P5C-event").

    CRED_MODEL=local/gemma4-12b LOCAL_JUDGE_BASE_URL=http://127.0.0.1:11434/v1 \
        python -m tools.credibility_lich_g4_baselines --engine docs/credibility-demo/replay_lich_g4.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tools import credibility_demo as demo   # bootstrap + _baseline_persona + MODEL(=CRED_MODEL)
from tools.rag_baseline import RagBaselineCharacter, TrackerRagCharacter

DOCS = pathlib.Path(__file__).resolve().parents[1] / "docs" / "credibility-demo"


def log(m: str) -> None:
    print(m, flush=True)


def branch_feed(beats: list[dict], branch: str) -> list[dict]:
    """Ordered replayable items for a branch, preserving each beat's real label."""
    out = []
    for b in beats:
        if b.get("branch") != branch:
            continue
        if b.get("kind") == "say":
            out.append({"kind": "say", "label": b.get("label", ""), "text": b["player"]})
        elif b.get("kind") == "event":
            out.append({"kind": "event", "label": b.get("label") or b.get("phase", "event"),
                        "text": b["fact"]})
    return out


def _mk(tier: str, persona: str):
    cls = TrackerRagCharacter if tier == "tracker" else RagBaselineCharacter
    return cls(persona, model=demo.MODEL)


def _feed(ch, tier: str, item: dict):
    if item["kind"] == "say":
        return ch.respond(item["text"])
    (ch.note_event if tier == "tracker" else ch.remember)(item["text"])
    return None


def run_recorded(tier: str, persona: str, prefix: list[dict], record: list[dict],
                 tag: str) -> list[dict]:
    """Accumulate `prefix` silently, then replay+record `record`."""
    ch = _mk(tier, persona)
    for item in prefix:
        _feed(ch, tier, item)
    beats = []
    for i, item in enumerate(record, 1):
        if item["kind"] == "say":
            reply, top = ch.respond(item["text"])
            rec = {"kind": "say", "label": item["label"], "player": item["text"], "reply": reply,
                   "retrieval": top[:3]}
        else:
            _feed(ch, tier, item)
            rec = {"kind": "event", "label": item["label"], "fact": item["text"]}
        if tier == "tracker":
            rec["tracker"] = ch.state()
        beats.append(rec)
        log(f"   [{tag}/{tier}] {i}/{len(record)} {item['kind']}:{item['label']}"
            + (f"  aff={ch.state()['affinity']:+d} {ch.state()['tier']}" if tier == "tracker" else ""))
    return beats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="docs/credibility-demo/replay_lich_g4.json")
    ap.add_argument("--out", default="docs/credibility-demo/replay_lich_g4_baselines.json")
    ap.add_argument("--felt-out", default="docs/credibility-demo/felt_test_g4_baselines.json")
    ap.add_argument("--rescue-out", default="docs/credibility-demo/rescue_test_g4_baselines.json")
    a = ap.parse_args()

    beats = json.load(open(a.engine, encoding="utf-8"))["beats"]
    persona = demo._baseline_persona()
    shared = branch_feed(beats, "shared")
    A = branch_feed(beats, "A") + branch_feed(beats, "A6")
    B = branch_feed(beats, "B2")
    C = branch_feed(beats, "C")
    felt = branch_feed(beats, "C-felt")
    rescue = branch_feed(beats, "C-rescue")
    log(f"model={demo.MODEL} · shared={len(shared)} A={len(A)} B={len(B)} C={len(C)} "
        f"felt={len(felt)} rescue={len(rescue)}")

    # main branches: prefix=shared, record=branch
    results = {}
    for br, feed in (("A", A), ("B", B), ("C", C)):
        results[br] = {t: run_recorded(t, persona, shared, feed, br) for t in ("rag", "tracker")}
    json.dump({"meta": {"model": demo.MODEL, "tiers": ["rag", "tracker"],
                        "note": "g4 fully-local baselines; byte-identical feeds from replay_lich_g4"},
               "results": results},
              open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    log(f"✔ main baselines -> {a.out}")

    # felt: scar the mind through shared+C, then record the 5 felt probes
    felt_out = {t: run_recorded(t, persona, shared + C, felt, "felt") for t in ("rag", "tracker")}
    json.dump(felt_out, open(a.felt_out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    log(f"✔ felt baselines -> {a.felt_out}")

    # rescue: continue the lineage shared+C+felt, then record the rescue event + 2 probes
    rescue_out = {t: run_recorded(t, persona, shared + C + felt, rescue, "rescue")
                  for t in ("rag", "tracker")}
    json.dump(rescue_out, open(a.rescue_out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    log(f"✔ rescue baselines -> {a.rescue_out}")


if __name__ == "__main__":
    main()
