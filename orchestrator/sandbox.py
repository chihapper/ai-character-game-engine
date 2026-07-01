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
from .memory.long_term import LongTermMemory
from .config import ROOT_DIR, EngineCaps, get_settings
from .context import RespondRequest, Situation
from .engine import Engine

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])

_engines: dict[str, Engine] = {}
# Per-role model choice (dev experiment: feel the cost vs realness tradeoff live). "reply" = the
# spoken dialogue (Engine.llm); "deliberation" = between-scenes change; "bookkeeping" = salience +
# reflection + the affect/scar judgment (assess_event_impact) — the last is NOT realness-free, hence
# the honest label in the UI. Defaults match the validated config (all Sonnet).
_MODELS = {"reply": "claude-sonnet-4-6", "deliberation": "claude-sonnet-4-6", "bookkeeping": "claude-sonnet-4-6"}
MODEL_OPTIONS = ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-8"]
# Anchored to the repo root / settings — NEVER the cwd (a server launched from elsewhere would
# otherwise reset/save against a different, empty .memory while engines write the real one).
SCEN_DIR = ROOT_DIR / ".sandbox_scenarios"
SAVES_DIR = ROOT_DIR / ".sandbox_saves"        # save-games: snapshots of ALL characters' state
MEM_DIR = pathlib.Path(get_settings().memory_dir)  # the engine's file-backed stores (per namespace)
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
    LongTermMemory.invalidate_all()     # ...including the shared memory caches (files were replaced)
    return json.loads((base / "manifest.json").read_text(encoding="utf-8"))


def _engine(slug: str) -> Engine:
    """Live Engine per character (created lazily; short-term persists for the session). The affect /
    metamorphosis features default OFF on the server, so enable them here — PER-ENGINE via
    EngineCaps, never by mutating the process-global settings (which silently reconfigured every
    other surface's engines — arch review theme B)."""
    _apply_models()  # honor the UI's per-role model choice (still global; dies with the item-5 LLM factory)
    if slug not in _engines:
        try:
            char = load_character(slug)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"no character '{slug}'") from e
        caps = EngineCaps.from_settings(get_settings(), relationship_state=True,
                                        reflection_enabled=True, intent_state=True)
        _engines[slug] = Engine(char, AnthropicLLM(model=_MODELS["reply"]), caps=caps)
    return _engines[slug]


def _apply_models():
    """Push the per-role model choice onto the global settings (deliberation + bookkeeping). The
    reply model is applied per-engine via Engine.llm (set at construction / on change)."""
    s = get_settings()
    s.deliberation_model = _MODELS["deliberation"]
    s.salience_model = _MODELS["bookkeeping"]
    s.reflection_model = _MODELS["bookkeeping"]


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
    importance: float | None = None  # pin = manual override; None = let the NPC appraise (#25)
    magnitude: float | None = None   # coarse objective-scale hint fed into NPC appraisal (#25)
    player_role: str | None = None   # "caused" | "benefited" | None (a pure world event)
    actor: str = "player"            # "player" | "self" (the NPC's own internal change)
    react: bool = False              # 2a: let them react IN THE MOMENT if it lands hard enough (#30)
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


REACT_SALIENCE_FLOOR = 0.7  # 2a: an event interrupts the scene only if the NPC RR-appraises it this high


@router.post("/{slug}/event")
async def event(slug: str, body: Event):
    eng = _engine(slug)
    clk = body.clock if body.clock is not None else 0.0
    # remember() RETURNS the character's appraised salience — the engine's half of the reaction seam.
    sal = await eng.remember(body.text, player_role=(body.player_role or None), actor=body.actor,
                             importance=body.importance, magnitude=body.magnitude, t=clk)
    out: dict = {"state": _state(eng)}
    if body.react:
        # The GAME (here, the sandbox) owns the interrupt policy: only take a beat to react if it
        # lands hard enough (#30 / 2a). RR — via the appraised salience — decides.
        out["salience"] = round(sal, 2) if sal is not None else None
        if sal is not None and sal >= REACT_SALIENCE_FLOOR:
            out["decision"] = await eng.deliberate(Situation(clock=clk), mode="free")
            out["reacted"] = True
            out["state"] = _state(eng)  # refresh after the reaction may have moved state
        else:
            out["reacted"] = False
    return out


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
    for f in glob.glob(str(MEM_DIR / f"{ns}.*")):
        os.remove(f)
    LongTermMemory.invalidate(ns)  # drop the shared cache so no live store resurrects deleted state
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


class ModelChoice(BaseModel):
    reply: str | None = None
    deliberation: str | None = None
    bookkeeping: str | None = None


@router.get("/models")
async def get_models():
    return {"choice": dict(_MODELS), "options": MODEL_OPTIONS}


@router.post("/models")
async def set_models(body: ModelChoice):
    for key, val in (("reply", body.reply), ("deliberation", body.deliberation), ("bookkeeping", body.bookkeeping)):
        if val:
            _MODELS[key] = val
    _apply_models()
    if body.reply:  # hot-swap the reply model on every live engine
        for eng in _engines.values():
            eng.llm = AnthropicLLM(model=body.reply)
    return {"ok": True, "choice": dict(_MODELS)}


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
    for f in glob.glob(str(MEM_DIR / f"{ns}.*")):
        os.remove(f)
    LongTermMemory.invalidate(ns)
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
            imp = step.get("importance")  # None on a recorded appraise-step -> NPC realizes it (#25)
            await eng.remember(step.get("text", ""), player_role=(step.get("player_role") or None),
                               actor=step.get("actor", "player"),
                               importance=(None if imp is None else float(imp)),
                               magnitude=step.get("magnitude"), t=clock)
            transcript.append({"type": "event", "clock": clock, "text": step.get("text", "")})
        elif kind == "deliberate":
            dec = await eng.deliberate(Situation(clock=clock), mode=step.get("mode", "free"))
            transcript.append({"type": "deliberate", "clock": clock, "decision": dec})
    return {"transcript": transcript, "state": _state(eng)}
