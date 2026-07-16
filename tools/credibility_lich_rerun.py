"""Replay the recorded lich arc through a FRESH engine mind — the model-comparison rerun.

The canonical arc (replay_lich_take1.json shared+A, then replay_lich.json B2/A6/C/C-felt/
C-rescue) was played live on opus. This runner re-executes the SAME action feed — every
player line, world event, clock advance, taking-stock beat, commitment resolution, branch
and restart — beat for beat against a lich driver instance configured for another model
(fixed stimulus, same methodology as the baselines replay). Corvin's replies, appraisals,
and state are the run's OWN; only the inputs are pinned.

Isolation contract (so the canonical demo is never touched): point the driver at its own
slug + emit basename, and give this runner a --tag-prefix so its snapshots get their own
names. E.g. the sonnet-5 rerun:

    $env:CRED_MODEL="claude-sonnet-5"; $env:CRED_ENGINE_MODEL="claude-sonnet-5"
    $env:CRED_LICH_SLUG="corvin-ashgrave-s5"; $env:CRED_LICH_EMIT="replay_lich_s5"
    .venv/Scripts/python.exe -m tools.credibility_lich --port 8802         # the driver
    .venv/Scripts/python.exe -m tools.credibility_lich_rerun --port 8802 --tag-prefix s5-

Recorded `resolve` beats resolve "the first open commitment" — a different model may have
made a different number of promises, so a resolve against an empty ledger is logged and
skipped, never fatal (the divergence is data, not an error).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parents[1]
DEMO_DIR = REPO / "docs" / "credibility-demo"
FEEDS = ("replay_lich_take1.json", "replay_lich.json")


def load_feed() -> list[dict]:
    beats: list[dict] = []
    for fn in FEEDS:
        beats.extend(json.load(open(DEMO_DIR / fn, encoding="utf-8"))["beats"])
    return beats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8802)
    ap.add_argument("--tag-prefix", default="s5-", help="prefix for every snapshot/branch tag")
    ap.add_argument("--start-at", type=int, default=0, help="resume: skip beats before this index")
    ap.add_argument("--limit", type=int, default=0, help="smoke test: stop after N executed beats")
    args = ap.parse_args()

    base = f"http://127.0.0.1:{args.port}"
    pfx = args.tag_prefix
    tag = lambda t: (pfx + t) if t else ""
    beats = load_feed()
    print(f"feed: {len(beats)} beats from {' + '.join(FEEDS)}  ->  driver {base}  (tags '{pfx}*')")

    client = httpx.Client(timeout=600.0)
    done = 0
    for i, b in enumerate(beats):
        if i < args.start_at:
            continue
        if args.limit and done >= args.limit:
            print(f"-- limit {args.limit} reached at feed index {i}; resume with --start-at {i}")
            return
        k = b["kind"]
        if k == "start":
            ep, body = "/start", {}
        elif k == "say":
            ep, body = "/say", {"text": b["player"], "label": b.get("label", ""),
                                "note": b.get("note", ""), "location": b.get("location", ""),
                                "phase": b.get("phase", "")}
        elif k == "event":
            ep, body = "/event", {"fact": b["fact"], "role": b.get("role", "none"),
                                  "note": b.get("note", ""), "phase": b.get("phase", "")}
        elif k == "stock":
            ep, body = "/stock", {"note": b.get("note", ""), "phase": b.get("phase", "")}
        elif k == "advance":
            ep, body = "/advance", {"days": float(b["days"])}
        elif k == "snapshot":
            ep, body = "/snapshot", {"tag": tag(b["tag"])}
        elif k == "restore":
            ep, body = "/restore", {"tag": tag(b["tag"])}
        elif k == "branch":
            ep, body = "/branch", {"name": b.get("name", ""), "tag": tag(b.get("tag", ""))}
        elif k == "resolve":
            ep, body = "/resolve", {"status": b.get("status", "fulfilled"), "note": b.get("note", "")}
        elif k == "restart":
            ep, body = "/reload-proof", {"note": b.get("note", "")}
        else:
            print(f"  {i:3} ?? unknown kind {k!r} — skipped")
            continue

        t0 = time.perf_counter()
        r = client.post(base + ep, json=body)
        dt = time.perf_counter() - t0
        if r.status_code == 400 and k == "resolve":
            print(f"  {i:3} [{b.get('branch')}] resolve — no open commitment on this mind (divergence, ok)")
            done += 1
            continue
        r.raise_for_status()
        j = r.json()
        rel = j.get("relationship") or {}
        line = str(j.get("reply") or j.get("decision") or "")[:70].replace("\n", " ")
        print(f"  {i:3} [{b.get('branch')}] {k:9} {b.get('label') or b.get('tag') or b.get('name') or ''!s:14}"
              f" {dt:5.1f}s  t={rel.get('trust', 0):.2f} a={rel.get('affection', 0):.2f}"
              f" r={rel.get('respect', 0):.2f}  {line}", flush=True)
        done += 1

    print(f"DONE — {done} beats executed. Replay written by the driver (CRED_LICH_EMIT).")


if __name__ == "__main__":
    main()
