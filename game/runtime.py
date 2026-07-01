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
from orchestrator.config import ROOT_DIR, EngineCaps, get_settings
from orchestrator.context import RespondRequest, Situation
from orchestrator.engine import Engine
from orchestrator.memory.long_term import LongTermMemory

from . import experiment_log
from .dm import DM

RUNS_DIR = ROOT_DIR / ".game_runs"  # repo-anchored, never cwd-relative


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
        # The whole point of the game is the affect/agency engine — turn it on PER-ENGINE (never by
        # mutating the process-global settings; arch review theme B).
        caps = EngineCaps.from_settings(get_settings(), relationship_state=True,
                                        reflection_enabled=True, intent_state=True)
        self.dm = DM(self.scenario, model=dm_model)
        self.present = [c["slug"] for c in self.scenario["cast"]]
        if reset:
            self._wipe_memory()
        self.engines = {c["slug"]: Engine(load_character(c["slug"]), AnthropicLLM(model=reply_model),
                                          caps=caps)
                        for c in self.scenario["cast"]}
        # Scenario-specific "why you're here tonight" — reconciles each borrowed character with this
        # setting; injected into their scene context every turn so responses are grounded in it.
        self.here_because = {c["slug"]: (c.get("here_because") or "").strip() for c in self.scenario["cast"]}
        # How each is referred to before a name is spoken (strangers) — used everywhere names would leak.
        self.handles = {c["slug"]: (c.get("handle") or "someone here").strip() for c in self.scenario["cast"]}
        self.known_names: dict[str, str] = {}  # slug -> name, once that character has spoken it aloud
        # Authoritative world-state the stateless DM narrates FROM (so it can't drift the player around).
        self.player_location = (self.scenario.get("player", {}).get("start_location")
                                or "in the taproom").strip()
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

    def _ref(self, slug: str) -> str:
        """How this person is referred to in-fiction RIGHT NOW: their name once they've spoken it,
        otherwise their appearance handle (strangers don't know names yet)."""
        return self.known_names.get(slug) or self.handles.get(slug) or "someone"

    def label(self, slug: str) -> str:
        """Standalone display label — the current reference, capitalized (handle, or name once learned)."""
        r = self._ref(slug)
        return r[:1].upper() + r[1:]

    def _maybe_learn_name(self, slug: str, text: str) -> None:
        """Name-discovery: if this character speaks any form of their OWN name (first, nickname, or
        surname) in a reply, the room now knows it — switch from handle to that name from here on.
        Stores the form they actually used (so 'Bri', 'Pockets', 'Della' — whatever they gave)."""
        if slug in self.known_names:
            return
        raw = re.sub(r"\s*\([^)]*\)\s*$", "", self.engines[slug].character.name)  # drop dev suffix
        candidates = re.findall(r"[A-Za-z]{2,}", raw.replace("'", " ").replace('"', " "))
        for c in candidates:
            if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE):
                self.known_names[slug] = c
                return

    def _scrub(self, text: str) -> str:
        """Belt-and-suspenders: replace any UNLEARNED character's name-forms with their handle, so an
        unlearned proper name can never reach the player or the DM even if the model slips. Learned
        names (spoken in dialogue) pass through. NOT applied to character dialogue — that's where names
        legitimately emerge."""
        if not text:
            return text
        for slug in self.present:
            if slug in self.known_names:
                continue
            handle = self.handles.get(slug) or "someone"
            raw = re.sub(r"\s*\([^)]*\)\s*$", "", self.engines[slug].character.name)
            raw = re.sub(r"\s+", " ", raw.replace("'", " ").replace('"', " ")).strip()
            forms = sorted({raw, *re.findall(r"[A-Za-z]{3,}", raw)}, key=len, reverse=True)
            for f in forms:
                if len(f) >= 3:
                    text = re.sub(rf"\b{re.escape(f)}\b", handle, text, flags=re.IGNORECASE)
            # a "First Last" leak becomes "handle handle" — collapse the repeat
            text = re.sub(rf"\b({re.escape(handle)})(\s+\1\b)+", r"\1", text, flags=re.IGNORECASE)
        return text

    def _resolve(self, ref: str) -> str | None:
        """Map a player-typed slug / name / appearance-handle to a present cast slug."""
        ref = (ref or "").strip().lower()
        for slug in self.present:
            if ref and (ref == slug or ref in self._name(slug).lower()
                        or ref in (self.handles.get(slug) or "").lower()
                        or ref in (self.known_names.get(slug) or "").lower()):
                return slug
        return None

    def _wipe_memory(self) -> None:
        for c in self.scenario["cast"]:
            ns = load_character(c["slug"]).memory_namespace
            for f in glob.glob(str(Path(get_settings().memory_dir) / f"{ns}.*")):
                os.remove(f)
            LongTermMemory.invalidate(ns)  # drop any shared cache over the deleted files

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
        return self._scrub("\n".join(out))

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
        others = [self._ref(s) for s in self.present if s != slug]
        recent = [f'{self.label(sl)} just said: "{ln}"' for sl, ln in (in_scene or [])]
        extra = {"Where the player is": self.player_location,
                 "Performance": (
                     "Speak your words in the first person, in quotes. Write your OWN actions and "
                     "reactions in the THIRD person (e.g. 'she brushes the rain from her hair'), never "
                     "the second person. Do not narrate the player's actions, body, or feelings.")}
        if self.here_because.get(slug):
            extra["Why you're here tonight"] = self.here_because[slug]
        return Situation(location=self._perception, present=others, recent_events=recent,
                         extra=extra, game_time=self._beat()["title"], clock=self.clock)

    def _dialogue_recap(self, n: int = 4) -> str:
        """The last few player/NPC lines, so the responder-picker can read who's being addressed."""
        keep = [h for h in self.history if h["kind"] in ("player", "dialogue")]
        return self._scrub("\n".join(
            f"{('Player' if h['kind'] == 'player' else h.get('who', ''))}: {h['text'][:160]}"
            for h in keep[-n:]))

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

    def _refs(self) -> list[str]:
        return [self._ref(s) for s in self.present]

    async def _enter_beat(self) -> None:
        beat = self._beat()
        refs = self._refs()
        narration = self._scrub(await self.dm.narrate_beat(beat, self._recap(), refs, self.player_location))
        self._log("narration", narration, beat_title=beat["title"])
        self._perception = self._scrub(await self.dm.scene_perception(beat, refs, self.player_location,
                                                                     recent=self._recap()))
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
                    self._log("reaction", self._scrub(dec["world_action"]), slug=slug, who=self.label(slug))

    async def talk(self, target_ref: str, line: str) -> str:
        slug = self._resolve(target_ref)
        if not slug:
            return f"(no one here answers to '{target_ref}')"
        self._log("player", line, to=slug)
        reply = await self.engines[slug].respond(
            RespondRequest(player_input=line, situation=self._situation_for(slug)))
        self._log("dialogue", reply, slug=slug, who=self.label(slug))
        self._maybe_learn_name(slug, reply)
        return reply

    async def say_to_room(self, line: str, *, max_speakers: int = 3) -> list[tuple[str, str]]:
        """The player addresses everyone; the DM picks who speaks up and they answer IN SEQUENCE,
        each perceiving the lines said before them this exchange (a group beat / NPC cross-awareness)."""
        self._log("player", line, to="room")
        responders = await self.dm.pick_responders(self._refs(), line, recent=self._dialogue_recap(),
                                                    maxn=max_speakers)
        if not responders:
            self._log("narration", "The words settle into the room; no one takes them up just yet.")
            return []
        said: list[tuple[str, str]] = []  # (slug, line) — perceived by later speakers this exchange
        for ref in responders:
            slug = self._resolve(ref)
            if not slug:
                continue
            reply = await self.engines[slug].respond(
                RespondRequest(player_input=line, situation=self._situation_for(slug, in_scene=said)))
            self._log("dialogue", reply, slug=slug, who=self.label(slug))
            self._maybe_learn_name(slug, reply)
            said.append((slug, reply))
        return [(self.label(s), r) for s, r in said]

    async def act(self, action: str) -> str:
        self._log("player_action", action)
        text = await self.dm.adjudicate(action, self._perception, self._refs(), self.player_location)
        # The DM appends `LOCATION: ...` ONLY when the action moved the player — apply it, strip it.
        m = re.search(r"(?im)^\s*LOCATION:\s*(.+?)\s*$", text)
        if m:
            self.player_location = m.group(1).strip()
            text = (text[:m.start()] + text[m.end():]).strip()
        text = self._scrub(text)
        self._log("narration", text)
        return text

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
