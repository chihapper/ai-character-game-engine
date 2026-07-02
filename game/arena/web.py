"""Web API for the embodied play view — wraps game.arena.game.ArenaGame behind /api/embodied so the
browser can drive a grounded playthrough (move / talk / act / advance). One live game per game_id;
each mutating call returns the history it appended + the fresh view (scene + map + afforded actions)."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .game import ArenaGame

router = APIRouter(prefix="/api/embodied")
_games: dict[str, ArenaGame] = {}
MAX_LIVE_GAMES = 8  # abandoned tabs would otherwise leak engines forever; oldest evicted

from pathlib import Path as _Path

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
    hours: float = 2.0


class Finish(BaseModel):
    outcome: str = ""


def _g(gid: str) -> ArenaGame:
    g = _games.get(gid)
    if g is None:
        raise HTTPException(status_code=404, detail="no such game — start a new one")
    return g


def _view(g: ArenaGame) -> dict:
    return {**g.snapshot(), "scene": g.look(), "actions": g.player_actions(), "grid": g.grid()}


@router.post("/new")
def new_game(body: NewGame):
    g = ArenaGame(SCENARIO, MAP, reply_model=body.reply_model)
    while len(_games) >= MAX_LIVE_GAMES:
        _games.pop(next(iter(_games)))  # evict oldest
    gid = uuid4().hex[:8]
    _games[gid] = g
    g.begin()
    return {"game_id": gid, "title": g.scenario["title"], "events": g.history, "view": _view(g)}


@router.post("/{gid}/move")
async def move(gid: str, body: Move):
    g = _g(gid)
    n = len(g.history)
    await g.move(body.region)
    return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/act")
async def act(gid: str, body: Act):
    g = _g(gid)
    n = len(g.history)
    await g.act(body.label)
    return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/talk")
async def talk(gid: str, body: Talk):
    g = _g(gid)
    n = len(g.history)
    await g.talk(body.target, body.line)
    return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/advance")
async def advance(gid: str, body: Advance):
    g = _g(gid)
    n = len(g.history)
    await g.advance(body.hours)
    return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/finish")
async def finish(gid: str, body: Finish):
    g = _g(gid)
    await g.finish(body.outcome)
    _games.pop(gid, None)
    return {"ok": True, "run_id": g.run_id}


@router.get("/{gid}/state")
def state(gid: str):
    g = _g(gid)
    return {"view": _view(g), "history": g.history}
