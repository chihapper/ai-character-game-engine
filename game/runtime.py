"""The game runtime: loads a scenario, drives the loop, and routes to the character engine per the
contract (respond / remember / deliberate). It owns the world (beats, clock, events, who's present)
and narrates via the DM; the engine owns the NPC minds. Headless + scriptable — the web play view
calls the same `Game` methods. Every playthrough writes a durable transcript and a row in the
embodiment-experiment log (#30)."""
from __future__ import annotations

import asyncio
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

from . import casting, experiment_log, policy
from .dm import DM

RUNS_DIR = ROOT_DIR / ".game_runs"  # repo-anchored, never cwd-relative


class Game:
    """One playthrough of one scenario. Condition ids match docs/embodiment-experiment.md
    (CTRL-TEXT is the text control arm)."""

    def __init__(self, scenario_path, *, condition: str = "CTRL-TEXT", reply_model: str | None = None,
                 dm_model: str | None = None, hours_per_beat: float = 2.0, reset: bool = True,
                 log_doc=None, isolated: bool = False):
        self.scenario = yaml.safe_load(Path(scenario_path).read_text(encoding="utf-8"))
        self.condition = condition
        self.reply_model = reply_model
        self.dm_model = dm_model
        self.hours_per_beat = hours_per_beat
        self.log_doc = log_doc or experiment_log.DOC_PATH
        # The whole point of the game is the affect/agency engine — turn it on PER-ENGINE (never by
        # mutating the process-global settings; arch review theme B).
        over = dict(relationship_state=True, reflection_enabled=True, intent_state=True,
                    background_reflection=True)  # long-lived server surface; finish() flushes
        window = (self.scenario.get("clock") or {}).get("recent_happenings_window")
        if window:  # the scenario's authored freshness window must reach the engine (it sat unread)
            over["recent_happenings_window"] = float(window)
        caps = EngineCaps.from_settings(get_settings(), **over)
        self.dm = DM(self.scenario, model=dm_model)
        self.present = [c["slug"] for c in self.scenario["cast"]]
        # ISOLATED (#37, run-scoped namespaces): this game gets its own COPIES of the minds —
        # a unique namespace per (run, character), born clean, deleted at finish(). Many games
        # can then run concurrently without stepping on each other's memories. The default
        # (shared namespaces + wipe) remains for experiments, where one canonical world is the
        # point and its memories are the artifact under study.
        from uuid import uuid4 as _uuid4
        self.ns_prefix = f"run-{_uuid4().hex[:10]}" if isolated else ""
        if reset and not self.ns_prefix:
            self._wipe_memory()

        # SITUATE each borrowed sheet INTO this world (same as the mind server, casting.situate):
        # bakes the world frame into the backstory at SYSTEM-PROMPT authority and applies the
        # cast's adapt swaps. Without this the text game ran raw sheets — Corvin as a literal
        # dockside harbormaster, Bri still naming "Marco" — because a per-turn situation note
        # can't out-argue the sheet. This is the real grounding; the situation extra is backup.
        by_slug = {c["slug"]: c for c in self.scenario["cast"]}

        def _char(slug: str):
            c = casting.situate(load_character(slug), self.scenario, by_slug.get(slug))
            if self.ns_prefix:
                from dataclasses import replace as _replace
                c = _replace(c, memory_namespace=f"{self.ns_prefix}.{c.memory_namespace}")
            return c

        self.engines = {c["slug"]: Engine(_char(c["slug"]), AnthropicLLM(model=reply_model),
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
                    # case-SENSITIVE: names in prose are capitalized; matching 'pockets' the verb
                    # because of Edwin "Pockets" Hale would mangle ordinary sentences.
                    text = re.sub(rf"\b{re.escape(f)}\b", handle, text)
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

    def _grounding_extra(self, slug: str) -> dict:
        """The world-anchoring EVERY situation needs so a borrowed sheet can't override tonight:
        the scenario's world frame (riverlands, no modern world) and why THIS character is here.
        Missing on the between-beat deliberation path was the 'Corvin at the docks' regression —
        his sheet is a harbormaster of a smuggling port; only this grounding makes him a river-inn
        guest. Same anchor the mind-server path injects into every situation."""
        extra = {"Performance": policy.PERFORMANCE_RULES}
        frame = (self.scenario.get("world_frame") or "").strip()
        if frame:
            extra["The world you live in"] = frame
        if self.here_because.get(slug):
            extra["Why you're here tonight"] = self.here_because[slug]
        return extra

    def _situation_for(self, slug: str, *, in_scene: list | None = None) -> Situation:
        """The perceiving NPC's view of the room right now: the rich-text perception, who's here, any
        lines JUST said in this exchange (so an NPC responding to the room hears the others), and why
        THEY are here tonight (scenario grounding)."""
        others = [self._ref(s) for s in self.present if s != slug]
        recent = [f'{self.label(sl)} just said: "{ln}"' for sl, ln in (in_scene or [])]
        extra = {"Where the player is": self.player_location, **self._grounding_extra(slug)}
        return Situation(location=self._perception, present=others, recent_events=recent,
                         extra=extra, game_time=self._beat()["title"], clock=self.clock)

    def _deliberation_situation(self, slug: str) -> Situation:
        """A GROUNDED situation for between-beat deliberation (advance + event reactions), so an
        off-duty mind metabolizes the night AS a guest in tonight's world, not its paper self."""
        return Situation(location=self._perception or self.player_location,
                         present=[self._ref(s) for s in self.present if s != slug],
                         extra=self._grounding_extra(slug),
                         game_time=self._beat()["title"], clock=self.clock)

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
        recap = self._recap()
        # narration and perception are independent DM calls — run them together (start-up
        # was two big sequential model calls before a player saw anything)
        narration, perception = await asyncio.gather(
            self.dm.narrate_beat(beat, recap, refs, self.player_location),
            self.dm.scene_perception(beat, refs, self.player_location, recent=recap))
        self._log("narration", self._scrub(narration), beat_title=beat["title"])
        self._perception = self._scrub(perception)
        for ev in beat.get("events", []):
            await self._fire_event(ev)

    async def _fire_event(self, ev: dict) -> None:
        text, mag = ev["text"], ev.get("magnitude")
        to = ev.get("to")
        targets = self.present if to in (None, "all") else [t for t in to if t in self.present]
        self._log("event", text)
        # each mind is its own engine — appraise everyone AT ONCE (sequential was the slowest
        # stretch of a beat, long enough to trip proxy timeouts on the tunnel)
        sals = await asyncio.gather(*(self.engines[s].remember(text, magnitude=mag, t=self.clock)
                                      for s in targets))
        if ev.get("react"):
            await self._provoke_reactions(targets, sals)

    async def _provoke_reactions(self, targets: list[str], sals: list) -> None:
        """Reaction recipe (game-owned): a witness whose salience clears the scenario's bar
        deliberates and may surface a `world_action`, which the game narrates. Shared by scripted
        events (`_fire_event`) AND witnessed player actions (`act`) so the room reacts to BOTH.
        Before this, only scripted events drew a reaction — a player drawing a weapon or shoving
        someone landed to total silence, which read as 'the characters don't understand actions'.
        Reactors deliberate in parallel; log order stays deterministic (targets order)."""
        threshold = self.scenario.get("deliberation", {}).get("react_threshold", 0.7)
        reactors = [s for s, sal in zip(targets, sals)
                    if sal is not None and sal >= threshold]
        if not reactors:
            return
        decs = await asyncio.gather(*(self.engines[s].deliberate(self._deliberation_situation(s), mode="free")
                                      for s in reactors))
        for slug, dec in zip(reactors, decs):
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

    # A private/introspective action is not a world event — nobody in the room perceives a thought.
    _INTROSPECTION = re.compile(
        r"\b(think|thought|wonder|ponder|reflect|consider|realis|realiz|myself|"
        r"recall|imagine|feel|felt|remember|remind)\b", re.IGNORECASE)

    def _witnessed(self, narration: str) -> str:
        """Reframe the player-facing 2nd-person narration into a 3rd-person WITNESSED account for
        the room's minds — to them, 'you' is themselves, so it must become 'the traveler'."""
        t = re.sub(r"\bYour\b", "The traveler's", narration)
        t = re.sub(r"\byour\b", "the traveler's", t)
        t = re.sub(r"\bYou\b", "The traveler", t)
        t = re.sub(r"\byou\b", "the traveler", t)
        return re.sub(r"\byourself\b", "themselves", t)

    def _personalize(self, witnessed: str, slug: str) -> str:
        """Rewrite a witnessed account into the SECOND PERSON for the one it happened TO — so the
        target of a slap remembers being slapped, not watching 'the young woman' get slapped. Only
        this character's OWN self-reference (handle / learned name) is swapped; everyone else stays
        third person. Returns the text UNCHANGED for a pure bystander (they aren't named in it),
        which is also how `act()` tells a participant from an onlooker."""
        forms = sorted({self.handles.get(slug) or "", self.known_names.get(slug) or "", self._name(slug)}
                       - {""}, key=len, reverse=True)
        out = witnessed
        for f in forms:
            if len(f) < 3:
                continue
            out = re.sub(rf"\b{re.escape(f)}'s\b", "your", out, flags=re.IGNORECASE)
            out = re.sub(rf"\b{re.escape(f)}\b", "you", out, flags=re.IGNORECASE)
        if out == witnessed:
            return witnessed
        # Recapitalize a 'you/your' that now opens a sentence.
        return re.sub(r"(^|[.!?]\s+)(you)", lambda m: m.group(1) + m.group(2).capitalize(), out)

    async def act(self, action: str) -> str:
        self._log("player_action", action)
        text = await self.dm.adjudicate(action, self._perception, self._refs(), self.player_location,
                                        recent=self._recap())
        # The DM appends `LOCATION: ...` ONLY when the action moved the player — apply it, strip it.
        m = re.search(r"(?im)^\s*LOCATION:\s*(.+?)\s*$", text)
        if m:
            self.player_location = m.group(1).strip()
            text = (text[:m.start()] + text[m.end():]).strip()
        # ...and `WITNESSED: ...` is a clean, past-tense account of what the room actually saw — the
        # memory the minds keep. We plant THIS, not the player-facing 2nd-person prose: crudely
        # regex-swapping "you"->"the traveler" on the narration produced garbled, ambiguous memories
        # ("You doesn't have time to react — her head snaps"), which the NPC then mis-read or forgot.
        witnessed_line = None
        m = re.search(r"(?im)^\s*WITNESSED:\s*(.+?)\s*$", text)
        if m:
            witnessed_line = m.group(1).strip()
            text = (text[:m.start()] + text[m.end():]).strip()
        # `TARGET: ...` names who the action was aimed at, so the one it happened to weighs it as a
        # participant AND has their disposition toward the player actually move. Parse + strip it.
        targets: list[str] = []
        m = re.search(r"(?im)^\s*TARGET:\s*(.+?)\s*$", text)
        if m:
            raw = m.group(1).strip()
            text = (text[:m.start()] + text[m.end():]).strip()
            if raw.lower() not in ("none", "no one", "-", ""):
                targets = [s for s in (self._resolve(r) for r in raw.split(",")) if s]
        text = self._scrub(text)
        self._log("narration", text)
        # WORLD -> MINDS: the people present WITNESS a physical player action, so plant it in their
        # memory via the engine's remember() seam — the SAME door _fire_event and the mind-server
        # /observe use. The engine stays ignorant of what the action IS; the game owns "who saw what".
        if not self._INTROSPECTION.search(action):
            # Prefer the DM's clean witnessed account; fall back to reframing the narration if absent.
            witnessed = witnessed_line or self._witnessed(text)
            # Each mind gets its OWN copy: the person it happened TO reads it in the second person
            # ("slapped you") and weighs it as a participant; onlookers get the third-person account.
            personal = [self._personalize(witnessed, s) for s in self.present]
            # A participant is whoever the DM named as a TARGET, or whoever the account put in the
            # scene by name (personalize changed their copy). They weigh it heavily; onlookers less.
            involved = [s in targets or p != witnessed for s, p in zip(self.present, personal)]
            # Whose disposition toward the player MOVES: the DM's explicit TARGETs — or, if it named
            # none, the SOLE person the clean account was actually written about (so a directed act
            # still costs/earns trust even when the TARGET line was dropped; an ambiguous multi-name
            # scene waits for an explicit TARGET rather than guess). The engine judges sign+size from
            # the account (a slap costs trust, a kindness earns it); onlookers just remember.
            caused = set(targets)
            if not caused:
                rewritten = [s for s, p in zip(self.present, personal) if p != witnessed]
                if len(rewritten) == 1:
                    caused = set(rewritten)
            sals = await asyncio.gather(*(
                self.engines[s].remember(
                    p, kind="player_event", actor="player",
                    player_role=("caused" if s in caused else None),
                    magnitude=(0.85 if inv else 0.5), t=self.clock)
                for s, p, inv in zip(self.present, personal, involved)))
            # ...and let anyone who found it salient enough REACT in the moment — the same recipe
            # scripted events use. Salience gates it, so mundane acts (counting coins, checking a
            # coat) stay quiet while a slap or a drawn blade draws a response.
            await self._provoke_reactions(self.present, sals)
        return text

    async def advance(self) -> bool:
        """Advance to the next beat: NPCs deliberate (metabolize the night), clock ticks, next beat
        is entered + its events fire. Returns False if there is no next beat (the story is over)."""
        if self.scenario.get("deliberation", {}).get("on_beat_advance"):
            # independent minds metabolize the night TOGETHER — this was four sequential
            # deliberations (1-3 model calls each) before the player saw anything
            await asyncio.gather(*(self.engines[s].deliberate(self._deliberation_situation(s), mode="free")
                                   for s in self.present))
        self.clock += self.hours_per_beat
        if self.beat_i + 1 >= len(self.scenario["beats"]):
            return False
        self.beat_i += 1
        await self._enter_beat()
        return True

    async def finish(self, outcome: str = "") -> None:
        for eng in self.engines.values():  # land in-flight background reflects before closing
            await eng.flush_reflection()
        if self.run_id:
            experiment_log.finalize_run(self.run_id, outcome or "(completed)", doc=self.log_doc)
        if self.ns_prefix:  # isolated run: its minds die with it — remove their memory files
            for eng in self.engines.values():
                ns = eng.character.memory_namespace
                for f in glob.glob(str(Path(get_settings().memory_dir) / f"{ns}.*")):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
                LongTermMemory.invalidate(ns)

    # ---- read-only snapshot for a play view / debugging ---------------------
    def snapshot(self) -> dict:
        return {"scenario": self.scenario["id"], "beat": self._beat()["id"],
                "beat_title": self._beat()["title"], "clock": self.clock,
                "present": [self.label(s) for s in self.present], "run_id": self.run_id}
