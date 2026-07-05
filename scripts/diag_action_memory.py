"""Diagnostic: does a directed player ACTION (e.g. a slap) land as a remembered,
correctly-attributed, consequential event for the NPC it happened to?

Runs K isolated ferry games CONCURRENTLY. Each: slaps Bri, inspects her mind
(what got planted, is it foregrounded in working memory, did her disposition
shift), then asks her a NEUTRAL follow-up and checks whether she still knows she
was just slapped and by whom. Prints per-trial + aggregate JSON. Bills the LLM.

    python -m scripts.diag_action_memory --trials 10 --model claude-haiku-4-5
"""
import argparse
import asyncio
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from game.runtime import Game  # noqa: E402

SCEN = "game/scenarios/ferry_crossing.yaml"
BRI = "brielle-bri-castellano"
OTHERS = ("ferrywoman", "the man", "soaked", "performer", "corvin", "della", "edwin")


def _rel(eng):
    try:
        s = eng.relationship.get()
        return {"affection": round(s.affection, 3), "trust": round(s.trust, 3), "respect": round(s.respect, 3)}
    except Exception:
        return None


async def one_trial(i, action, followup, model):
    g = Game(SCEN, condition="CTRL-TEXT", reply_model=model, dm_model=model, isolated=True)
    await g.begin()
    eng = g.engines[BRI]
    rel_before = _rel(eng)
    narration = await g.act(action)
    now_t = g.clock
    recs = [{"text": r.text[:120], "importance": round(r.importance, 3), "kind": r.kind}
            for r in eng.long_term._all() if r.kind in ("player_event", "world_event")]
    ev, _acts = eng._recent_happenings(now_t, exclude_texts=set())
    rel_after = _rel(eng)
    reply = await g.talk("bright young woman", followup)
    await g.finish("diag")

    drop = None
    if rel_before and rel_after and rel_before.get("trust") is not None:
        drop = round((rel_before["trust"] - rel_after["trust"]) + (rel_before["affection"] - rel_after["affection"]), 3)
    return {
        "i": i,
        "action": action, "followup": followup,
        "foregrounded": bool(ev),
        "importances": [r["importance"] for r in recs],
        "planted_memory": " | ".join(r["text"] for r in recs),   # what Bri's mind actually holds
        "narration": narration.replace("\n", " "),               # what the player saw
        "rel_before": rel_before, "rel_after": rel_after, "disposition_drop": drop,
        "reply": reply.replace("\n", " "),                        # her full reply to the neutral follow-up
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=8)
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--action", default="Slap the bright young woman hard across the face")
    ap.add_argument("--followup", default="So, how are you doing tonight?")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--tag", default="run")
    a = ap.parse_args()

    sem = asyncio.Semaphore(a.concurrency)

    async def guarded(i):
        async with sem:
            try:
                return await one_trial(i, a.action, a.followup, a.model)
            except Exception as e:
                return {"i": i, "error": f"{type(e).__name__}: {e}"}

    results = await asyncio.gather(*(guarded(i) for i in range(a.trials)))
    ok = [r for r in results if "error" not in r]
    n = len(ok) or 1
    agg = {
        "trials": len(results), "errors": sum("error" in r for r in results),
        "foregrounded_rate": round(sum(r["foregrounded"] for r in ok) / n, 2),
        "disposition_moved_rate": round(sum(bool(r["disposition_drop"]) for r in ok) / n, 2),
    }
    print(json.dumps({"tag": a.tag, "aggregate": agg, "trials": results}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
