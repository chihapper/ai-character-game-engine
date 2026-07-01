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
from orchestrator.config import ROOT_DIR, get_settings
from orchestrator.context import RespondRequest, Situation
from orchestrator.engine import Engine

from .. import experiment_log
from .actions import available, execute
from .perception import perceive, render_player_view, to_situation
from .world import load_world

RUNS_DIR = ROOT_DIR / ".game_runs"  # repo-anchored, never cwd-relative
_PERF = ("Speak your words in the first person, in quotes. Write your OWN actions in the third person "
         "using a PRONOUN (he/she/they) — e.g. 'she brushes the rain off' — never the second person and "
         "NEVER your own name. Never narrate the player's actions, body, or feelings.")


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
        s = get_settings()
        s.relationship_state = True
        s.reflection_enabled = True
        s.intent_state = True
        if reset:
            mem_dir = Path(get_settings().memory_dir)
            for slug in self.cast:
                for f in glob.glob(str(mem_dir / f"{load_character(slug).memory_namespace}.*")):
                    os.remove(f)
        self.engines = {slug: Engine(load_character(slug), AnthropicLLM(model=reply_model)) for slug in self.cast}
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
            return "the stranger just in from the storm"
        return self.known_names.get(eid) or self.handles.get(eid) or eid

    def _label(self, eid: str) -> str:
        r = self._ref(eid) if eid != "player" else "you"
        return r[:1].upper() + r[1:]

    def _maybe_learn_name(self, slug: str, text: str) -> None:
        import re
        if slug in self.known_names:
            return
        raw = re.sub(r"\s*\([^)]*\)\s*$", "", self.engines[slug].character.name)
        for c in re.findall(r"[A-Za-z]{2,}", raw.replace("'", " ").replace('"', " ")):
            if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE):
                self.known_names[slug] = c
                return

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

    # ---- player moves ----
    def move(self, region: str) -> str:
        if not self.world.move_to_region("player", region):
            return f"(there's no {region} to cross to)"
        self._log("player_move", f"you cross to {region}")
        scene = self.look()
        self._log("scene", scene)
        return scene

    def act(self, label: str) -> str:
        acts = available(self.world, "player", ref_of=self._ref)
        conseq = execute(self.world, "player", label, acts)
        text = f"you {conseq}" if conseq else "(you can't do that here)"
        self._log("player_act", text)
        return text

    async def talk(self, target_ref: str, line: str) -> str:
        slug = self._resolve(target_ref)
        if not slug:
            return f"(no one here answers to '{target_ref}')"
        self._log("player", line, to=slug)
        reply = await self.engines[slug].respond(
            RespondRequest(player_input=line, situation=self._situation_for(slug)))
        self._log("dialogue", reply, slug=slug, who=self._label(slug))
        self._maybe_learn_name(slug, reply)
        return reply

    # ---- the world turns (time passes; NPCs perceive + act) ----
    async def advance(self, hours: float = 2.0) -> list[dict]:
        before = len(self.history)
        self.clock += hours
        self._log("time", f"— {hours:g} hours pass —")
        for slug in self.cast:
            p = perceive(self.world, slug, clock=self.clock, elapsed=hours, ref_of=self._ref)  # all feel the gap
            acts = available(self.world, slug, ref_of=self._ref)
            # Grounded choice: the engine folds in evolved goals/intent/feelings/beliefs (#30 review D).
            choice = await self.engines[slug].choose_action(render_player_view(p),
                                                            [a.label for a in acts])
            if choice.get("action"):
                execute(self.world, slug, choice["action"], acts)
                self._log("npc_act", choice["action"], slug=slug, who=self._label(slug), reason=choice.get("reason", ""))
        self._log("scene", self.look())
        return self.history[before:]

    async def finish(self, outcome: str = "") -> None:
        if self.run_id:
            experiment_log.finalize_run(self.run_id, outcome or "(embodied session)", doc=self.log_doc)
