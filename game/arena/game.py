"""The embodied runtime — YOU in the arena (#30 treatment). The player is a body with a position;
you move / approach / act / talk, and everything resolves against the authoritative world (world.py).
NPCs perceive you (first-person, grounded) and respond/act through the UNCHANGED engine; the DM is
gone — the "scene" is a faithful VIEW of your percept, not invented prose. Time is real (a clock the
characters perceive), so "the night moved on" is felt. Sits beside the text game as the matched pair.

Playable methods: look / move / approach / act / talk / advance. The web + CLI call these."""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import yaml

from orchestrator.adapters.llm_anthropic import AnthropicLLM
from orchestrator.character_store import load_character
from orchestrator.config import ROOT_DIR, EngineCaps, get_settings
from orchestrator.context import RespondRequest, Situation
from orchestrator.engine import Engine
from orchestrator.memory.long_term import LongTermMemory

from .. import experiment_log
from .. import policy
from .actions import available, execute
from .perception import _proximity, perceive, render_player_view, to_situation
from .world import load_world

RUNS_DIR = ROOT_DIR / ".game_runs"  # repo-anchored, never cwd-relative
_PERF = policy.PERFORMANCE_RULES


class ArenaGame:
    def __init__(self, scenario_path: str, map_path: str, *, condition: str = "TREAT-EMBODIED",
                 reply_model: str | None = None, reset: bool = True, log_doc=None):
        self.scenario = yaml.safe_load(Path(scenario_path).read_text(encoding="utf-8"))
        self.world = load_world(map_path)
        self.condition = condition
        self.reply_model = reply_model
        self.log_doc = log_doc or experiment_log.DOC_PATH
        self.cast = [c["slug"] for c in self.scenario["cast"]]
        self.handles = {c["slug"]: (c.get("handle") or "someone").strip() for c in self.scenario["cast"]}
        self.here_because = {c["slug"]: (c.get("here_because") or "").strip() for c in self.scenario["cast"]}
        self.known_names: dict[str, str] = {}
        # The player's in-fiction handle is scenario data, not engine code (any scenario can cast
        # the player as someone else walking into a different room).
        self.player_handle = (self.scenario.get("player_handle")
                              or "the stranger just in from the storm").strip()
        # Affect/agency ON per-engine (never by mutating global settings; arch review theme B).
        # background_reflection: this is a long-lived server surface — don't tax every reply with
        # the post-turn affect calls; finish() flushes them. The scenario's authored clock window
        # (e.g. "a beat stays fresh 6 hours") must actually reach the engine, not sit unread in
        # the YAML while the engine default silently applies.
        over = dict(relationship_state=True, reflection_enabled=True, intent_state=True,
                    background_reflection=True)
        window = (self.scenario.get("clock") or {}).get("recent_happenings_window")
        if window:
            over["recent_happenings_window"] = float(window)
        caps = EngineCaps.from_settings(get_settings(), **over)
        if reset:
            mem_dir = Path(get_settings().memory_dir)
            for slug in self.cast:
                ns = load_character(slug).memory_namespace
                for f in glob.glob(str(mem_dir / f"{ns}.*")):
                    os.remove(f)
                LongTermMemory.invalidate(ns)  # drop any shared cache over the deleted files
        self.engines = {slug: Engine(load_character(slug), AnthropicLLM(model=reply_model), caps=caps)
                        for slug in self.cast}
        self.clock = 0.0
        self.history: list[dict] = []
        self.run_id: str | None = None
        self.transcript_path: Path | None = None

    # ---- references (strangers: appearance handle until a name is spoken) ----
    def _name(self, slug: str) -> str:
        import re
        return re.sub(r"\s*\([^)]*\)\s*$", "", self.engines[slug].character.name).strip()

    def _ref(self, eid: str) -> str:
        if eid == "player":
            return self.player_handle
        return self.known_names.get(eid) or self.handles.get(eid) or eid

    def _label(self, eid: str) -> str:
        r = self._ref(eid) if eid != "player" else "you"
        return r[:1].upper() + r[1:]

    _split_quotes = staticmethod(policy.split_quotes)

    def _name_forms(self, slug: str) -> list[str]:
        """The name tokens that count as a leak for this character (full name + words >=3 chars),
        longest first so 'Della Fenwick' rewrites before 'Della'."""
        import re
        raw = re.sub(r"\s*\([^)]*\)\s*$", "", self.engines[slug].character.name)
        raw = re.sub(r"\s+", " ", raw.replace("'", " ").replace('"', " ")).strip()
        return sorted({raw, *re.findall(r"[A-Za-z]{3,}", raw)}, key=len, reverse=True)

    def _scrub_names(self, text: str) -> str:
        """Names may emerge ONLY as spoken introductions. In the NARRATION segments (outside quoted
        speech — stage directions like 'Della nods'), replace any UNLEARNED character's name-forms
        with their handle; quoted speech is left untouched, so a character saying their own name
        aloud still introduces them (and _maybe_learn_name then makes it official)."""
        import re
        if not text:
            return text
        segs = self._split_quotes(text)
        for slug in self.cast:
            if slug in self.known_names:
                continue
            handle = self.handles.get(slug) or "someone"
            for i in range(0, len(segs), 2):  # narration segments only
                for f in self._name_forms(slug):
                    # case-SENSITIVE: names in prose are capitalized; matching 'pockets' the verb
                    # because of Edwin "Pockets" Hale would mangle ordinary sentences.
                    segs[i] = re.sub(rf"\b{re.escape(f)}\b", handle, segs[i])
                # a "First Last" leak becomes "handle handle" — collapse
                segs[i] = re.sub(rf"\b({re.escape(handle)})(\s+\1\b)+", r"\1", segs[i],
                                 flags=re.IGNORECASE)
        return "".join(segs)

    def _maybe_learn_name(self, slug: str, text: str) -> None:
        """Learn a name ONLY from QUOTED speech — an actual spoken introduction ('Name's Della'),
        never a narration slip (those are scrubbed before this runs). The what-counts rules live
        in game/policy.py (shared with the Unity bridge)."""
        if slug in self.known_names:
            return
        name = policy.spoken_name(self.engines[slug].character.name, text)
        if name:
            self.known_names[slug] = name

    def _resolve(self, ref: str) -> str | None:
        ref = (ref or "").strip().lower()
        for slug in self.cast:
            if ref and (ref == slug or ref in self._name(slug).lower()
                        or ref in self.handles.get(slug, "").lower()
                        or ref in (self.known_names.get(slug) or "").lower()):
                return slug
        return None

    # ---- perception / situation ----
    def _situation_for(self, slug: str, *, elapsed=None) -> Situation:
        p = perceive(self.world, slug, clock=self.clock, elapsed=elapsed, ref_of=self._ref)
        sit = to_situation(p)
        sit.extra["Performance"] = _PERF
        if self.here_because.get(slug):
            sit.extra["Why you're here tonight"] = self.here_because[slug]
        return sit

    def _log(self, kind: str, text: str, **meta) -> dict:
        rec = {"clock": self.clock, "kind": kind, "text": text, **meta}
        self.history.append(rec)
        if self.transcript_path:
            with open(self.transcript_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    # ---- lifecycle ----
    def begin(self) -> str:
        RUNS_DIR.mkdir(exist_ok=True)
        book = get_settings().salience_model
        self.run_id = experiment_log.start_run(
            condition=self.condition, scenario=self.scenario["id"], characters=self.cast,
            models=f"reply={self.reply_model or 'default'} book={book}", doc=self.log_doc)
        self.transcript_path = RUNS_DIR / f"{self.run_id}.jsonl"
        experiment_log.update_run(self.run_id, transcript=str(self.transcript_path), doc=self.log_doc)
        self._log("scene", self.look())
        return self.run_id

    # ---- read-only ----
    def look(self) -> str:
        return render_player_view(perceive(self.world, "player", clock=self.clock, ref_of=self._ref))

    def player_actions(self) -> list[str]:
        return [a.label for a in available(self.world, "player", ref_of=self._ref)]

    def present(self) -> list[dict]:
        return [{"slug": s, "ref": self._label(s), "region": self.world.region_of(self.world.entities[s].pos)}
                for s in self.cast]

    def snapshot(self) -> dict:
        return {"clock": self.clock, "where": self.world.region_of(self.world.entities["player"].pos),
                "present": self.present(), "run_id": self.run_id}

    def grid(self) -> dict:
        """Structured map for a renderer to draw: dimensions, named regions (rects), and every body's
        cell + how they're currently referred to (you / handle / name)."""
        return {"w": self.world.w, "h": self.world.h,
                "regions": [{"name": r.name, "rect": list(r.rect)} for r in self.world.regions],
                "entities": [{"ref": ("you" if e.kind == "player" else self._label(s)),
                              "x": e.pos[0], "y": e.pos[1], "you": e.kind == "player",
                              "stance": e.stance}
                             for s, e in self.world.entities.items()]}

    # ---- in-the-moment reactions (the contract's react RECIPE, wired to player acts) ----
    # Game policy, not engine policy: how salient an observed act must be — by the NPC's OWN
    # appraisal — before it interrupts what they're doing, and the higher bar where the
    # reaction earns words instead of just a move. Mundane acts score low and pass in silence;
    # reacting to everything would be as dead as reacting to nothing.
    # Calibrated live (2026-07-01): vigilant characters RECALL nearly everything a stranger does
    # (~0.72 floor — character-true; recall is what salience measures), so the interrupt bar sits
    # above that floor: crossing the room / ordering a drink pass in silence; being watched spikes
    # only the one it's aimed at (Corvin 0.82); barring the door sets the whole room off (0.72-0.93).
    REACT_SALIENCE = policy.REACT_SALIENCE
    SPEAK_SALIENCE = policy.SPEAK_SALIENCE
    # The game's coarse OBJECTIVE scale per act kind (the #25 magnitude hint): without it the
    # appraiser rated even crossing the room at 0.7-0.8 for three of four NPCs. The character
    # still realizes their OWN salience around the hint — a low-magnitude move can still spike
    # for the one it threatens.
    OBJ_MAGNITUDE = policy.OBJ_MAGNITUDE

    _as_observed = staticmethod(policy.as_observed)

    async def _react_to_player(self, conseq: str, *, magnitude: float = 0.1) -> None:
        """Run the reaction recipe (docs/engine-game-contract.md) for everyone who saw the
        player's act: remember → the NPC appraises the moment's salience for THEMSELVES →
        our thresholds decide → a grounded action beat, or words when it truly lands. The
        world answers 'who saw it' for free (proximity is in the observation, so the same act
        weighs differently right beside you vs across the room)."""
        import asyncio
        seen = self._as_observed(conseq)
        ppos = self.world.entities["player"].pos

        async def appraise(slug: str):
            d = self.world.dist(self.world.entities[slug].pos, ppos)
            observed = f"{self._ref('player')} ({_proximity(d)}) {seen}"
            sal = await self.engines[slug].remember(observed, kind="player_event", t=self.clock,
                                                    magnitude=magnitude)
            return slug, observed, sal or 0.0

        results = await asyncio.gather(*(appraise(s) for s in self.cast))
        speakers = [(s, o) for s, o, sal in results if sal >= self.SPEAK_SALIENCE]
        movers = [(s, o) for s, o, sal in results if self.REACT_SALIENCE <= sal < self.SPEAK_SALIENCE]

        # The beats run CONCURRENTLY (independent minds thinking at once — serial awaits stacked
        # up to 4 LLM round-trips of player-visible latency); everything they decided FROM is the
        # same world snapshot, and world changes apply afterwards, in cast order, deterministically.
        async def speech_beat(slug: str, observed: str):
            reply = await self.engines[slug].respond(RespondRequest(
                event=f"Right now, before your eyes: {observed}. React as feels true to you.",
                situation=self._situation_for(slug)))
            return slug, observed, self._scrub_names(reply)

        async def action_beat(slug: str, observed: str):
            acts = available(self.world, slug, ref_of=self._ref)
            p = perceive(self.world, slug, clock=self.clock, ref_of=self._ref)
            choice = await self.engines[slug].choose_action(
                f"{render_player_view(p)}\nJust now: {observed}", [a.label for a in acts])
            return slug, acts, choice

        spoken, acted = await asyncio.gather(
            asyncio.gather(*(speech_beat(s, o) for s, o in speakers)),
            asyncio.gather(*(action_beat(s, o) for s, o in movers)))
        for slug, observed, reply in spoken:
            self._log("dialogue", reply, slug=slug, who=self._label(slug), reacted_to=observed)
            self._maybe_learn_name(slug, reply)
        for slug, acts, choice in acted:
            if choice.get("action"):
                execute(self.world, slug, choice["action"], acts)
                self._log("npc_act", choice["action"], slug=slug, who=self._label(slug),
                          reason=self._scrub_names(choice.get("reason", "")))
                await self._remember_own_act(slug, choice)

    # ---- player moves ----
    async def move(self, region: str) -> str:
        if not self.world.move_to_region("player", region):
            return f"(there's no {region} to cross to)"
        self._log("player_move", f"you cross to {region}")
        await self._react_to_player(f"crosses to {region}", magnitude=self.OBJ_MAGNITUDE["move"])
        scene = self.look()
        self._log("scene", scene)
        return scene

    async def act(self, label: str) -> str:
        acts = available(self.world, "player", ref_of=self._ref)
        chosen = next((a for a in acts if a.label == label), None)
        conseq = execute(self.world, "player", label, acts)
        if not conseq or not chosen:
            return "(you can't do that here)"  # not logged — the API surfaces it as an error
        # A movement act reads as the act you chose ("you cross to the bar" — the consequence
        # phrase is third-person and glued to "you" it read broken), and arriving somewhere new
        # deserves a fresh scene, exactly like move().
        moved = chosen.kind in ("move", "approach")
        self._log("player_act", f"you {label}" if moved else f"you {conseq}")
        # holding still isn't an event; anything else, the room gets its chance to notice
        if chosen.kind != "wait":
            await self._react_to_player(conseq, magnitude=self.OBJ_MAGNITUDE.get(chosen.kind, 0.1))
        if moved:
            self._log("scene", self.look())
        return f"you {label}" if moved else f"you {conseq}"

    async def talk(self, target_ref: str, line: str) -> str:
        slug = self._resolve(target_ref)
        if not slug:
            return f"(no one here answers to '{target_ref}')"
        self._log("player", line, to=slug)
        reply = await self.engines[slug].respond(
            RespondRequest(player_input=line, situation=self._situation_for(slug)))
        # Scrub narration-leaked names to handles FIRST ("Della nods" -> "the ferrywoman nods"),
        # THEN learn — so only a name surviving in QUOTED speech (a real introduction) flips the label.
        reply = self._scrub_names(reply)
        self._log("dialogue", reply, slug=slug, who=self._label(slug))
        self._maybe_learn_name(slug, reply)
        return reply

    # ---- the world turns (time passes; NPCs perceive + act) ----
    async def advance(self, hours: float = 2.0) -> list[dict]:
        import asyncio
        before = len(self.history)
        self.clock += hours
        self._log("time", f"— {hours:g} hours pass —")
        # Everyone perceives the SAME pre-advance world (a true simultaneous beat), chooses
        # concurrently (serial awaits stacked 4 LLM round-trips of dead time), then the choices
        # apply in cast order. The elapsed gap rides IN the situation text — perceive() carries
        # it, but render_player_view doesn't show it, so without the line nobody actually FELT
        # the hours pass ("all feel the gap" was a comment, not a behavior).
        snaps = []
        for slug in self.cast:
            p = perceive(self.world, slug, clock=self.clock, elapsed=hours, ref_of=self._ref)
            acts = available(self.world, slug, ref_of=self._ref)
            snaps.append((slug, acts, f"{render_player_view(p)}\nTime just passed: {hours:g} hours."))
        # Grounded choice: the engine folds in evolved goals/intent/feelings/beliefs (#30 review D).
        choices = await asyncio.gather(*(self.engines[slug].choose_action(sit, [a.label for a in acts])
                                         for slug, acts, sit in snaps))
        for (slug, acts, _), choice in zip(snaps, choices):
            if choice.get("action"):
                execute(self.world, slug, choice["action"], acts)
                self._log("npc_act", choice["action"], slug=slug, who=self._label(slug),
                          reason=self._scrub_names(choice.get("reason", "")))
                await self._remember_own_act(slug, choice)
        self._log("scene", self.look())
        return self.history[before:]

    async def _remember_own_act(self, slug: str, choice: dict) -> None:
        """The body just did the chosen thing — write it into the MIND as their own act, or the
        next conversation gets confabulation ('why did you come over?'). Pinned salience puts it
        in the #30 working-memory foreground; the (chose...) prefix renders it first-person."""
        act = choice["action"]
        if act.startswith("stay where"):
            return
        reason = (choice.get("reason") or "").strip()
        text = f"(chose, of their own will) {act}" + (f" — {reason}" if reason else "")
        await self.engines[slug].remember(text, kind="decision", importance=0.65, t=self.clock)

    async def finish(self, outcome: str = "") -> None:
        for eng in self.engines.values():  # land in-flight background reflects before closing the book
            await eng.flush_reflection()
        if self.run_id:
            experiment_log.finalize_run(self.run_id, outcome or "(embodied session)", doc=self.log_doc)
