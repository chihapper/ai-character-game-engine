"""Web API for the play view — wraps game.runtime.Game behind /api/game so web/play.js can drive a
playthrough (talk / say / act / advance / finish). One live Game per game_id. The play view is the
PLAYER surface (no stats panel, per the thesis); the director sandbox is the dev tool. Each mutating
call returns the history records it appended, so the client renders the story incrementally."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .runtime import Game

router = APIRouter(prefix="/api/game")
_games: dict[str, Game] = {}

DEFAULT_SCENARIO = "game/scenarios/ferry_crossing.yaml"


class NewGame(BaseModel):
    scenario: str = DEFAULT_SCENARIO
    condition: str = "CTRL-TEXT"
    reply_model: str | None = None
    dm_model: str | None = None


class Talk(BaseModel):
    target: str
    line: str


class Say(BaseModel):
    line: str


class Act(BaseModel):
    action: str


class Finish(BaseModel):
    outcome: str = ""


def _game(gid: str) -> Game:
    g = _games.get(gid)
    if g is None:
        raise HTTPException(status_code=404, detail="no such game — start a new one")
    return g


def _view(g: Game) -> dict:
    snap = g.snapshot()  # scenario, beat, beat_title, clock, present (names), run_id
    snap["roster"] = [{"slug": s, "name": g._name(s)} for s in g.present]
    return snap


@router.post("/new")
async def new_game(body: NewGame):
    g = Game(body.scenario, condition=body.condition,
             reply_model=body.reply_model, dm_model=body.dm_model)
    gid = uuid4().hex[:8]
    _games[gid] = g
    await g.begin()
    return {"game_id": gid, "title": g.scenario["title"], "events": g.history, "view": _view(g)}


@router.post("/{gid}/talk")
async def talk(gid: str, body: Talk):
    g = _game(gid)
    n = len(g.history)
    await g.talk(body.target, body.line)
    return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/say")
async def say(gid: str, body: Say):
    g = _game(gid)
    n = len(g.history)
    await g.say_to_room(body.line)
    return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/act")
async def act(gid: str, body: Act):
    g = _game(gid)
    n = len(g.history)
    await g.act(body.action)
    return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/advance")
async def advance(gid: str):
    g = _game(gid)
    n = len(g.history)
    more = await g.advance()
    return {"events": g.history[n:], "view": _view(g), "ended": not more}


@router.post("/{gid}/finish")
async def finish(gid: str, body: Finish):
    g = _game(gid)
    await g.finish(body.outcome)
    _games.pop(gid, None)
    return {"ok": True, "run_id": g.run_id}


@router.get("/{gid}/state")
async def state(gid: str):
    g = _game(gid)
    return {"view": _view(g), "history": g.history}
