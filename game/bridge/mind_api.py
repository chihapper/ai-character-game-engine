"""The MIND SERVER seam for a foreign world (#35/#38): Unity (or any client that owns a world)
drives the UNCHANGED engine over plain JSON. The client composes each NPC's first-person percept
(line of sight, gaze, proximity — earned from real space) into `situation`; the engine never
learns what a raycast is. Game policy (react thresholds, magnitudes, name/acquaintance rules)
lives in game/policy.py, shared with the grid arena so the treatment arms can't drift.

ONE live session per process — every session shares the per-character memory namespaces and a
new session resets them (same rule as the grid arena; run-scoped namespaces are #37). All DTOs
are flat/array-shaped so Unity's built-in JsonUtility can produce and parse them."""
from __future__ import annotations

import asyncio
import glob
import os
from pathlib import Path
from uuid import uuid4

import yaml
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from orchestrator.adapters.llm_anthropic import AnthropicLLM
from orchestrator.character_store import load_character
from orchestrator.config import ALLOWED_MODEL_IDS, EngineCaps, get_settings
from orchestrator.context import RespondRequest, Situation
from orchestrator.engine import Engine
from orchestrator.memory.long_term import LongTermMemory

from .. import casting, experiment_log, policy

def _tts():
    from orchestrator.adapters.tts_elevenlabs import ElevenLabsTTS
    return ElevenLabsTTS()

def _stt():
    from orchestrator.adapters.stt_assemblyai import AssemblyAISTT
    return AssemblyAISTT()

router = APIRouter(prefix="/api/mind")

_GAME_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO = "ferry_crossing.yaml"


class MindSession:
    """The engines for one cast + the run bookkeeping — a world-less ArenaGame."""

    def __init__(self, scenario_path: Path, reply_model: str | None):
        self.scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
        self.cast = [c["slug"] for c in self.scenario["cast"]]
        self.handles = {c["slug"]: (c.get("handle") or "someone").strip() for c in self.scenario["cast"]}
        self.here_because = {c["slug"]: (c.get("here_because") or "").strip() for c in self.scenario["cast"]}
        self.player_handle = (self.scenario.get("player_handle") or "a newcomer").strip()
        over = dict(relationship_state=True, reflection_enabled=True, intent_state=True,
                    background_reflection=True)
        window = (self.scenario.get("clock") or {}).get("recent_happenings_window")
        if window:
            over["recent_happenings_window"] = float(window)
        caps = EngineCaps.from_settings(get_settings(), **over)
        mem_dir = Path(get_settings().memory_dir)
        for slug in self.cast:  # fresh minds per run (shared namespaces; one live session)
            ns = load_character(slug).memory_namespace
            for f in glob.glob(str(mem_dir / f"{ns}.*")):
                os.remove(f)
            LongTermMemory.invalidate(ns)
        by_slug = {c["slug"]: c for c in self.scenario["cast"]}
        self.engines = {slug: Engine(casting.situate(load_character(slug), self.scenario, by_slug.get(slug)),
                                     AnthropicLLM(model=reply_model), caps=caps)
                        for slug in self.cast}
        # voice casting: profile ElevenLabs voice_id wins; else the scenario's authored voice
        # NAME resolved against the account's library at first use (game data end to end)
        self.voice_names = {c["slug"]: (c.get("voice") or "").strip() for c in self.scenario["cast"]}
        self.voice_ids: dict = {}
        self.voice_ready = bool(get_settings().elevenlabs_api_key)
        book = get_settings().salience_model
        self.run_id = experiment_log.start_run(
            condition="TREAT-EMBODIED-3D", scenario=self.scenario["id"], characters=self.cast,
            models=f"reply={reply_model or 'default'} book={book}")

    def engine(self, slug: str) -> Engine:
        eng = self.engines.get(slug)
        if eng is None:
            raise HTTPException(status_code=404, detail=f"no such character in this session: {slug}")
        return eng

    def situation(self, slug: str, sit: "SituationDTO | None") -> Situation | None:
        d = {"location": sit.location, "present": sit.present, "clock": sit.clock} if sit else {}
        d["extra"] = {"Performance": sit.performance if sit and sit.performance
                      else policy.PERFORMANCE_RULES}
        if sit and sit.ambient:
            d["extra"]["Around you, right now"] = sit.ambient
        frame = (self.scenario.get("world_frame") or "").strip()
        if frame:  # the scenario's world overrides a reused sheet's old life (no Marco here)
            d["extra"]["The world you live in"] = frame
        if self.here_because.get(slug):
            d["extra"]["Why you're here tonight"] = self.here_because[slug]
        return Situation.from_dict(d)

    async def voice_for(self, slug: str) -> str | None:
        if not self.voice_ready:
            return None
        if slug in self.voice_ids:
            return self.voice_ids[slug]
        char = self.engine(slug).character
        vid = (char.voice_id or "").strip() if getattr(char, "tts_provider", "") == "elevenlabs" else ""
        if not vid:
            try:
                voices = await _tts().list_voices()
                want = self.voice_names.get(slug, "").lower()
                match = next((v for v in voices if want and want in (v["name"] or "").lower()), None)
                vid = (match or (voices[0] if voices else {})).get("id") or ""
            except Exception:
                vid = ""
        self.voice_ids[slug] = vid or None
        return self.voice_ids[slug]

    async def finish(self, outcome: str) -> None:
        for eng in self.engines.values():
            await eng.flush_reflection()
        experiment_log.finalize_run(self.run_id, outcome or "(unity session)")


_sessions: dict[str, MindSession] = {}
_locks: dict[str, asyncio.Lock] = {}


def _s(sid: str) -> MindSession:
    s = _sessions.get(sid)
    if s is None:
        raise HTTPException(status_code=404, detail="no such session — create one")
    return s


def _lock(sid: str) -> asyncio.Lock:
    return _locks.setdefault(sid, asyncio.Lock())


# ---- DTOs (JsonUtility-friendly: flat fields + arrays, no dicts) --------------------------------

class NewSession(BaseModel):
    scenario: str = DEFAULT_SCENARIO
    reply_model: str | None = None


class SituationDTO(BaseModel):
    location: str = ""
    present: list[str] = Field(default_factory=list)  # client-composed first-person strings
    clock: float | None = None
    performance: str = ""  # optional override of the default performance rules
    ambient: str = ""      # what the world is DOING around them (the storm's arc, perceived)


class Respond(BaseModel):
    line: str = ""    # a spoken player line (framed as address by the engine)
    event: str = ""   # OR a non-spoken trigger ("you just watched the stranger bar the door")
    situation: SituationDTO | None = None


class Choose(BaseModel):
    situation: str = ""            # the rendered first-person scene text
    options: list[str] = Field(default_factory=list)


class ObservedItem(BaseModel):
    slug: str
    observed: str  # first-person, composed by the client ("the newcomer (close by) bars the door")


class Observe(BaseModel):
    clock: float | None = None
    magnitude: float = Field(default=0.1, ge=0, le=1)
    items: list[ObservedItem] = Field(default_factory=list)


class Acted(BaseModel):
    action: str
    reason: str = ""
    clock: float | None = None


class Finish(BaseModel):
    outcome: str = ""


# ---- endpoints -----------------------------------------------------------------------------------

@router.post("/session")
async def new_session(body: NewSession):
    if body.reply_model and body.reply_model not in ALLOWED_MODEL_IDS:
        raise HTTPException(status_code=422, detail=f"unknown reply_model {body.reply_model!r}")
    path = _GAME_DIR / "scenarios" / Path(body.scenario or DEFAULT_SCENARIO).name
    if path.suffix != ".yaml" or not path.is_file():
        raise HTTPException(status_code=400, detail=f"unknown scenario '{body.scenario}'")
    for sid, old in list(_sessions.items()):  # one live session per process (shared namespaces)
        async with _lock(sid):
            try:
                await old.finish("(superseded by a new session)")
            except Exception:
                pass
            _sessions.pop(sid, None)
            _locks.pop(sid, None)
    s = MindSession(path, body.reply_model)
    sid = uuid4().hex[:8]
    _sessions[sid] = s
    return {"session_id": sid, "title": s.scenario["title"], "player_handle": s.player_handle,
            "voice": s.voice_ready,
            "react_at": policy.REACT_SALIENCE, "speak_at": policy.SPEAK_SALIENCE,
            "cast": [{"slug": c, "handle": s.handles[c], "here_because": s.here_because[c]}
                     for c in s.cast]}


@router.post("/{sid}/{slug}/respond")
async def respond(sid: str, slug: str, body: Respond):
    s = _s(sid)
    eng = s.engine(slug)
    if not (body.line.strip() or body.event.strip()):
        raise HTTPException(status_code=400, detail="need line or event")
    async with _lock(sid):
        reply = await eng.respond(RespondRequest(
            player_input=body.line.strip() or None, event=body.event.strip() or None,
            situation=s.situation(slug, body.situation)))
    return {"reply": reply, "name_spoken": policy.spoken_name(eng.character.name, reply) or ""}


@router.post("/{sid}/{slug}/choose")
async def choose(sid: str, slug: str, body: Choose):
    s = _s(sid)
    eng = s.engine(slug)
    if not body.options:
        raise HTTPException(status_code=400, detail="need options (the afforded actions)")
    sit = body.situation
    frame = (s.scenario.get("world_frame") or "").strip()
    if frame:  # choices ground on the scenario's world too, not a reused sheet's old life
        sit = f"(The world you live in: {frame})\n{sit}"
    async with _lock(sid):
        out = await eng.choose_action(sit, body.options)
    return {"action": out.get("action") or "", "reason": out.get("reason") or ""}


@router.post("/{sid}/observe")
async def observe(sid: str, body: Observe):
    """The react recipe's server half: each witness remembers its own first-person observation
    (appraised salience, #25 magnitude hint) and shared policy maps salience -> ''|'act'|'speak'.
    The CLIENT decided who witnessed (line of sight / earshot — free from the scene) and, for
    reactors, follows up with /choose or /respond."""
    s = _s(sid)
    async with _lock(sid):
        async def appraise(item: ObservedItem):
            sal = await s.engine(item.slug).remember(
                item.observed, kind="player_event", t=body.clock, magnitude=body.magnitude)
            return {"slug": item.slug, "salience": sal or 0.0,
                    "react": policy.react_verdict(sal or 0.0)}
        return {"results": await asyncio.gather(*(appraise(i) for i in body.items))}


@router.post("/{sid}/{slug}/acted")
async def acted(sid: str, slug: str, body: Acted):
    """The game ENACTED a chosen action — write it into the character's memory as their OWN act.
    Without this the body moves but the mind never learns it did ('why did you come over?' →
    confabulation — the sandbox continuity bug, rediscovered live on the Unity arm). The stored
    form + pinned salience put it in the #30 working-memory foreground for the next few beats."""
    s = _s(sid)
    eng = s.engine(slug)
    text = f"(chose, of their own will) {body.action}" + (f" — {body.reason}" if body.reason else "")
    async with _lock(sid):
        await eng.remember(text, kind="decision", importance=0.65, t=body.clock)
    return {"ok": True}


class Speak(BaseModel):
    text: str


@router.post("/{sid}/{slug}/speak")
async def speak(sid: str, slug: str, body: Speak):
    """The character's line as AUDIO in their own voice — raw PCM s16le mono (rate in header),
    played by the client at the speaker's position. Stateless: no session lock held."""
    s = _s(sid)
    vid = await s.voice_for(slug)
    if not vid or not body.text.strip():
        raise HTTPException(status_code=404, detail="no voice available")
    from orchestrator.config import AUDIO_SAMPLE_RATE
    chunks = []
    async for chunk in _tts().stream_speech(body.text, vid):
        chunks.append(chunk)
    if not chunks:
        raise HTTPException(status_code=404, detail="nothing speakable")
    return Response(content=b"".join(chunks), media_type="application/octet-stream",
                    headers={"X-Sample-Rate": str(AUDIO_SAMPLE_RATE)})


@router.post("/{sid}/stt")
async def stt(sid: str, request: Request):
    """Push-to-talk: a WAV clip in, the player's words out (AssemblyAI batch — short clips
    resolve in a few seconds)."""
    _s(sid)
    audio = await request.body()
    if not audio or len(audio) < 1000:
        raise HTTPException(status_code=400, detail="empty clip")
    text = await _stt().transcribe(audio)
    return {"text": (text or "").strip()}


@router.post("/{sid}/finish")
async def finish(sid: str, body: Finish):
    s = _s(sid)
    async with _lock(sid):
        await s.finish(body.outcome)
    _sessions.pop(sid, None)
    _locks.pop(sid, None)
    return {"ok": True, "run_id": s.run_id}
