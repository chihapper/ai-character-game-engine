"""Engine-integration layer — one `Engine` per named NPC, driven ONLY through the documented seam.

The game feeds the engine and enacts what it returns; it never models minds (guardrails #1-#6).
Depth faculties are turned on via a per-`Engine` CAPS OVERRIDE (the chosen approach) so the engine
core stays neutral and the #30 control arm can still switch a faculty off explicitly. Named NPCs
are RESKINNED from the tuned cast: clone the psychology, reskin the identity, give a FRESH
`memory_namespace` so the mind starts empty and meets the player in-world.
"""
from __future__ import annotations

import dataclasses

from orchestrator.adapters.llm_anthropic import AnthropicLLM
from orchestrator.character_store import Character, load_character
from orchestrator.config import EngineCaps, get_settings
from orchestrator.context import RespondRequest, Situation
from orchestrator.engine import Engine

# Every depth faculty ON, per-Engine (owner's choice). Filtered to real EngineCaps fields at
# build time so an unknown/renamed flag can't crash construction.
_DESIRED_DEPTH = dict(
    relationship_state=True, relationship_time_decay=True, reflection_enabled=True,
    background_reflection=True, intent_state=True, salience_scoring=True,
    commitment_detection=True, contradiction_detection=True, recent_happenings=True,
    arena_query=True, reinforce_on_recall=True,
)


def full_depth_caps(**extra) -> EngineCaps:
    """`EngineCaps` with every faculty ON — a fresh reskinned NPC runs at full depth out of the box.
    Pass `recent_happenings_window=<clock-unit>` (or any other cap) via `extra` to tune to the
    game's clock unit."""
    valid = {f.name for f in dataclasses.fields(EngineCaps)}
    over = {k: v for k, v in {**_DESIRED_DEPTH, **extra}.items() if k in valid}
    return EngineCaps.from_settings(get_settings(), **over)


def reskin(base_slug: str, *, slug: str, name: str, memory_namespace: str | None = None,
           **identity) -> Character:
    """Clone a base character's tuned PSYCHOLOGY and reskin the IDENTITY into a new named NPC with a
    FRESH `memory_namespace`. Pass identity overrides (`role`, `concept`, `backstory`, `goals`,
    `secrets`, `greeting`, `voice_id`, `handle`, `game_data`, ...). The psychology (temperament,
    speech style, disposition, boundaries, sample lines) carries over unless explicitly overridden —
    that's the point: identical events should evolve a Corvin-derived and a Bri-derived NPC
    differently."""
    base = load_character(base_slug)
    fields = dict(slug=slug, name=name, memory_namespace=memory_namespace or slug,
                  system_prompt="")            # clear so build_prompt recompiles from the reskinned fields
    fields.update(identity)
    return dataclasses.replace(base, **fields)


class Minds:
    """Owns one `Engine` per named NPC + thin seam wrappers. The GAME builds a `Situation` from the
    world (it owns the clock + who's present); the ENGINE owns everything about the mind. Reactions
    are composed game-side (remember -> your salience threshold -> deliberate -> enact) — there is
    no `engine.react()`."""

    def __init__(self, characters: dict[str, Character], *, reply_model: str | None = None,
                 caps: EngineCaps | None = None) -> None:
        self.caps = caps or full_depth_caps()
        self.characters = characters
        self.engines: dict[str, Engine] = {
            slug: Engine(char, AnthropicLLM(model=reply_model), caps=self.caps)
            for slug, char in characters.items()
        }

    def situation(self, *, clock: float, location: str = "", present: list[str] | None = None,
                  recent_events: list[str] | None = None, game_time: str = "",
                  extra: dict | None = None) -> Situation:
        """Build the per-turn `Situation` the engine reads. Always carries the numeric `clock`
        (temporal decay); `game_time` is a display string the engine never parses."""
        return Situation(clock=clock, location=location, present=present or [],
                         recent_events=recent_events or [], game_time=game_time, extra=extra or {})

    async def talk(self, slug: str, player_input: str, situation: Situation) -> str:
        """An NPC's spoken reply (voiced by Hume downstream). The engine owns the words AND the
        inner change the exchange causes."""
        return await self.engines[slug].respond(RespondRequest(player_input=player_input, situation=situation))

    async def act(self, slug: str, situation: Situation, options: list[str]) -> dict:
        """On-map / combat behavior: the engine picks ONE of the afforded `options`, grounded in
        who it has become. Returns {action, reason, expression, face}; the GAME enacts the choice."""
        return await self.engines[slug].choose_action(situation, options)

    async def deliberate(self, slug: str, situation: Situation, *, mode: str = "free") -> dict:
        """Between-scene metabolizing (#20): the NPC may change on its own and return a
        `world_action` for the game to enact or narrate."""
        return await self.engines[slug].deliberate(situation, mode=mode)

    async def remember(self, slug: str, fact: str, **kw) -> float | None:
        """The world->mind seam: feed an attributable world event into a mind (pass `player_role`,
        `actor`, `magnitude`, `t=clock`). Returns the character's appraised salience — the game's
        gate for whether the event is worth a reaction."""
        return await self.engines[slug].remember(fact, **kw)

    async def flush(self) -> None:
        """Land any in-flight background reflections (call before save/exit)."""
        for eng in self.engines.values():
            if hasattr(eng, "flush_reflection"):
                await eng.flush_reflection()
