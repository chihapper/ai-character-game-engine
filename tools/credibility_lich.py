"""Lich-arc driver — a persistent control server for the 5-part demo arc (task #37).

See docs/credibility-demo/lich-arc-spec.md + lich-arc-beats.md (APPROVED). The arc is driven
ADAPTIVELY, beat by beat, per the emergence rule: the operator (Claude) reads Corvin's actual
replies and chooses the next player line by the beat gates — nothing is force-fed. This server
just holds the engine hot (one embedder warmup for the whole arc) and exposes the seams:

    POST /start            wipe -> fresh Corvin, arc caps (demo six + commitment_detection), clock 41
    POST /say              {text, label?, note?, location?, phase?} -> reply + full panel (recorded)
    POST /event            {fact, role: none|benefited|caused|self, note?, phase?} (recorded)
    POST /stock            {note?, phase?} -> deliberate(mode="free")  — the TAKING STOCK beat
    POST /advance          {days} -> clock bump + relationship drift
    POST /snapshot {tag} · /restore {tag} · /branch {name}   (branch = restore branch-point + relabel)
    POST /resolve          {status: fulfilled|broken} -> close the first open commitment
    POST /reload-proof     drop caches, rebuild engine from DISK, return state (the restart beat)
    GET  /state            current relationship/beliefs/commitments/clock

Every action appends to docs/credibility-demo/replay_lich.json (+ .js) immediately — crash-safe,
and the future overlay reads it. Engine talk model = opus; engine-process = default sonnet.

    python -m tools.credibility_lich            # port 8801
"""
# NB: no `from __future__ import annotations` — FastAPI body-model resolution (see live server).

import argparse
import asyncio
import json
import os
import pathlib

from tools import credibility_demo as demo   # bootstrap() + the demo-six set_flags at import
from tools._harness import make_engine, set_flags, wipe

set_flags(commitment_detection=True)          # the package promise must become a tracked obligation

# Rerun isolation (model-comparison runs): a different slug keeps the canonical Corvin mind and
# its snapshots untouched; a different emit basename keeps the canonical replay files untouched.
demo.SLUG = os.environ.get("CRED_LICH_SLUG", demo.SLUG)
demo.apply_engine_model(demo.ENGINE_MODEL)    # CRED_ENGINE_MODEL — demo.main() applies it, we must too

from orchestrator.config import get_settings

# THIS demo's clock unit is DAYS with weeks-scale scene gaps -> widen working-memory foregrounding
# to the demo's cadence. Per-game obligation (engine-game contract §4 + config.py note): the window
# is in the game's clock unit and must cover a typical between-scene time-skip.
get_settings().recent_happenings_window = 10.0

from orchestrator.character_store import load_character
from orchestrator.context import RespondRequest, Situation

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "credibility-demo" / os.environ.get("CRED_LICH_EMIT", "replay_lich")
DOCK = demo.DOCK
SHED = "back of the tackle-shed, after dark"

STATE: dict = {"eng": None, "clock": 41.0, "branch": "shared", "turns": 0}
_LOCK = asyncio.Lock()
REPLAY: dict = {"meta": {"character": "Corvin", "slug": demo.SLUG, "arc": "lich",
                         "model": demo.MODEL,
                         "engine_model": demo.ENGINE_MODEL or "default (claude-sonnet-4-6)"},
                "beats": []}


def _name() -> str:
    return load_character(demo.SLUG).name.split(" (")[0].split()[0]


def _seed_clock() -> None:
    eng = STATE["eng"]
    ts = [v for r in eng.long_term._all() for v in (r.t, r.last_t) if v is not None]
    lt = eng.relationship.get().last_t
    if lt is not None:
        ts.append(lt)
    STATE["clock"] = round(max(ts) + 0.02, 3) if ts else 41.0


def _rebuild() -> None:
    STATE["eng"] = make_engine(demo.SLUG, model=demo.MODEL, max_tokens=1024)
    _seed_clock()


def _commits(eng) -> list:
    return [{"text": c.text, "due": c.due} for c in eng.commitments.open_items()]


def _snap(extra: dict | None = None) -> dict:
    eng = STATE["eng"]
    d = {"relationship": demo.rel_snap(eng), "beliefs": list(eng.long_term.beliefs()),
         "intent": eng.intent.get().intent or "", "commitments": _commits(eng),
         "clock": STATE["clock"], "branch": STATE["branch"], "turns": STATE["turns"]}
    if extra:
        d.update(extra)
    return d


def _record(kind: str, **rec) -> None:
    REPLAY["beats"].append({"kind": kind, "branch": STATE["branch"], "clock": STATE["clock"], **rec})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.with_suffix(".json").write_text(json.dumps(REPLAY, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    OUT.with_suffix(".js").write_text("window.CRED_REPLAY_LICH = " +
                                      json.dumps(REPLAY, ensure_ascii=False) + ";", encoding="utf-8")


def build_app():
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel

    class SayIn(BaseModel):
        text: str
        label: str = ""
        note: str = ""
        location: str = ""
        phase: str = ""

    class EventIn(BaseModel):
        fact: str
        role: str = "none"           # none | benefited | caused | self
        note: str = ""
        phase: str = ""

    class TagIn(BaseModel):
        tag: str = ""
        name: str = ""
        days: float = 0.0
        status: str = ""
        note: str = ""
        phase: str = ""

    app = FastAPI(title="Lich arc driver")

    @app.get("/state")
    async def state() -> JSONResponse:
        return JSONResponse(_snap())

    @app.post("/start")
    async def start() -> JSONResponse:
        async with _LOCK:
            wipe(demo.SLUG)
            STATE["clock"] = 41.0
            STATE["branch"] = "shared"
            STATE["turns"] = 0
            REPLAY["beats"].clear()
            _rebuild()
            STATE["clock"] = 41.0
            _record("start", note="fresh Corvin from Wipe; arc caps = demo six + commitment_detection")
            return JSONResponse(_snap())

    @app.post("/say")
    async def say(b: SayIn) -> JSONResponse:
        async with _LOCK:
            eng = STATE["eng"]
            sit = Situation(location=b.location or DOCK, clock=STATE["clock"], present=[_name()])
            reply, dbg = await eng.respond(RespondRequest(player_input=b.text, situation=sit),
                                           debug=True)
            STATE["clock"] = round(STATE["clock"] + 0.02, 3)
            STATE["turns"] += 1
            _record("say", label=b.label, phase=b.phase, note=b.note,
                    location=b.location or DOCK, player=b.text, reply=reply,
                    query=(dbg.get("query") or "")[:400], scored=demo.scored_rows(dbg),
                    relationship=demo.rel_snap(eng), beliefs=list(eng.long_term.beliefs()),
                    commitments=_commits(eng))
            return JSONResponse(_snap({"reply": reply,
                                       "recalled": [s["text"] for s in (dbg.get("scored") or [])
                                                    if s.get("selected")]}))

    @app.post("/event")
    async def event(b: EventIn) -> JSONResponse:
        async with _LOCK:
            eng = STATE["eng"]
            role = b.role.lower()
            sal = await eng.remember(
                b.fact,
                player_role=(role if role in ("benefited", "caused") else None),
                actor=("self" if role == "self" else "player"),
                t=STATE["clock"])
            _record("event", phase=b.phase, note=b.note, fact=b.fact, role=role,
                    salience=round(sal or 0.0, 3), relationship=demo.rel_snap(eng))
            return JSONResponse(_snap({"salience": round(sal or 0.0, 3)}))

    @app.post("/stock")
    async def stock(b: TagIn) -> JSONResponse:
        async with _LOCK:
            eng = STATE["eng"]
            sit = Situation(location=DOCK, clock=STATE["clock"], present=[_name()])
            decision = await eng.deliberate(situation=sit, mode="free")
            _record("stock", phase=b.phase, note=b.note, decision=decision,
                    relationship=demo.rel_snap(eng), beliefs=list(eng.long_term.beliefs()),
                    intent=eng.intent.get().intent or "")
            return JSONResponse(_snap({"decision": decision}))

    @app.post("/advance")
    async def advance(b: TagIn) -> JSONResponse:
        async with _LOCK:
            eng = STATE["eng"]
            STATE["clock"] = round(STATE["clock"] + float(b.days), 3)
            eng._age_relationship(STATE["clock"])
            _record("advance", days=b.days, note=b.note, relationship=demo.rel_snap(eng))
            return JSONResponse(_snap())

    @app.post("/snapshot")
    async def snapshot(b: TagIn) -> JSONResponse:
        async with _LOCK:
            demo.snapshot(b.tag)
            _record("snapshot", tag=b.tag, note=b.note)
            return JSONResponse(_snap())

    @app.post("/restore")
    async def restore(b: TagIn) -> JSONResponse:
        async with _LOCK:
            demo.restore(b.tag)
            _rebuild()
            _record("restore", tag=b.tag, note=b.note)
            return JSONResponse(_snap())

    @app.post("/branch")
    async def branch(b: TagIn) -> JSONResponse:
        """Restore the branch-point snapshot and relabel the stream (A already ran from it live)."""
        async with _LOCK:
            if b.tag:
                demo.restore(b.tag)
                _rebuild()
            STATE["branch"] = b.name or "A"
            _record("branch", name=STATE["branch"], tag=b.tag, note=b.note)
            return JSONResponse(_snap())

    @app.post("/resolve")
    async def resolve(b: TagIn) -> JSONResponse:
        async with _LOCK:
            eng = STATE["eng"]
            items = eng.commitments.open_items()
            if not items:
                return JSONResponse({"error": "no open commitments"}, status_code=400)
            c = await eng.resolve_commitment(items[0].id, b.status or "fulfilled", t=STATE["clock"])
            _record("resolve", status=b.status, note=b.note,
                    commitment=(c.text if c else items[0].text))
            return JSONResponse(_snap({"resolved": c.text if c else ""}))

    @app.post("/reload-proof")
    async def reload_proof(b: TagIn) -> JSONResponse:
        """The RESTART beat: drop in-process caches, rebuild from disk, return the loaded mind."""
        async with _LOCK:
            from orchestrator.memory.long_term import LongTermMemory
            ns = load_character(demo.SLUG).memory_namespace
            STATE["eng"] = None
            LongTermMemory.invalidate(ns)
            _rebuild()
            _record("restart", note=b.note or "cold reload from .memory/ — nothing carried in RAM",
                    relationship=demo.rel_snap(STATE["eng"]),
                    beliefs=list(STATE["eng"].long_term.beliefs()),
                    commitments=_commits(STATE["eng"]))
            return JSONResponse(_snap())

    return app


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8801)
    args = ap.parse_args()
    _rebuild()
    print(f"   ⚙ lich-arc driver · {_name()} · talk={demo.MODEL} · clock={STATE['clock']}")
    print(f"   ▶ control surface: http://127.0.0.1:{args.port}/  (POST /start begins a fresh arc)")
    import uvicorn
    uvicorn.run(build_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
