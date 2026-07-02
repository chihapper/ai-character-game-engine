"""Web API for the embodied play view — wraps game.arena.game.ArenaGame behind /api/embodied so the
browser can drive a grounded playthrough (move / talk / act / advance). ONE live world per process:
every game shares the per-character memory namespaces (and a new run RESETS them), so a second
"concurrent" game would play against wiped/cross-contaminated minds — /new finalizes whatever is
live and starts fresh. (True multi-world needs run-scoped namespaces — deferred, tracked.)

Each mutating call is serialized per game with an asyncio.Lock: handlers capture a history offset,
await multi-second LLM chains, then slice — interleaved requests on the same game would duplicate
events and mutate the world mid-recipe. A failure string from the game ("(no one here answers…)")
surfaces as HTTP 400, not a silent 200 with empty events."""
from __future__ import annotations

import asyncio
from pathlib import Path as _Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orchestrator.config import ALLOWED_MODEL_IDS

from .game import ArenaGame

router = APIRouter(prefix="/api/embodied")
_games: dict[str, ArenaGame] = {}
_locks: dict[str, asyncio.Lock] = {}

_GAME_DIR = _Path(__file__).resolve().parents[1]
SCENARIO = str(_GAME_DIR / "scenarios" / "ferry_crossing.yaml")   # repo-anchored, never cwd-relative
MAP = str(_GAME_DIR / "arena" / "maps" / "ferry_inn.yaml")


class NewGame(BaseModel):
    reply_model: str | None = None


class Move(BaseModel):
    region: str


class Talk(BaseModel):
    target: str
    line: str


class Act(BaseModel):
    label: str


class Advance(BaseModel):
    # gt/le also reject NaN (NaN compares false) and Infinity — clock += inf would
    # permanently zero every recency/decay computation for the rest of the run.
    hours: float = Field(default=2.0, gt=0, le=24)


class Finish(BaseModel):
    outcome: str = ""


def _g(gid: str) -> ArenaGame:
    g = _games.get(gid)
    if g is None:
        raise HTTPException(status_code=404, detail="no such game — start a new one")
    return g


def _lock(gid: str) -> asyncio.Lock:
    return _locks.setdefault(gid, asyncio.Lock())


def _view(g: ArenaGame) -> dict:
    return {**g.snapshot(), "scene": g.look(), "actions": g.player_actions(), "grid": g.grid()}


def _fail_if_refused(g: ArenaGame, n: int, out: str) -> None:
    """Game methods answer an impossible request with an explanation and log NOTHING — so
    "no new events" is the reliable failure signal (a legit NPC reply could itself start with a
    parenthesis). It must reach the client as an error, not a 200 with an empty events array."""
    if len(g.history) == n:
        raise HTTPException(status_code=400,
                            detail=(out or "").strip("()") or "the world refused that")


@router.post("/new")
async def new_game(body: NewGame):
    if body.reply_model and body.reply_model not in ALLOWED_MODEL_IDS:
        raise HTTPException(status_code=422,
                            detail=f"unknown reply_model {body.reply_model!r}; "
                                   f"allowed: {sorted(ALLOWED_MODEL_IDS)}")
    # One live world per process (shared minds): finalize the old run PROPERLY — flush its
    # background reflects + close its experiment-log row — before the new one wipes the namespaces.
    for gid, old in list(_games.items()):
        async with _lock(gid):
            try:
                await old.finish("(superseded by a new run)")
            except Exception:
                pass
            _games.pop(gid, None)
            _locks.pop(gid, None)
    g = ArenaGame(SCENARIO, MAP, reply_model=body.reply_model)
    gid = uuid4().hex[:8]
    _games[gid] = g
    g.begin()
    return {"game_id": gid, "title": g.scenario["title"], "events": g.history, "view": _view(g)}


@router.post("/{gid}/move")
async def move(gid: str, body: Move):
    g = _g(gid)
    async with _lock(gid):
        n = len(g.history)
        _fail_if_refused(g, n, await g.move(body.region))
        return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/act")
async def act(gid: str, body: Act):
    g = _g(gid)
    async with _lock(gid):
        n = len(g.history)
        _fail_if_refused(g, n, await g.act(body.label))
        return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/talk")
async def talk(gid: str, body: Talk):
    g = _g(gid)
    async with _lock(gid):
        n = len(g.history)
        _fail_if_refused(g, n, await g.talk(body.target, body.line))
        return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/advance")
async def advance(gid: str, body: Advance):
    g = _g(gid)
    async with _lock(gid):
        n = len(g.history)
        await g.advance(body.hours)
        return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/finish")
async def finish(gid: str, body: Finish):
    g = _g(gid)
    async with _lock(gid):
        await g.finish(body.outcome)
    _games.pop(gid, None)
    _locks.pop(gid, None)
    return {"ok": True, "run_id": g.run_id}


@router.get("/{gid}/state")
def state(gid: str):
    g = _g(gid)
    return {"view": _view(g), "history": g.history}
