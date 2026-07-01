"""The game runtime: loads a scenario, drives the loop, and routes to the character engine per the
contract (respond / remember / deliberate). It owns the world (beats, clock, events, who's present)
and narrates via the DM; the engine owns the NPC minds. Headless + scriptable — the web play view
calls the same `Game` methods. Every playthrough writes a durable transcript and a row in the
embodiment-experiment log (#30)."""
from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

import yaml

from orchestrator.adapters.llm_anthropic import AnthropicLLM
from orchestrator.character_store import load_character
from orchestrator.config import get_settings
from orchestrator.context import RespondRequest, Situation
from orchestrator.engine import Engine

from . import experiment_log
from .dm import DM

RUNS_DIR = Path(".game_runs")


class Game:
    """One playthrough of one scenario. Condition ids match docs/embodiment-experiment.md
    (CTRL-TEXT is the text control arm)."""

    def __init__(self, scenario_path, *, condition: str = "CTRL-TEXT", reply_model: str | None = None,
                 dm_model: str | None = None, hours_per_beat: float = 2.0, reset: bool = True,
                 log_doc=None):
        self.scenario = yaml.safe_load(Path(scenario_path).read_text(encoding="utf-8"))
        self.condition = condition
        self.reply_model = reply_model
        self.dm_model = dm_model
        self.hours_per_beat = hours_per_beat
        self.log_doc = log_doc or experiment_log.DOC_PATH
        # The whole point of the game is the affect/agency engine — turn it on.
        s = get_settings()
        s.relationship_state = True
        s.reflection_enabled = True
        s.intent_state = True
        self.dm = DM(self.scenario, model=dm_model)
        self.present = [c["slug"] for c in self.scenario["cast"]]
        if reset:
            self._wipe_memory()
        self.engines = {c["slug"]: Engine(load_character(c["slug"]), AnthropicLLM(model=reply_model))
                        for c in self.scenario["cast"]}
        self.beat_i = 0
        self.clock = float(self.scenario.get("clock", {}).get("start", 0) or 0)
        self.history: list[dict] = []       # rolling narration/dialogue for DM recap
        self.run_id: str | None = None
        self.transcript_path: Path | None = None
        self._perception = ""               # current beat's shared rich perception

    # ---- helpers ------------------------------------------------------------
    def _name(self, slug: str) -> str:
        # Strip dev-variant suffixes like "(Inworld)"/"(Eleven)" for in-fiction display.
        return re.sub(r"\s*\([^)]*\)\s*$", "", self.engines[slug].character.name).strip()

    def _resolve(self, ref: str) -> str | None:
        """Map a player-typed name/slug to a present cast slug."""
        ref = (ref or "").strip().lower()
        for slug in self.present:
            if ref == slug or ref and ref in self._name(slug).lower():
                return slug
        return None

    def _wipe_memory(self) -> None:
        for c in self.scenario["cast"]:
            ns = load_character(c["slug"]).memory_namespace
            for f in glob.glob(f".memory/{ns}.*"):
                os.remove(f)

    def _models_str(self) -> str:
        book = get_settings().salience_model
        return f"reply={self.reply_model or 'default'} dm={self.dm_model or 'default'} book={book}"

    def _recap(self) -> str:
        keep = [h for h in self.history if h["kind"] in ("narration", "dialogue", "event")]
        return " ".join(h["text"][:160] for h in keep[-4:])

    def _beat(self) -> dict:
        return self.scenario["beats"][self.beat_i]

    def _log(self, kind: str, text: str, **meta) -> dict:
        rec = {"beat": self._beat()["id"], "clock": self.clock, "kind": kind, "text": text, **meta}
        self.history.append(rec)
        if self.transcript_path:
            with open(self.transcript_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def _situation_for(self, slug: str) -> Situation:
        """The perceiving NPC's view of the room right now (the rich-text perception + who's here)."""
        others = [self._name(s) for s in self.present if s != slug]
        return Situation(location=self._perception, present=others,
                         game_time=self._beat()["title"], clock=self.clock)

    # ---- lifecycle ----------------------------------------------------------
    async def begin(self) -> str:
        RUNS_DIR.mkdir(exist_ok=True)
        self.run_id = experiment_log.start_run(
            condition=self.condition, scenario=self.scenario["id"], characters=self.present,
            models=self._models_str(), doc=self.log_doc)
        self.transcript_path = RUNS_DIR / f"{self.run_id}.jsonl"
        experiment_log.update_run(self.run_id, transcript=str(self.transcript_path), doc=self.log_doc)
        self._log("player_role", self.scenario["player"]["opening"])
        await self._enter_beat()
        return self.run_id

    async def _enter_beat(self) -> None:
        beat = self._beat()
        narration = await self.dm.narrate_beat(beat, self._recap())
        self._log("narration", narration, beat_title=beat["title"])
        self._perception = await self.dm.scene_perception(beat, [self._name(s) for s in self.present])
        for ev in beat.get("events", []):
            await self._fire_event(ev)

    async def _fire_event(self, ev: dict) -> None:
        text, mag = ev["text"], ev.get("magnitude")
        to = ev.get("to")
        targets = self.present if to in (None, "all") else [t for t in to if t in self.present]
        self._log("event", text)
        threshold = self.scenario.get("deliberation", {}).get("react_threshold", 0.7)
        for slug in targets:
            sal = await self.engines[slug].remember(text, magnitude=mag, t=self.clock)
            if ev.get("react") and sal is not None and sal >= threshold:
                dec = await self.engines[slug].deliberate(Situation(clock=self.clock), mode="free")
                if dec.get("changed") and dec.get("world_action"):
                    self._log("reaction", dec["world_action"], slug=slug, who=self._name(slug))

    async def talk(self, target_ref: str, line: str) -> str:
        slug = self._resolve(target_ref)
        if not slug:
            return f"(no one here answers to '{target_ref}')"
        self._log("player", line, to=slug)
        reply = await self.engines[slug].respond(
            RespondRequest(player_input=line, situation=self._situation_for(slug)))
        self._log("dialogue", reply, slug=slug, who=self._name(slug))
        return reply

    async def act(self, action: str) -> str:
        self._log("player_action", action)
        narration = await self.dm.adjudicate(action, self._perception)
        self._log("narration", narration)
        return narration

    async def advance(self) -> bool:
        """Advance to the next beat: NPCs deliberate (metabolize the night), clock ticks, next beat
        is entered + its events fire. Returns False if there is no next beat (the story is over)."""
        if self.scenario.get("deliberation", {}).get("on_beat_advance"):
            for slug in self.present:
                await self.engines[slug].deliberate(Situation(clock=self.clock), mode="free")
        self.clock += self.hours_per_beat
        if self.beat_i + 1 >= len(self.scenario["beats"]):
            return False
        self.beat_i += 1
        await self._enter_beat()
        return True

    async def finish(self, outcome: str = "") -> None:
        if self.run_id:
            experiment_log.finalize_run(self.run_id, outcome or "(completed)", doc=self.log_doc)

    # ---- read-only snapshot for a play view / debugging ---------------------
    def snapshot(self) -> dict:
        return {"scenario": self.scenario["id"], "beat": self._beat()["id"],
                "beat_title": self._beat()["title"], "clock": self.clock,
                "present": [self._name(s) for s in self.present], "run_id": self.run_id}
