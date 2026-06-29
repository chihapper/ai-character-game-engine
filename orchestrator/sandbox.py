"""Director's sandbox — a dev-only test surface that lets you drive an NPC's world by hand: talk to
them, jump the in-game clock forward, inject world events at a chosen time, trigger a deliberation,
and watch the inner state change. It deliberately CIRCUMVENTS normal play so the engine's
metamorphosis (scars, evolving goals, RR-grounded change between scenes) can be validated in minutes
instead of hours. Single-user dev tool: holds one live Engine per character (short-term continuity),
backed by the same file-persisted stores the real runtime uses.

Mounted under /api/sandbox/* and the /sandbox page. Scenarios (sequences of steps) save to
.sandbox_scenarios/ and replay against any character.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import pathlib
import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .adapters.llm_anthropic import AnthropicLLM
from .character_store import load_character
from .config import get_settings
from .context import RespondRequest, Situation
from .engine import Engine

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])

_engines: dict[str, Engine] = {}
SCEN_DIR = pathlib.Path(".sandbox_scenarios")
SAVES_DIR = pathlib.Path(".sandbox_saves")     # save-games: snapshots of ALL characters' state
MEM_DIR = pathlib.Path(".memory")              # the engine's file-backed stores (per namespace)
TRANS_DIR = SAVES_DIR / "_transcripts"         # durable per-turn verbatim transcripts (sandbox-layer)


def _safe(name: str) -> str:
    return "".join(c for c in (name or "") if c.isalnum() or c in " -_").strip() or "save"


def _state_chars() -> list[str]:
    """Memory-namespaces that currently have persisted state on disk."""
    if not MEM_DIR.exists():
        return []
    return sorted({p.name.split(".")[0] for p in MEM_DIR.glob("*") if p.is_file()})


def _log_turn(slug: str, clock, user: str, reply: str) -> None:
    """Append a turn to a durable, clean verbatim transcript — independent of the engine's
    reflection-flush timing, so a crash/restart can never lose the conversation as it was said."""
    TRANS_DIR.mkdir(parents=True, exist_ok=True)
    with (TRANS_DIR / f"{slug}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"clock": clock, "user": user, "reply": reply}) + "\n")


def _snapshot(name: str, clock=None) -> dict:
    """Copy ALL characters' persisted stores (+ transcripts) into a named save-game. Returns the
    manifest. Pure file copy of the stores the engine already uses — does NOT change the engine."""
    name = _safe(name)
    base = SAVES_DIR / name
    if (base / "memory").exists():
        shutil.rmtree(base / "memory")
    (base / "memory").mkdir(parents=True, exist_ok=True)
    chars = _state_chars()
    if MEM_DIR.exists():
        for f in MEM_DIR.glob("*"):
            if f.is_file():
                shutil.copy2(f, base / "memory" / f.name)
    if TRANS_DIR.exists():  # bundle the verbatim transcripts with the save
        (base / "transcripts").mkdir(exist_ok=True)
        for f in TRANS_DIR.glob("*.jsonl"):
            shutil.copy2(f, base / "transcripts" / f.name)
    manifest = {"name": name, "created": datetime.datetime.now().isoformat(timespec="seconds"),
                "clock": clock, "characters": chars}
    (base / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _restore(name: str) -> dict:
    """Restore a save-game: overwrite .memory (+ transcripts) from the snapshot and drop all live
    engines so they reload from the restored state. Auto-backs up current state first."""
    base = SAVES_DIR / _safe(name)
    if not (base / "memory").exists():
        raise HTTPException(status_code=404, detail=f"no save '{name}'")
    _snapshot("_autosave_before_load")  # safety net — current state is never silently lost
    MEM_DIR.mkdir(exist_ok=True)
    for f in MEM_DIR.glob("*"):         # clear current, then restore the snapshot's set exactly
        if f.is_file():
            f.unlink()
    for f in (base / "memory").glob("*"):
        shutil.copy2(f, MEM_DIR / f.name)
    if (base / "transcripts").exists():
        TRANS_DIR.mkdir(parents=True, exist_ok=True)
        for f in (base / "transcripts").glob("*.jsonl"):
            shutil.copy2(f, TRANS_DIR / f.name)
    _engines.clear()                    # every character reloads from the restored stores
    return json.loads((base / "manifest.json").read_text(encoding="utf-8"))


def _engine(slug: str) -> Engine:
    """Live Engine per character (created lazily; short-term persists for the session). The affect /
    metamorphosis features default OFF on the server, so enable them here — the whole point of the
    sandbox is to exercise the relationship + deliberation engine."""
    s = get_settings()
    s.relationship_state = True
    s.reflection_enabled = True
    s.intent_state = True
    if slug not in _engines:
        try:
            char = load_character(slug)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"no character '{slug}'") from e
        _engines[slug] = Engine(char, AnthropicLLM(model=s.deliberation_model))
    return _engines[slug]


def _state(eng: Engine) -> dict:
    recs = sorted(eng.long_term._all(), key=lambda r: (r.t if r.t is not None else float(r.index)))
    return {
        "relationship": eng.relationship.get().to_dict(),
        "goals": eng.agency.goals() or list(eng.character.goals),
        "intent": eng.intent.get().intent,
        "last_deliberation_t": eng.agency.last_t(),
        "recent_memories": [
            {"text": r.text, "importance": round(r.importance, 2), "kind": r.kind, "t": r.t}
            for r in recs[-10:]
        ],
    }


class Say(BaseModel):
    text: str
    clock: float | None = None


class Event(BaseModel):
    text: str
    importance: float = 0.6
    player_role: str | None = None   # "caused" | "benefited" | None (a pure world event)
    actor: str = "player"            # "player" | "self" (the NPC's own internal change)
    clock: float | None = None


class Deliberate(BaseModel):
    clock: float | None = None
    mode: str = "free"               # "free" | "gated"


class Scenario(BaseModel):
    name: str
    slug: str | None = None
    steps: list[dict] = []           # [{type: say|event|advance|deliberate, ...}]


@router.get("/{slug}/state")
async def get_state(slug: str):
    return _state(_engine(slug))


@router.post("/{slug}/say")
async def say(slug: str, body: Say):
    eng = _engine(slug)
    clk = body.clock if body.clock is not None else 0.0
    reply = await eng.respond(RespondRequest(player_input=body.text, situation=Situation(clock=clk)))
    _log_turn(slug, clk, body.text, reply)  # durable verbatim transcript, written per-turn
    return {"reply": reply, "state": _state(eng)}


@router.post("/{slug}/event")
async def event(slug: str, body: Event):
    eng = _engine(slug)
    await eng.remember(body.text, player_role=(body.player_role or None), actor=body.actor,
                       importance=body.importance, t=(body.clock if body.clock is not None else 0.0))
    return {"state": _state(eng)}


@router.post("/{slug}/deliberate")
async def deliberate(slug: str, body: Deliberate):
    eng = _engine(slug)
    dec = await eng.deliberate(Situation(clock=body.clock if body.clock is not None else 0.0), mode=body.mode)
    return {"decision": dec, "state": _state(eng)}


@router.post("/{slug}/reset")
async def reset(slug: str):
    """Drop the live engine and wipe this character's persisted stores — a clean slate."""
    _engines.pop(slug, None)
    try:
        ns = load_character(slug).memory_namespace
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"no character '{slug}'") from e
    for f in glob.glob(f".memory/{ns}.*"):
        os.remove(f)
    return {"state": _state(_engine(slug))}


class SaveReq(BaseModel):
    name: str
    clock: float | None = None


@router.get("/{slug}/transcript")
async def get_transcript(slug: str):
    """The durable verbatim transcript for this character (every say + reply, per-turn)."""
    p = TRANS_DIR / f"{slug}.jsonl"
    if not p.exists():
        return {"turns": []}
    turns = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {"turns": turns}


@router.post("/save")
async def save_game(body: SaveReq):
    """SAVE-GAME: snapshot the CURRENT state of ALL characters (memories, goals, scores, scars,
    intent) + transcripts into a named save. Deterministic — load restores exactly this point."""
    return {"ok": True, **_snapshot(body.name, clock=body.clock)}


@router.get("/saves")
async def list_saves():
    SAVES_DIR.mkdir(exist_ok=True)
    out = []
    for d in sorted(SAVES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):  # hide _transcripts / _autosave_* / _backup_*
            continue
        mf = d / "manifest.json"
        if mf.exists():
            try:
                out.append(json.loads(mf.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
    return out


@router.post("/load")
async def load_game(body: SaveReq):
    """LOAD-GAME: restore a save's exact state for ALL characters (auto-backs up current first)."""
    return {"ok": True, "manifest": _restore(body.name)}


@router.get("/scenarios")
async def list_scenarios():
    SCEN_DIR.mkdir(exist_ok=True)
    out = []
    for p in sorted(SCEN_DIR.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return out


@router.post("/scenarios")
async def save_scenario(body: Scenario):
    SCEN_DIR.mkdir(exist_ok=True)
    safe = "".join(c for c in body.name if c.isalnum() or c in " -_").strip() or "scenario"
    (SCEN_DIR / f"{safe}.json").write_text(
        json.dumps({"name": safe, "slug": body.slug, "steps": body.steps}, indent=2), encoding="utf-8")
    return {"ok": True, "name": safe}


@router.post("/{slug}/replay")
async def replay(slug: str, body: Scenario):
    """Run a saved step-sequence against a (freshly reset) engine, returning a transcript. `advance`
    steps move the in-game clock; say/event/deliberate act at the current clock."""
    try:
        ns = load_character(slug).memory_namespace
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"no character '{slug}'") from e
    _snapshot("_autosave_before_replay")  # replay is destructive — never lose the pre-replay state
    _engines.pop(slug, None)
    for f in glob.glob(f".memory/{ns}.*"):
        os.remove(f)
    eng = _engine(slug)
    clock, transcript = 0.0, []
    for step in body.steps:
        kind = step.get("type")
        if kind == "advance":
            clock += float(step.get("days", 0) or 0)
            transcript.append({"type": "advance", "clock": clock})
        elif kind == "say":
            reply = await eng.respond(RespondRequest(player_input=step.get("text", ""),
                                                     situation=Situation(clock=clock)))
            _log_turn(slug, clock, step.get("text", ""), reply)
            transcript.append({"type": "say", "clock": clock, "text": step.get("text", ""), "reply": reply})
        elif kind == "event":
            await eng.remember(step.get("text", ""), player_role=(step.get("player_role") or None),
                               actor=step.get("actor", "player"),
                               importance=float(step.get("importance", 0.6)), t=clock)
            transcript.append({"type": "event", "clock": clock, "text": step.get("text", "")})
        elif kind == "deliberate":
            dec = await eng.deliberate(Situation(clock=clock), mode=step.get("mode", "free"))
            transcript.append({"type": "deliberate", "clock": clock, "decision": dec})
    return {"transcript": transcript, "state": _state(eng)}
