"""Baselines over the lich arc — plain RAG + affinity-tracker replay the ENGINE's realized runs.

Feeds are byte-identical to what the engine lived: the shared P1-2 player lines, then each
branch's realized lines + witnessed-event texts, in order (docs/credibility-demo/lich-arc-spec.md).
Baselines have no clock/deliberation/commitments — that's the point — so advance/stock/restart
beats simply don't exist for them; events go in as memory text (and to the tracker's judge).

    python -m tools.credibility_lich_baselines            # writes replay_lich_baselines.json

Sources: shared+A from git 2c85f37 (pass --take1 path), A6/B2/C from the current replay.
Bills the LLM heavily (~370 calls): reply + rolling summary per line per tier, + tracker judge.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

from tools import credibility_demo as demo          # bootstrap + _baseline_persona + MODEL
from tools.rag_baseline import RagBaselineCharacter, TrackerRagCharacter

_PRINT = threading.Lock()


def log(msg: str) -> None:
    with _PRINT:
        print(msg, flush=True)


def feed_items(beats: list[dict], branch: str) -> list[dict]:
    """The replayable items for one branch label, in recorded order."""
    out = []
    for b in beats:
        if b.get("branch") != branch:
            continue
        if b.get("kind") == "say":
            out.append({"kind": "say", "label": b.get("label", ""), "text": b["player"]})
        elif b.get("kind") == "event":
            out.append({"kind": "event", "label": b.get("phase", "event"), "text": b["fact"]})
    return out


def run_tier(tier: str, persona: str, shared: list[dict], branch_feed: list[dict],
             branch: str) -> list[dict]:
    cls = TrackerRagCharacter if tier == "tracker" else RagBaselineCharacter
    ch = cls(persona, model=demo.MODEL)
    beats = []
    for i, item in enumerate(shared + branch_feed, 1):
        if item["kind"] == "say":
            reply, top = ch.respond(item["text"])
            rec = {"kind": "say", "label": item["label"], "player": item["text"], "reply": reply,
                   "retrieval": top[:3]}
        else:
            if tier == "tracker":
                ch.note_event(item["text"])
            else:
                ch.remember(item["text"])
            rec = {"kind": "event", "label": item["label"], "fact": item["text"]}
        if tier == "tracker":
            rec["tracker"] = ch.state()
        beats.append(rec)
        log(f"   [{branch}/{tier}] {i}/{len(shared) + len(branch_feed)} {item['kind']}:{item['label']}"
            + (f"  aff={ch.state()['affinity']:+d} {ch.state()['tier']}" if tier == "tracker" else ""))
    return beats


def run_branch(branch: str, persona: str, shared: list[dict], branch_feed: list[dict]) -> dict:
    log(f"▶ branch {branch}: {len(shared)} shared + {len(branch_feed)} branch items, two tiers")
    return {
        "rag": run_tier("rag", persona, shared, branch_feed, branch),
        "tracker": run_tier("tracker", persona, shared, branch_feed, branch),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--take1", required=True, help="path to the 2c85f37 replay (shared + branch A)")
    ap.add_argument("--current", default="docs/credibility-demo/replay_lich.json")
    ap.add_argument("--out", default="docs/credibility-demo/replay_lich_baselines.json")
    args = ap.parse_args()

    take1 = json.load(open(args.take1, encoding="utf-8"))["beats"]
    cur = json.load(open(args.current, encoding="utf-8"))["beats"]

    shared = feed_items(take1, "shared")
    feeds = {
        "A": feed_items(take1, "A") + feed_items(cur, "A6"),
        "B": feed_items(cur, "B2"),
        "C": feed_items(cur, "C"),
    }
    persona = demo._baseline_persona()
    log(f"model={demo.MODEL} · shared={len(shared)} · " +
        " · ".join(f"{k}={len(v)}" for k, v in feeds.items()))

    results: dict = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {k: ex.submit(run_branch, k, persona, shared, v) for k, v in feeds.items()}
        for k, f in futs.items():
            results[k] = f.result()

    out = {"meta": {"model": demo.MODEL, "tiers": ["rag", "tracker"],
                    "note": "byte-identical feeds from the engine's realized runs"},
           "shared_feed": shared, "branch_feeds": feeds, "results": results}
    pathlib.Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False),
                                      encoding="utf-8")
    log(f"✔ saved -> {args.out}")
    for br in ("A", "B", "C"):
        st = [b.get("tracker") for b in results[br]["tracker"] if b.get("tracker")]
        if st:
            log(f"   {br}: tracker end affinity {st[-1]['affinity']:+d} ({st[-1]['tier']}) "
                f"worst={st[-1]['worst']!r}")


if __name__ == "__main__":
    main()
