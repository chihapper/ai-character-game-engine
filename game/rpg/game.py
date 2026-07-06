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
from .dm import DM
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
    def __init__(self, state: GameState, minds: Minds, rules: D20Rules, dm: DM) -> None:
        self.state = state
        self.minds = minds
        self.rules = rules
        self.dm = dm
        self._events: asyncio.Queue[GameEvent] = asyncio.Queue()

    @classmethod
    def new(cls, *, seed: int = 1337, reply_model: str | None = "claude-haiku-4-5",
            dm_model: str | None = "claude-haiku-4-5") -> "RpgGame":
        state, chars = build_first_slice(seed=seed)
        rules = D20Rules(seed=seed)
        return cls(state, Minds(chars, reply_model=reply_model), rules, DM(rules, model=dm_model))

    async def begin(self) -> None:
        """Open the game with a DM scene — the world speaks first."""
        self._emit(NarrationEvent(text=await self.dm.narrate_scene(self._scene_text())))

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
        for d in s.doors:
            if d.locked:
                ents.append(EntityView(id=d.id, name="Door", pos=d.pos, kind="door"))
        objective = next((q.title for q in s.quests if q.state in ("open", "active")), "")
        return StateSnapshot(
            mode=s.mode, clock=s.clock.value, player=s.player, objective=objective,
            inventory=[it.name for it in s.player.inventory],
            map_width=s.world_map.width, map_height=s.world_map.height, tiles=s.world_map.tiles,
            entities=ents, combat_order=(s.combat.order if s.combat else []),
            # This loop resolves player -> all allies -> all enemies per action rather than stepping a
            # single initiative cursor, so there is no one "current" combatant to report (turn_index
            # is not advanced). Leave combat_turn None instead of always claiming order[0].
            combat_turn=None, show_enemy_hp=show_hp)

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
        if self.state.flags.get("game_over"):
            return                           # terminal state — the only way on is a fresh game
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
        elif action.kind == "recruit":
            await self._recruit(action)
        elif action.kind == "do":
            await self._do(action.text)
        elif action.kind == "look":
            self._emit(NarrationEvent(text=await self.dm.narrate_scene(self._scene_text())))
        elif action.kind == "wait":
            self.state.clock.advance(0.1)

    def _scene_text(self) -> str:
        """The world-state the DM narrates FROM — where the player is, who's near, recent history."""
        s = self.state
        near = [n.name for n in s.npcs if n.pos and self._dist(n.pos, s.player.pos) <= 5]
        party = [f.name for f in s.followers if f.alive]
        parts = ["The player stands deep in the Sunken Vault — black stone, standing water, old wards, "
                 "torchlight the only light."]
        if near:
            parts.append("Others nearby: " + ", ".join(near) + ".")
        if party:
            parts.append("Traveling with the player: " + ", ".join(party) + ".")
        recent = [e.text for e in s.campaign_log.recent(4)]
        if recent:
            parts.append("Recently: " + " ".join(recent))
        return " ".join(parts)

    async def _do(self, action_text: str) -> None:
        """A free-form player action — the DM adjudicates (rules core is the authority) and narrates."""
        if not (action_text or "").strip():
            return
        narration = await self.dm.adjudicate(action_text, scene=self._scene_text(),
                                             player=self.state.player, grant_item=self._grant_item)
        self._emit(NarrationEvent(text=narration))
        self.state.campaign_log.add(self.state.clock.value, narration, tags=["action"])
        self.state.clock.advance(0.1)

    def _move_player(self, dx: int, dy: int) -> None:
        s = self.state
        nx, ny = s.player.pos[0] + dx, s.player.pos[1] + dy
        door = next((d for d in s.doors if d.locked and tuple(d.pos) == (nx, ny)), None)
        if door:
            self._try_open_door(door)       # walking into a locked door = try to open it
            return
        if not s.world_map.walkable(nx, ny) or self._occupied((nx, ny), s.player.id):
            return
        s.player.pos = (nx, ny)
        s.clock.advance(0.05)               # exploration narrative time (game owns the clock)
        self._step_followers()              # companions trail you
        self._maybe_trigger_encounter()

    def _try_open_door(self, door) -> None:
        """Opening is GAME-enforced: a keyed door yields to its keystone (the DM can't hand-wave it).
        If you don't have the keystone you may still FORCE it with a hard STR check — a costly, luck-
        dependent fallback so alienating Vael (the keystone's holder) is a real setback, not a dead
        soft-lock. The check is game-owned (rules core), re-attemptable each time you shoulder it."""
        s = self.state
        if not door.key_item or s.has_item(door.key_item):
            self._open_inner_door(door, "You set the black keystone to the lock; " + door.name +
                                  " grinds open, and cold air breathes up from a stair spiraling down "
                                  "into deeper dark.")
            return
        r = self.rules.ability_check(s.player, "STR", 18)   # DC 18: hard, not hopeless
        if r.success:
            self._open_inner_door(door, "You set your shoulder to " + door.name + " and heave — old iron "
                                  "shrieks, timber splinters, and it bursts inward. Cold air breathes up "
                                  "from a stair spiraling down into deeper dark.")
        else:
            self._emit(NarrationEvent(text=f"{door.name} holds fast against your shoulder. It won't give "
                                           "without its keystone — or a mightier effort than that."))

    def _open_inner_door(self, door, how: str) -> None:
        s = self.state
        door.locked = False
        self._emit(NarrationEvent(text=how))
        for q in s.quests:
            if q.id == "descend":
                q.state = "done"
        s.flags["inner_door_open"] = True
        self._emit(NarrationEvent(text="[End of the demo slice — the way down is open. What you carry and "
                                        "who walks beside you are yours to take deeper.]"))

    # ---- shared movement / occupancy helpers ----
    def _occupied(self, pos, exclude_id: str | None = None) -> bool:
        s = self.state
        pos = tuple(pos)
        if pos == tuple(s.player.pos) and exclude_id != s.player.id:
            return True
        if any(f.pos and tuple(f.pos) == pos and f.id != exclude_id for f in s.followers):
            return True
        if any(n.pos and tuple(n.pos) == pos for n in s.npcs):
            return True
        return any(en.alive and en.pos and tuple(en.pos) == pos and en.id != exclude_id
                   for e in s.encounters for en in e.enemies)

    def _step_toward(self, mover, dest) -> None:
        s = self.state
        opts = [(mover.pos[0] + dx, mover.pos[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        opts = [c for c in opts if s.world_map.walkable(*c) and not self._occupied(c, mover.id)]
        if opts:
            mover.pos = min(opts, key=lambda c: self._dist(c, dest))

    def _step_followers(self) -> None:
        for f in self.state.followers:
            if f.alive and f.pos and self._dist(f.pos, self.state.player.pos) > 1:
                self._step_toward(f, self.state.player.pos)

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
        slug = action.target_id
        if not slug:                        # fall back to the nearest NPC in speaking range
            near = [n for n in s.npcs if n.pos and self._dist(n.pos, s.player.pos) <= 2]
            tgt = min(near, key=lambda n: self._dist(n.pos, s.player.pos), default=None)
            slug = tgt.slug if tgt else None
        if not slug or slug not in self.minds.engines:   # engines are keyed by slug — works for followers too
            self._emit(NarrationEvent(text="There is no one close enough to speak to."))
            return
        name = self.minds.characters[slug].name
        reply = await self.minds.talk(slug, action.text, self._situation(slug))
        self._emit(DialogueEvent(npc=name, slug=slug, text=reply))
        s.campaign_log.add(s.clock.value, f'The traveler said to {name}: "{action.text}"', tags=["talk", slug])

    async def _recruit(self, action: PlayerAction) -> None:
        """Ask an adjacent NPC to join. The NPC DECIDES via choose_action, grounded in how they've
        come to regard the traveler — so a Vael you've helped comes along; one you've wronged won't.
        On yes, they become a Follower who trails you (and can fight beside you)."""
        s = self.state
        npc = next((n for n in s.npcs if n.slug == action.target_id), None)
        if npc is None:
            npc = min((n for n in s.npcs if n.pos and self._dist(n.pos, s.player.pos) <= 1),
                      key=lambda n: self._dist(n.pos, s.player.pos), default=None)
        if npc is None:
            self._emit(NarrationEvent(text="No one beside you to ask along."))
            return
        choice = await self.minds.act(npc.slug, self._situation(
            npc.slug, recent=["The traveler asks you to come with them, deeper into the Vault."]),
            ["Go with the traveler", "Stay here"])
        self._emit(DialogueEvent(npc=npc.name, slug=npc.slug, text=choice.get("reason") or "..."))
        if "go" in (choice.get("action") or "").lower():
            self._make_follower(npc)
            self._emit(NarrationEvent(text=f"{npc.name} falls in beside you."))
            self._maybe_give_keystone(npc)

    def _maybe_give_keystone(self, npc) -> None:
        """The differentiator meets progression: Vael only chooses to JOIN if he's come to trust you —
        and a Vael who trusts you enough to travel with you hands over the keystone (his secret). A
        Vael you've alienated won't join, so this path to the inner door stays shut. Consequences."""
        from .content import KEYSTONE, VAEL, keystone_item
        s = self.state
        if npc.slug == VAEL and not s.has_item(KEYSTONE):
            s.player.inventory.append(keystone_item())
            self._emit(DialogueEvent(npc=npc.name, slug=npc.slug,
                       text="If we're in this together — here. The thing my crew died for. It opens the "
                            "inner door. Don't make me sorry I trusted you with it."))
            self._emit(NarrationEvent(text=f"{npc.name} presses a black keystone into your palm."))
            for q in s.quests:
                if q.id == "descend":
                    q.state = "active"

    def _grant_item(self, name: str, kind: str = "misc") -> str:
        """DM callback: loot found through a free-form action becomes a REAL item — but never the
        objective key (that gate is game-owned, not the DM's to hand out)."""
        iid = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")[:40] or "item"
        if "keystone" in iid or iid == "keystone":
            return "(refused: that item is off-limits to grant)"
        from .state import Item
        self.state.player.inventory.append(Item(id=iid, name=name, kind=kind))
        self.state.campaign_log.add(self.state.clock.value, f"The traveler took {name}.", tags=["loot"])
        return name

    def _make_follower(self, npc) -> None:
        from .state import Follower, Stats
        char = self.minds.characters.get(npc.slug)
        sheet = ((char.game_data if char else {}) or {}).get("dnd5e", {}).get("sheet", {})
        hp = int(sheet.get("max_hp", 12))
        self.state.followers.append(Follower(
            id=npc.slug, name=npc.name, mind_slug=npc.slug, pos=npc.pos, max_hp=hp, hp=hp,
            ac=int(sheet.get("ac", 12)),
            stats=Stats(STR=sheet.get("STR", 10), DEX=sheet.get("DEX", 10), CON=sheet.get("CON", 10))))
        self.state.npcs = [n for n in self.state.npcs if n.slug != npc.slug]
        self.state.campaign_log.add(self.state.clock.value, f"{npc.name} joined the traveler.", tags=["recruit", npc.slug])

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

    # ---- combat (turn-based) ----
    def _enter_combat(self, encounter) -> None:
        from .state import CombatState
        encounter.triggered = True
        combatants = ([self.state.player] + [f for f in self.state.followers if f.alive]
                      + [e for e in encounter.enemies if e.alive])
        order = self.rules.roll_initiative(combatants)
        self.state.combat = CombatState(order=order, round=1, turn_index=0)
        self.state.mode = Mode.combat
        self._emit(ModeChangedEvent(mode=Mode.combat))
        self._emit(CombatEvent(text="Steel rings in the dark — goblins boil out of the shadows! "
                                    "(move into one to attack · g: toggle their HP)"))

    def _living_enemies(self) -> list:
        return [en for e in self.state.encounters for en in e.enemies if en.alive]

    def _resolve_attack(self, attacker, target, dice: str, ability: str) -> None:
        r = self.rules.attack(attacker, target, ability=ability, damage_dice=dice)
        self._emit(CombatEvent(text=f"{attacker.name} {'hits for %d' % r.damage if r.hit else 'misses'} {target.name}."))
        if r.target_down:
            self._emit(CombatEvent(text=f"{target.name} falls."))

    async def _combat_action(self, action: PlayerAction) -> None:
        s = self.state
        # PLAYER turn: bump-to-attack or step
        if action.kind == "move":
            tx, ty = s.player.pos[0] + action.dx, s.player.pos[1] + action.dy
            tgt = next((e for e in self._living_enemies() if e.pos and tuple(e.pos) == (tx, ty)), None)
            if tgt:
                self._resolve_attack(s.player, tgt, "1d8", "STR")
            elif s.world_map.walkable(tx, ty) and not self._occupied((tx, ty), s.player.id):
                s.player.pos = (tx, ty)
            else:
                return                       # bumped a wall — not a turn
        elif action.kind != "wait":
            return
        if not self._living_enemies():
            self._end_combat(victory=True); return
        await self._ally_turns()             # the differentiator: does the ally fight for you?
        if not self._living_enemies():
            self._end_combat(victory=True); return
        self._enemy_turns()
        if not s.player.alive:
            self._on_player_death()
            return
        s.combat.round += 1

    def _on_player_death(self) -> None:
        """Defeat is a TERMINAL state, not a stuck combat: leave combat mode, set game_over, and
        stop accepting further actions (submit_action guards on the flag). Without this the player
        is trapped in combat forever — a corpse that can still 'act' while enemies keep rolling."""
        s = self.state
        s.flags["game_over"] = True
        s.mode = Mode.exploration
        s.combat = None
        self._emit(ModeChangedEvent(mode=Mode.exploration))
        self._emit(CombatEvent(text="You fall in the dark of the Vault, and it closes over you. "
                                    "Your story ends here. (press q to quit)"))

    async def _ally_turns(self) -> None:
        s = self.state
        for f in s.followers:
            if not (f.alive and self._living_enemies()):
                continue
            # Decide the ally's stance ONCE per fight (an LLM call), grounded in how they regard the
            # traveler — then just execute it each round. This is the sharpest differentiator: a Vael
            # you've helped fights; one you've wronged guards himself, hangs back, or flees.
            act = s.combat.ally_stance.get(f.mind_slug)
            if act is None:
                choice = await self.minds.act(f.mind_slug, self._situation(
                    f.mind_slug, recent=["Goblins have set on the traveler — steel is out in the dark."]),
                    ["Fight the goblins beside the traveler", "Guard the traveler", "Hang back", "Flee the fight"])
                act = (choice.get("action") or "").lower()
                s.combat.ally_stance[f.mind_slug] = act
                self._emit(CombatEvent(text=f"{f.name}: {choice.get('reason') or act}"))
            if "fight" in act or "beside" in act:
                tgt = min(self._living_enemies(), key=lambda e: self._dist(f.pos, e.pos))
                if self._dist(f.pos, tgt.pos) > 1:
                    self._step_toward(f, tgt.pos)
                if self._dist(f.pos, tgt.pos) <= 1:
                    self._resolve_attack(f, tgt, "1d6", "STR")
            # guard / hang back / flee -> no attack: a wronged ally simply won't spend blood for you

    def _enemy_turns(self) -> None:
        s = self.state
        marks = [s.player] + [f for f in s.followers if f.alive]
        for g in self._living_enemies():
            tgt = min(marks, key=lambda t: self._dist(g.pos, t.pos))
            if self._dist(g.pos, tgt.pos) > 1:
                self._step_toward(g, tgt.pos)
            if self._dist(g.pos, tgt.pos) <= 1:
                self._resolve_attack(g, tgt, "1d4", "DEX")

    def _end_combat(self, victory: bool) -> None:
        s = self.state
        s.mode = Mode.exploration
        s.combat = None
        self._emit(ModeChangedEvent(mode=Mode.exploration))
        if victory:
            self._emit(CombatEvent(text="The goblins are down. Quiet settles back over the Vault."))
