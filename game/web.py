"""Web API for the play view — wraps game.runtime.Game behind /api/game so web/play.js can drive a
playthrough (talk / say / act / advance / finish). One live Game per game_id. The play view is the
PLAYER surface (no stats panel, per the thesis); the director sandbox is the dev tool. Each mutating
call returns the history records it appended, so the client renders the story incrementally."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from orchestrator.config import ALLOWED_MODEL_IDS

from .runtime import Game

router = APIRouter(prefix="/api/game")
_games: dict[str, Game] = {}
_locks: dict[str, "asyncio.Lock"] = {}


def _lock(gid: str):
    import asyncio
    return _locks.setdefault(gid, asyncio.Lock())

SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"
DEFAULT_SCENARIO = "ferry_crossing.yaml"


def _scenario_path(name: str) -> Path:
    """Allow-list scenarios to game/scenarios/ — the API must never accept an arbitrary filesystem
    path (it would be an arbitrary-file-read that also wipes cast memory as a side effect)."""
    p = SCENARIOS_DIR / Path(name or DEFAULT_SCENARIO).name
    if p.suffix != ".yaml" or not p.is_file():
        raise HTTPException(status_code=400, detail=f"unknown scenario '{name}'")
    return p


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
    snap = g.snapshot()  # scenario, beat, beat_title, clock, present (handles), run_id
    # Chips address people by appearance (strangers) — same as the fiction; the slug does the routing.
    snap["roster"] = [{"slug": s, "name": g.label(s)} for s in g.present]
    return snap


@router.post("/new")
async def new_game(body: NewGame):
    for m in (body.reply_model, body.dm_model):
        if m and m not in ALLOWED_MODEL_IDS:
            raise HTTPException(status_code=422, detail=f"unknown model {m!r}")
    # ONE live world per process: all games share the cast's memory namespaces and a new run
    # resets them — a second "concurrent" game would play against wiped minds. Finalize the old
    # run properly (its experiment-log row closes) before the reset.
    for old_gid, old in list(_games.items()):
        async with _lock(old_gid):
            try:
                await old.finish("(superseded by a new run)")
            except Exception:
                pass
            _games.pop(old_gid, None)
            _locks.pop(old_gid, None)
    g = Game(str(_scenario_path(body.scenario)), condition=body.condition,
             reply_model=body.reply_model, dm_model=body.dm_model)
    gid = uuid4().hex[:8]
    _games[gid] = g
    await g.begin()
    return {"game_id": gid, "title": g.scenario["title"], "events": g.history, "view": _view(g)}


@router.post("/{gid}/talk")
async def talk(gid: str, body: Talk):
    g = _game(gid)
    async with _lock(gid):
        n = len(g.history)
        await g.talk(body.target, body.line)
        return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/say")
async def say(gid: str, body: Say):
    g = _game(gid)
    async with _lock(gid):
        n = len(g.history)
        await g.say_to_room(body.line)
        return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/act")
async def act(gid: str, body: Act):
    g = _game(gid)
    async with _lock(gid):
        n = len(g.history)
        await g.act(body.action)
        return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/advance")
async def advance(gid: str):
    g = _game(gid)
    async with _lock(gid):
        n = len(g.history)
        more = await g.advance()
        return {"events": g.history[n:], "view": _view(g), "ended": not more}


@router.post("/{gid}/finish")
async def finish(gid: str, body: Finish):
    g = _game(gid)
    async with _lock(gid):
        await g.finish(body.outcome)
    _games.pop(gid, None)
    _locks.pop(gid, None)
    return {"ok": True, "run_id": g.run_id}


class Voice(BaseModel):
    slug: str
    text: str


@router.post("/{gid}/voice")
async def voice(gid: str, body: Voice):
    """A character's line as STREAMING audio (PCM s16le mono, X-Sample-Rate header) — the
    text game's presentation layer, beside the game not inside it. Streams chunks as the
    provider renders them so the browser starts playback at first audio, not at the end.
    Cast per slug lives in casting.HUME_VOICES; GAME_TTS picks the provider."""
    from fastapi.responses import StreamingResponse
    from orchestrator.config import AUDIO_SAMPLE_RATE
    from . import casting, policy
    from .bridge.mind_api import _tts, _tts_provider
    _game(gid)   # 404 on unknown/expired games
    provider = _tts_provider()
    if provider == "hume":
        vid = casting.hume_voice(body.slug)
        text = body.text            # Hume ACTS the stage directions (adapter splits them out)
    else:
        raise HTTPException(status_code=404,
                            detail=f"play-view voice is cast for GAME_TTS=hume (got '{provider}')")
    if not (text or "").strip():
        raise HTTPException(status_code=400, detail="nothing to speak")
    tts = _tts()

    async def gen():
        async for chunk in tts.stream_speech(text, vid):
            yield chunk

    return StreamingResponse(gen(), media_type="application/octet-stream",
                             headers={"X-Sample-Rate": str(AUDIO_SAMPLE_RATE),
                                      "Cache-Control": "no-store"})


@router.get("/{gid}/state")
async def state(gid: str):
    g = _game(gid)
    return {"view": _view(g), "history": g.history}
