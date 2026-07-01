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
        # Scenario-specific "why you're here tonight" — reconciles each borrowed character with this
        # setting; injected into their scene context every turn so responses are grounded in it.
        self.here_because = {c["slug"]: (c.get("here_because") or "").strip() for c in self.scenario["cast"]}
        # How each is referred to before a name is spoken (strangers) — used everywhere names would leak.
        self.handles = {c["slug"]: (c.get("handle") or "someone here").strip() for c in self.scenario["cast"]}
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

    def label(self, slug: str) -> str:
        """Standalone display label — the appearance-handle, capitalized. Names aren't known in-fiction
        yet (strangers), so people are shown by how they look until a name is spoken in dialogue."""
        h = self.handles.get(slug) or "someone"
        return h[:1].upper() + h[1:]

    def _resolve(self, ref: str) -> str | None:
        """Map a player-typed slug / name / appearance-handle to a present cast slug."""
        ref = (ref or "").strip().lower()
        for slug in self.present:
            if ref and (ref == slug or ref in self._name(slug).lower()
                        or ref in (self.handles.get(slug) or "").lower()):
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

    def _recap(self, n: int = 6) -> str:
        """A labelled 'story so far' for the DM — recent narration, events, and who said what — so it
        can advance the scene instead of re-establishing or contradicting it."""
        keep = [h for h in self.history if h["kind"] in ("narration", "event", "dialogue", "reaction")]
        out = []
        for h in keep[-n:]:
            if h["kind"] == "dialogue":
                out.append(f'{h.get("who", "")}: {h["text"][:140]}')
            elif h["kind"] == "event":
                out.append(f'[event] {h["text"][:140]}')
            elif h["kind"] == "reaction":
                out.append(f'{h.get("who", "")} {h["text"][:140]}')
            else:
                out.append(h["text"][:140])
        return "\n".join(out)

    def _beat(self) -> dict:
        return self.scenario["beats"][self.beat_i]

    def _log(self, kind: str, text: str, **meta) -> dict:
        rec = {"beat": self._beat()["id"], "clock": self.clock, "kind": kind, "text": text, **meta}
        self.history.append(rec)
        if self.transcript_path:
            with open(self.transcript_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def _situation_for(self, slug: str, *, in_scene: list | None = None) -> Situation:
        """The perceiving NPC's view of the room right now: the rich-text perception, who's here, any
        lines JUST said in this exchange (so an NPC responding to the room hears the others), and why
        THEY are here tonight (scenario grounding)."""
        others = [self.handles[s] for s in self.present if s != slug]
        recent = [f'{self.label(sl)} just said: "{ln}"' for sl, ln in (in_scene or [])]
        extra = {"Performance": (
            "Speak your words in the first person, in quotes. Write your OWN actions and reactions in "
            "the THIRD person (e.g. 'she brushes the rain from her hair'), never the second person. "
            "Do not narrate the player's actions, body, or feelings — that is theirs.")}
        if self.here_because.get(slug):
            extra["Why you're here tonight"] = self.here_because[slug]
        return Situation(location=self._perception, present=others, recent_events=recent,
                         extra=extra, game_time=self._beat()["title"], clock=self.clock)

    def _dialogue_recap(self, n: int = 4) -> str:
        """The last few player/NPC lines, so the responder-picker can read who's being addressed."""
        keep = [h for h in self.history if h["kind"] in ("player", "dialogue")]
        return "\n".join(f"{('Player' if h['kind'] == 'player' else h.get('who', ''))}: {h['text'][:160]}"
                         for h in keep[-n:])

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
        handles = [self.handles[s] for s in self.present]
        narration = await self.dm.narrate_beat(beat, self._recap(), handles)
        self._log("narration", narration, beat_title=beat["title"])
        self._perception = await self.dm.scene_perception(beat, handles, recent=self._recap())
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
                    self._log("reaction", dec["world_action"], slug=slug, who=self.label(slug))

    async def talk(self, target_ref: str, line: str) -> str:
        slug = self._resolve(target_ref)
        if not slug:
            return f"(no one here answers to '{target_ref}')"
        self._log("player", line, to=slug)
        reply = await self.engines[slug].respond(
            RespondRequest(player_input=line, situation=self._situation_for(slug)))
        self._log("dialogue", reply, slug=slug, who=self.label(slug))
        return reply

    async def say_to_room(self, line: str, *, max_speakers: int = 3) -> list[tuple[str, str]]:
        """The player addresses everyone; the DM picks who speaks up and they answer IN SEQUENCE,
        each perceiving the lines said before them this exchange (a group beat / NPC cross-awareness)."""
        self._log("player", line, to="room")
        handles = [self.handles[s] for s in self.present]
        responders = await self.dm.pick_responders(handles, line, recent=self._dialogue_recap(),
                                                    maxn=max_speakers)
        if not responders:
            self._log("narration", "The words settle into the room; no one takes them up just yet.")
            return []
        said: list[tuple[str, str]] = []  # (slug, line) — perceived by later speakers this exchange
        for handle in responders:
            slug = self._resolve(handle)
            if not slug:
                continue
            reply = await self.engines[slug].respond(
                RespondRequest(player_input=line, situation=self._situation_for(slug, in_scene=said)))
            self._log("dialogue", reply, slug=slug, who=self.label(slug))
            said.append((slug, reply))
        return [(self.label(s), r) for s, r in said]

    async def act(self, action: str) -> str:
        self._log("player_action", action)
        narration = await self.dm.adjudicate(action, self._perception, [self.handles[s] for s in self.present])
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
                "present": [self.label(s) for s in self.present], "run_id": self.run_id}
