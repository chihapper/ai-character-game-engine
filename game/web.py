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
# One TTS adapter per game (built lazily on first /voice), so a stateful provider (Hume
# Octave continuation) keeps its cross-turn prosody through-line scoped to THIS playthrough
# and can't bleed into another concurrent game on the same NPC voice. Reset on a scene cut
# (/advance); evicted when the game finishes or is reaped.
_tts_by_game: dict = {}


def _game_tts(gid: str):
    """The game's own TTS adapter, reused across every /voice call so continuity carries
    turn-to-turn within the playthrough while staying isolated from other concurrent games."""
    tts = _tts_by_game.get(gid)
    if tts is None:
        from .bridge.mind_api import _tts
        tts = _tts()
        _tts_by_game[gid] = tts
    return tts


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
    snap["history_len"] = len(g.history)   # lets a client that lost a response resync the delta
    return snap


MAX_ACTIVE_GAMES = 5          # each concurrent world costs real LLM + TTS spend — cap it
IDLE_GAME_TTL_S = 90 * 60     # walked-away worlds get finalized (and their minds cleaned up)
_last_touch: dict[str, float] = {}


def _touch(gid: str) -> None:
    import time
    _last_touch[gid] = time.monotonic()


async def _reap_idle() -> None:
    """Finalize abandoned games: frees their run-scoped memories and a concurrency slot."""
    import time
    now = time.monotonic()
    for gid, g in list(_games.items()):
        if now - _last_touch.get(gid, now) > IDLE_GAME_TTL_S:
            async with _lock(gid):
                try:
                    await g.finish("(abandoned — idle timeout)")
                except Exception:
                    pass
                _games.pop(gid, None)
                _locks.pop(gid, None)
                _last_touch.pop(gid, None)
                _tts_by_game.pop(gid, None)


@router.post("/new")
async def new_game(body: NewGame):
    for m in (body.reply_model, body.dm_model):
        if m and m not in ALLOWED_MODEL_IDS:
            raise HTTPException(status_code=422, detail=f"unknown model {m!r}")
    # CONCURRENT worlds (#37): each game runs ISOLATED minds (run-scoped memory namespaces,
    # cleaned up at finish), so several people can play at once without sharing a world.
    await _reap_idle()
    if len(_games) >= MAX_ACTIVE_GAMES:
        raise HTTPException(status_code=429,
                            detail="the inn is full tonight — too many games in progress; try again soon")
    g = Game(str(_scenario_path(body.scenario)), condition=body.condition,
             reply_model=body.reply_model, dm_model=body.dm_model, isolated=True)
    gid = uuid4().hex[:8]
    _games[gid] = g
    _touch(gid)
    await g.begin()
    return {"game_id": gid, "title": g.scenario["title"], "events": g.history, "view": _view(g)}


@router.post("/{gid}/talk")
async def talk(gid: str, body: Talk):
    g = _game(gid)
    _touch(gid)
    async with _lock(gid):
        n = len(g.history)
        await g.talk(body.target, body.line)
        return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/say")
async def say(gid: str, body: Say):
    g = _game(gid)
    _touch(gid)
    async with _lock(gid):
        n = len(g.history)
        await g.say_to_room(body.line)
        return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/act")
async def act(gid: str, body: Act):
    g = _game(gid)
    _touch(gid)
    async with _lock(gid):
        n = len(g.history)
        await g.act(body.action)
        return {"events": g.history[n:], "view": _view(g)}


@router.post("/{gid}/advance")
async def advance(gid: str):
    g = _game(gid)
    _touch(gid)
    async with _lock(gid):
        n = len(g.history)
        more = await g.advance()
        # A beat advance is a scene cut: drop any carried voice mood so the next beat's
        # spoken lines start fresh instead of inheriting the previous scene's through-line.
        tts = _tts_by_game.get(gid)
        if tts is not None:
            tts.reset_continuation()
        return {"events": g.history[n:], "view": _view(g), "ended": not more}


@router.post("/{gid}/finish")
async def finish(gid: str, body: Finish):
    g = _game(gid)
    _touch(gid)
    async with _lock(gid):
        await g.finish(body.outcome)
    _games.pop(gid, None)
    _locks.pop(gid, None)
    _tts_by_game.pop(gid, None)
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
    from .bridge.mind_api import _tts_provider
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
    tts = _game_tts(gid)

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

