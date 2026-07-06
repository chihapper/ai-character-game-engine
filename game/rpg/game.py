"""RpgGame — the concrete `GameSession` that ties the WORLD (`GameState`), the MINDS (`Minds`),
and the RULES (`D20Rules`) together behind one boundary. Free-flow exploration by default;
turn-based combat on encounter. Renderer-agnostic: consumes `PlayerAction`s, emits DATA events.

This is the game-core loop the spec's step 7 describes. Reactions stay a game-composed recipe
(remember -> salience -> deliberate -> enact); the DM narrator (step 5) and full combat resolution
layer on top of this without changing the seam.
"""
from __future__ import annotations

import asyncio

from game import policy

from .content import build_first_slice
from .minds import Minds
from .rules import D20Rules
from .session import (
    CombatEvent,
    DialogueEvent,
    GameEvent,
    GameSession,
    ModeChangedEvent,
    NarrationEvent,
    PlayerAction,
    StateChangedEvent,
)
from .state import EntityView, GameState, Mode, NpcPlacement, StateSnapshot

WORLD_FRAME = ("You are deep in the Sunken Vault — a flooded, ancient dungeon of black stone, old "
               "wards, and worse things in the dark. Torchlight, dripping water, no way out but "
               "through. This is a world of blades and lantern-light, not of any modern place.")
_REACT_THRESHOLD = 0.7   # game-owned salience bar for turning a witnessed event into a reaction


class RpgGame(GameSession):
    def __init__(self, state: GameState, minds: Minds, rules: D20Rules) -> None:
        self.state = state
        self.minds = minds
        self.rules = rules
        self._events: asyncio.Queue[GameEvent] = asyncio.Queue()

    @classmethod
    def new(cls, *, seed: int = 1337, reply_model: str | None = "claude-haiku-4-5") -> "RpgGame":
        state, chars = build_first_slice(seed=seed)
        return cls(state, Minds(chars, reply_model=reply_model), D20Rules(seed=seed))

    # ---- events (to the view) ----
    def _emit(self, ev: GameEvent) -> None:
        self._events.put_nowait(ev)

    async def events(self):
        while True:
            yield await self._events.get()

    # ---- state snapshot (mechanical only — no mind) ----
    def get_state(self) -> StateSnapshot:
        s = self.state
        ents: list[EntityView] = []
        for n in s.npcs:
            ents.append(EntityView(id=n.slug, name=n.name, pos=n.pos, kind="npc"))
        for f in s.followers:
            ents.append(EntityView(id=f.id, name=f.name, pos=f.pos, kind="follower", hp=f.hp, max_hp=f.max_hp))
        # Enemies are visible on the map (no fog-of-war yet); HP stays hidden unless the player
        # toggles it in combat (guardrail #5). `triggered` governs combat ENTRY, not sight.
        show_hp = bool(s.combat and s.combat.show_enemy_hp)
        for e in s.encounters:
            for en in e.enemies:
                if en.alive:
                    ents.append(EntityView(id=en.id, name=en.name, pos=en.pos, kind="enemy",
                                           hp=en.hp if show_hp else None,
                                           max_hp=en.max_hp if show_hp else None))
        return StateSnapshot(
            mode=s.mode, clock=s.clock.value, player=s.player,
            map_width=s.world_map.width, map_height=s.world_map.height, tiles=s.world_map.tiles,
            entities=ents, combat_order=(s.combat.order if s.combat else []),
            combat_turn=(s.combat.current() if s.combat else None), show_enemy_hp=show_hp)

    # ---- world helpers ----
    def _npc_at(self, pos) -> NpcPlacement | None:
        return next((n for n in self.state.npcs if n.pos and tuple(n.pos) == tuple(pos)), None)

    def _dist(self, a, b) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _present_near(self, slug: str | None = None, radius: int = 6) -> list[str]:
        """NPC slugs within `radius` of the player (who can perceive/witness the scene)."""
        px, py = self.state.player.pos
        return [n.slug for n in self.state.npcs
                if n.slug != slug and n.pos and self._dist(n.pos, (px, py)) <= radius]

    def _situation(self, for_slug: str, *, recent: list[str] | None = None):
        """Build the perceiving NPC's `Situation` from the world — location + who's present + the
        numeric clock + light grounding. The engine owns everything about the mind."""
        others = [self.state.player.name] + [n.name for n in self.state.npcs
                                             if n.slug != for_slug and n.pos
                                             and self._dist(n.pos, self.state.player.pos) <= 6]
        extra = {"The world you live in": WORLD_FRAME, "Performance": policy.PERFORMANCE_RULES}
        return self.minds.situation(clock=self.state.clock.value, location="a chamber of the Sunken Vault",
                                    present=others, recent_events=recent or [], game_time="deep underground",
                                    extra=extra)

    # ---- action dispatch ----
    async def submit_action(self, action: PlayerAction) -> None:
        if action.kind == "toggle_enemy_hp":
            if self.state.combat:
                self.state.combat.show_enemy_hp = not self.state.combat.show_enemy_hp
        elif self.state.mode == Mode.combat:
            await self._combat_action(action)
        else:
            await self._explore_action(action)
        self._emit(StateChangedEvent())

    # ---- exploration (free-flow) ----
    async def _explore_action(self, action: PlayerAction) -> None:
        if action.kind == "move":
            self._move_player(action.dx, action.dy)
        elif action.kind == "talk":
            await self._talk(action)
        elif action.kind == "wait":
            self.state.clock.advance(0.1)

    def _move_player(self, dx: int, dy: int) -> None:
        s = self.state
        px, py = s.player.pos
        nx, ny = px + dx, py + dy
        if not s.world_map.walkable(nx, ny) or self._npc_at((nx, ny)):
            return
        s.player.pos = (nx, ny)
        s.clock.advance(0.05)               # exploration narrative time (game owns the clock)
        self._maybe_trigger_encounter()

    def _maybe_trigger_encounter(self) -> None:
        s = self.state
        for e in s.encounters:
            if e.triggered or not e.trigger_pos:
                continue
            if self._dist(s.player.pos, e.trigger_pos) <= 2:
                self._enter_combat(e)
                return

    async def _talk(self, action: PlayerAction) -> None:
        s = self.state
        target = None
        if action.target_id:
            target = next((n for n in s.npcs if n.slug == action.target_id or n.name.lower() == action.target_id.lower()), None)
        if target is None:                  # nearest NPC in speaking range
            near = [n for n in s.npcs if n.pos and self._dist(n.pos, s.player.pos) <= 2]
            target = min(near, key=lambda n: self._dist(n.pos, s.player.pos), default=None)
        if target is None:
            self._emit(NarrationEvent(text="There is no one close enough to speak to."))
            return
        reply = await self.minds.talk(target.slug, action.text, self._situation(target.slug))
        self._emit(DialogueEvent(npc=target.name, slug=target.slug, text=reply))
        s.campaign_log.add(s.clock.value, f'The traveler said to {target.name}: "{action.text}"', tags=["talk", target.slug])

    async def remember_player_deed(self, fact: str, *, targets: list[str], player_role: str = "caused",
                                   magnitude: float = 0.6) -> None:
        """World->mind seam for a consequential PLAYER deed toward named NPCs (free them, rob them,
        share loot). Plants it in each target's mind (attributed to the player) so their disposition
        and future choices evolve — then composes the reaction recipe game-side."""
        sals = await asyncio.gather(*(
            self.minds.remember(slug, fact, kind="player_event", actor="player",
                                player_role=player_role, magnitude=magnitude, t=self.state.clock.value)
            for slug in targets))
        self.state.campaign_log.add(self.state.clock.value, fact, tags=["deed", *targets])
        for slug, sal in zip(targets, sals):
            if sal is not None and sal >= _REACT_THRESHOLD:
                dec = await self.minds.deliberate(slug, self._situation(slug))
                if dec.get("changed") and dec.get("world_action"):
                    name = next((n.name for n in self.state.npcs if n.slug == slug), slug)
                    self._emit(NarrationEvent(text=f"{name} {dec['world_action']}"))

    # ---- combat (turn-based) — entry + scaffold; full resolution is the next step ----
    def _enter_combat(self, encounter) -> None:
        from .state import CombatState
        encounter.triggered = True
        combatants = [self.state.player] + [e for e in encounter.enemies if e.alive]
        order = self.rules.roll_initiative(combatants)
        self.state.combat = CombatState(order=order, round=1, turn_index=0)
        self.state.mode = Mode.combat
        self._emit(ModeChangedEvent(mode=Mode.combat))
        self._emit(CombatEvent(text="Steel rings in the dark — the goblins are on you!",
                               data={"order": order}))

    async def _combat_action(self, action: PlayerAction) -> None:
        # Full turn-based resolution (player attack, enemy AI, named-NPC choose_action) lands next.
        self._emit(CombatEvent(text="(combat resolution is being built — next step)"))
