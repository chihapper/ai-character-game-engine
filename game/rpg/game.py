"""RpgGame — the concrete `GameSession` that ties the WORLD (`GameState`), the MINDS (`Minds`),
and the RULES (`D20Rules`) together behind one boundary. Free-flow exploration by default;
turn-based combat on encounter. Renderer-agnostic: consumes `PlayerAction`s, emits DATA events.

This is the game-core loop the spec's step 7 describes. Reactions stay a game-composed recipe
(remember -> salience -> deliberate -> enact); the DM narrator (step 5) and full combat resolution
layer on top of this without changing the seam.
"""
from __future__ import annotations

import asyncio
import re

from game import policy

from .dm import DM
from .minds import Minds
from .rules import D20Rules
from .srd.combat import CombatEngine
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

_REACT_THRESHOLD = 0.7   # game-owned salience bar for turning a witnessed event into a reaction


def _enemy_label(enemies) -> str:
    """A readable plural for the DOMINANT enemy in a fight ('goblins', 'cinder-husks') — so combat
    barks name whatever the slice actually fielded, never a hard-coded 'goblins'. Ties break
    alphabetically (sorted) so the label is deterministic across processes — a bare set() iteration
    order varies with string-hash randomization."""
    names = [e.name for e in enemies] or ["enemies"]
    noun = max(sorted(set(names)), key=names.count).lower()
    return noun if noun.endswith("s") else noun + "s"


_QUOTED = re.compile(r'"([^"]*)"|“([^”]*)”')


def _split_speech(text: str) -> tuple[str, str]:
    """Split an NPC reply into (spoken speech, stage-direction action). The engine's replies mix
    first-person quoted speech ("Name's Vael…") with third-person action beats ("He shifts weight…").
    The game/client layer separates them: speech becomes the dialogue line (shown + voiced); action
    is carried as DATA for the voice layer (Hume acts it) and possible DM narration — it is NEVER
    rendered as player-visible text (owner directive). No quotes -> the whole line is speech."""
    text = (text or "").strip()
    quoted = [(m.group(1) or m.group(2) or "").strip() for m in _QUOTED.finditer(text)]
    quoted = [q for q in quoted if q]
    if not quoted:
        return text, ""
    speech = " ".join(quoted)
    action = re.sub(r"\s+", " ", _QUOTED.sub(" ", text)).strip(" *—-")
    return speech, action


_SIGHT_RADIUS = 8   # how far the player sees (tiles), before walls block the line of sight


def _bresenham(x0: int, y0: int, x1: int, y1: int) -> list:
    """Integer grid line from (x0,y0) to (x1,y1), inclusive of both endpoints."""
    pts = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        pts.append((x, y))
        if x == x1 and y == y1:
            return pts
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


class RpgGame(GameSession):
    def __init__(self, state: GameState, minds: Minds, rules: D20Rules, dm: DM) -> None:
        self.state = state
        self.minds = minds
        self.rules = rules
        self.dm = dm
        # The turn-based combat engine shares the rules' RNG so the whole game is one deterministic
        # stream (initiative, attacks, saves, death saves).
        self.combat_engine = CombatEngine(rng=getattr(self.rules, "rng", None))
        self._events: asyncio.Queue[GameEvent] = asyncio.Queue()
        self._visible: set = set()              # tiles the player can see right now (fog of war)
        self._recompute_fov()                   # light up the starting area

    @classmethod
    def new(cls, *, slice: str = "vault", seed: int = 1337,
            reply_model: str | None = "claude-haiku-4-5",
            dm_model: str | None = "claude-haiku-4-5") -> "RpgGame":
        """Build a game from a named SLICE. The slice is pure content (map + minds + world flavor);
        the core reads `state.flavor` and never authors prose, so a new slice needs no core change."""
        from .content import SLICES
        builder = SLICES.get(slice)
        if builder is None:
            raise ValueError(f"unknown slice {slice!r}; known: {', '.join(sorted(SLICES))}")
        state, chars = builder(seed=seed)
        rules = D20Rules(seed=seed)
        # The DM's setting/genre comes from the slice's flavor — not a hard-coded dungeon.
        return cls(state, Minds(chars, reply_model=reply_model), rules,
                   DM(rules, model=dm_model, setting=state.flavor.dm_setting))

    @classmethod
    def resume(cls, *, slice: str, seed: int, state: GameState,
               reply_model: str | None = "claude-haiku-4-5",
               dm_model: str | None = "claude-haiku-4-5") -> "RpgGame":
        """Rebuild a game around a SAVED world state (the Phase-A persistence promise: world + minds
        across a restart). The WORLD comes from the save; the CAST is rebuilt from the slice (their
        MINDS persist on their own — each engine character auto-loads its memory namespace), so a
        remembered kindness survives the restart along with the map you cleared. The RNG is re-seeded
        (its mid-stream state is deliberately not persisted — replay is not a supported property)."""
        from .content import SLICES
        builder = SLICES.get(slice)
        if builder is None:
            raise ValueError(f"unknown slice {slice!r}; known: {', '.join(sorted(SLICES))}")
        fresh, chars = builder(seed=seed)        # throwaway world — the cast + AUTHORED data source
        rules = D20Rules(seed=seed)
        # Re-stamp AUTHOR-OWNED content from the current slice onto the saved world: prose and
        # social gates are the author's to evolve between sessions (a save from before a balance
        # pass must not freeze Vael's gate at an old default), while WORLD PROGRESS (positions,
        # inventory, flags, talk counts, who joined) stays exactly as saved.
        state.flavor = fresh.flavor
        fresh_npcs = {n.slug: n for n in fresh.npcs}
        for n in state.npcs:
            src = fresh_npcs.get(n.slug)
            if src is not None:
                n.recruit_min_talks = src.recruit_min_talks
                n.recruit_requires_flag = src.recruit_requires_flag
                n.on_recruit_grant = src.on_recruit_grant
                n.on_recruit_line = src.on_recruit_line
        return cls(state, Minds(chars, reply_model=reply_model), rules,
                   DM(rules, model=dm_model, setting=state.flavor.dm_setting))

    async def begin(self) -> None:
        """Open the game with a DM scene — the world speaks first. On a RESUMED game this reads the
        saved campaign log through _scene_text, so the DM naturally recaps where things stand."""
        self._emit(NarrationEvent(text=await self.dm.narrate_scene(self._scene_text())))

    # ---- events (to the view) ----
    def _emit(self, ev: GameEvent) -> None:
        self._events.put_nowait(ev)

    def _say(self, name: str, slug: str, text: str) -> None:
        """Emit an NPC line, split into spoken speech vs. stage-direction action (see _split_speech).
        The renderer shows only `speech` as the dialogue line (`action` is never shown as text);
        downstream voice synthesis reads the full `text` (Hume voices the quoted speech, ACTS the
        directions)."""
        speech, action = _split_speech(text)
        self._emit(DialogueEvent(npc=name, slug=slug, text=text, speech=speech, action=action))

    async def events(self):
        while True:
            yield await self._events.get()

    def drain_events(self) -> list[GameEvent]:
        """Non-blocking: pop every event queued since the last drain. The request/response IPC seam
        (the WebSocket server, and any renderer that polls after an action) uses this instead of the
        blocking `events()` stream."""
        out: list[GameEvent] = []
        while not self._events.empty():
            out.append(self._events.get_nowait())
        return out

    # ---- state snapshot (mechanical only — no mind) ----
    def get_state(self) -> StateSnapshot:
        s = self.state
        vis = self._visible
        seen = lambda p: p is not None and (int(p[0]), int(p[1])) in vis
        explored = lambda p: p is not None and f"{int(p[0])},{int(p[1])}" in s.explored
        ents: list[EntityView] = []
        # Fog of war: NPCs and enemies show only where the player can SEE them; a locked door stays on
        # the map once explored (a remembered feature); followers are with you, so always shown.
        for n in s.npcs:
            if seen(n.pos):
                ents.append(EntityView(id=n.slug, name=n.name, pos=n.pos, kind="npc"))
        for f in s.followers:
            ents.append(EntityView(id=f.id, name=f.name, pos=f.pos, kind="follower", hp=f.hp, max_hp=f.max_hp,
                                   down=f.down, death_successes=f.death_save_successes,
                                   death_failures=f.death_save_failures))
        show_hp = bool(s.combat and s.combat.show_enemy_hp)   # HP hidden unless toggled (guardrail #5)
        for e in s.encounters:
            for en in e.enemies:
                if en.alive and seen(en.pos):
                    ents.append(EntityView(id=en.id, name=en.name, pos=en.pos, kind="enemy",
                                           hp=en.hp if show_hp else None,
                                           max_hp=en.max_hp if show_hp else None))
        for d in s.doors:
            if d.locked and explored(d.pos):
                ents.append(EntityView(id=d.id, name="Door", pos=d.pos, kind="door"))
        objective = next((q.title for q in s.quests if q.state in ("open", "active")), "")
        cs = s.combat
        return StateSnapshot(
            mode=s.mode, clock=s.clock.value, player=s.player, objective=objective,
            inventory=[it.name for it in s.player.inventory],
            map_width=s.world_map.width, map_height=s.world_map.height, tiles=s.world_map.tiles,
            entities=ents, combat_order=(cs.order if cs else []),
            # The initiative cursor is real now: begin_combat/advance_turn keep it in sync, so
            # combat_turn is whoever is acting this instant (the view highlights them + gates input).
            combat_turn=(cs.current() if cs else None), show_enemy_hp=show_hp,
            combat_round=(cs.round if cs else 0),
            combat_movement=(cs.movement_left if cs else 0),
            combat_action_used=(cs.action_used if cs else False),
            visible=[f"{x},{y}" for (x, y) in vis], explored=list(s.explored))

    # ---- world helpers ----
    def _npc_at(self, pos) -> NpcPlacement | None:
        return next((n for n in self.state.npcs if n.pos and tuple(n.pos) == tuple(pos)), None)

    def _dist(self, a, b) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _situation(self, for_slug: str, *, recent: list[str] | None = None):
        """Build the perceiving NPC's `Situation` from the world — location + who's present + the
        numeric clock + light grounding. The engine owns everything about the mind. PRESENT includes
        party followers (recruits leave s.npcs when they join, so without this a companion standing
        right there was invisible to every mind — talking past someone the scene says is present)."""
        s = self.state
        others = [s.player.name] + [n.name for n in s.npcs
                                    if n.slug != for_slug and n.pos
                                    and self._dist(n.pos, s.player.pos) <= 6]
        others += [f.name for f in s.followers
                   if f.alive and f.pos and f.mind_slug != for_slug
                   and self._dist(f.pos, s.player.pos) <= 6]
        flavor = self.state.flavor
        extra = {"The world you live in": flavor.world_frame, "Performance": policy.PERFORMANCE_RULES}
        return self.minds.situation(clock=self.state.clock.value, location=flavor.location_label,
                                    present=others, recent_events=recent or [], game_time=flavor.time_label,
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
            # If moving tripped an encounter, the setup is done but no one has acted yet: let the
            # combat engine run NPC turns until it's the (living) player's turn — the player may not
            # win initiative. Idempotent when the player IS first (returns immediately).
            if self.state.mode == Mode.combat:
                await self._resume_combat()
        self._emit(StateChangedEvent())

    # ---- exploration (free-flow) ----
    async def _explore_action(self, action: PlayerAction) -> None:
        if action.kind == "move":
            self._move_player(action.dx, action.dy)
        elif action.kind == "move_to":
            self._move_to(action.tx, action.ty)
        elif action.kind == "talk":
            await self._talk(action)
        elif action.kind == "recruit":
            await self._recruit(action)
        elif action.kind == "do":
            await self._do(action.text)
        elif action.kind == "look":
            self._emit(NarrationEvent(text=await self.dm.narrate_scene(self._scene_text())))
        elif action.kind == "use":
            self._use_item(action.target_id)
        elif action.kind == "rest":
            self._rest()
        elif action.kind == "wait":
            self.state.clock.advance(0.1)

    def _use_item(self, item_id: str = "") -> bool:
        """Consume an inventory item (today: anything with a `heal` roll in its data — a healing
        draught). `item_id` picks a specific one; empty = the first healing consumable carried.
        Returns True if something was consumed (the combat path spends the ACTION on it; the
        exploration path advances the clock). Multi-use items (`data.uses`) decrement and are
        removed only when spent. GAME-enforced mechanics: the dice decide the healing, never
        narration. Refuses at full HP so a stray keypress can't waste an item (or the action)."""
        s = self.state
        p = s.player
        def _healable(it) -> bool:
            return it.kind == "consumable" and bool((it.data or {}).get("heal"))
        item = next((it for it in p.inventory
                     if (it.id == item_id if item_id else _healable(it))), None)
        if item is None or not _healable(item):
            # Honest wording: non-heal consumables (antitoxin, oils...) exist but have no game
            # effect wired yet — "yet" keeps the refusal truthful for them.
            self._emit(NarrationEvent(text="Nothing in your pack you can use yet."))
            return False
        if p.hp >= p.max_hp:
            self._emit(NarrationEvent(text="You're unhurt — no sense wasting it."))
            return False
        healed = max(1, self.combat_engine.dice.roll(str(item.data["heal"])))
        before = p.hp
        p.hp = min(p.max_hp, p.hp + healed)
        uses = int((item.data or {}).get("uses", 1) or 1) - 1
        if uses > 0:
            item.data["uses"] = uses
        else:
            p.inventory.remove(item)
        if s.mode != Mode.combat:                 # combat pays with the ACTION; exploration with time
            s.clock.advance(0.05)
        self._emit(NarrationEvent(
            text=f"You down {item.name} — {p.hp - before} HP back ({p.hp}/{p.max_hp}).",
            data={"sfx": "drink"}))
        s.campaign_log.add(s.clock.value, f"The traveler used {item.name}.", tags=["item"])
        return True

    def _rest(self) -> None:
        """A costed camp rest (completes the fight/loot/heal survival loop): the whole party heals
        a hit-die + CON each (dice decide, never narration), REAL time passes, and settling down in
        hostile dark is LOUD — a seeded chance that a nearby untriggered encounter comes to see
        (the same noise pattern as door-forcing; all prose is the slice's WorldFlavor data)."""
        s = self.state
        party = [s.player] + [f for f in s.followers if f.alive]
        if all(c.hp >= c.max_hp for c in party):
            self._emit(NarrationEvent(text="No one needs the rest — better to keep moving."))
            return
        s.clock.advance(0.5)                     # a rest is the most expensive time purchase there is
        healed: list[str] = []
        for c in party:
            if c.hp >= c.max_hp:
                continue
            roll = self.combat_engine.dice.roll(c.hit_dice or "1d8") + c.stats.mod("CON")
            gain = min(c.max_hp - c.hp, max(1, roll))
            c.hp += gain
            healed.append(f"{c.name} +{gain}")
        self._emit(NarrationEvent(text=f"{s.flavor.rest_text} ({', '.join(healed)} HP)"))
        s.campaign_log.add(s.clock.value, "The party rested.", tags=["rest"])
        # Noise: resting can draw a nearby pack that hasn't been dealt with yet (seeded).
        if self.rules.rng.random() < 0.35:
            noisy = next((e for e in s.encounters
                          if not e.triggered and e.trigger_pos
                          and self._dist(s.player.pos, e.trigger_pos) <= 20), None)
            if noisy is not None:
                self._emit(NarrationEvent(text=s.flavor.rest_ambush))
                self._enter_combat(noisy)        # submit_action resumes NPC turns right after

    def _scene_text(self) -> str:
        """The world-state the DM narrates FROM — where the player is, who's near, recent history.
        The base setting sentence is the SLICE's (flavor.scene_prose); the core only assembles the
        live who's-near / party / recent context around it."""
        s = self.state
        near = [n.name for n in s.npcs if n.pos and self._dist(n.pos, s.player.pos) <= 5]
        party = [f.name for f in s.followers if f.alive]
        parts = [s.flavor.scene_prose]
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
        if abs(dx) + abs(dy) != 1:          # server authority: one orthogonal step, never a teleport
            return                          # (a raw wire client could otherwise jump walls/doors)
        old = tuple(s.player.pos)
        nx, ny = old[0] + dx, old[1] + dy
        door = next((d for d in s.doors if d.locked and tuple(d.pos) == (nx, ny)), None)
        if door:
            self._try_open_door(door)       # walking into a locked door = try to open it
            return
        if not s.world_map.walkable(nx, ny):
            return
        # Enemies are solid (you reach them through combat). A non-hostile NPC on the target cell is
        # pushed to your OLD cell so a bystander can't wall you off; followers are re-threaded onto
        # your trail below (see _advance_followers), so walking onto one is fine.
        if any(en.alive and en.pos and tuple(en.pos) == (nx, ny) for e in s.encounters for en in e.enemies):
            return
        npc = next((n for n in s.npcs if n.pos and tuple(n.pos) == (nx, ny)), None)
        if npc is not None:
            npc.pos = old
        s.player.pos = (nx, ny)
        s.clock.advance(0.05)               # exploration narrative time (game owns the clock)
        self._recompute_fov()               # reveal what the new vantage can see
        self._advance_followers(old)        # party follows your EXACT path, single-file
        self._maybe_trigger_encounter()

    def _try_open_door(self, door) -> None:
        """Opening is GAME-enforced: a keyed door yields to its key item (the DM can't hand-wave it).
        Without the key you may still FORCE it with a hard STR check (door.force_dc) — a costly,
        luck-dependent fallback so losing the key-holder's goodwill is a real setback, not a dead
        soft-lock. All narration is the SLICE's (door.*_text); the core names no keystone or stair."""
        s = self.state
        if not door.key_item or s.has_item(door.key_item):
            self._open_door(door, door.open_text or f"You unlock {door.name}; it swings open.")
            return
        if door.force_dc <= 0:                              # slice declared this gate unforceable
            self._emit(NarrationEvent(text=door.locked_text or f"{door.name} holds fast — it needs its key."))
            return
        # Forcing is COSTLY, not free: every attempt spends narrative time, and a FAILED attempt is
        # LOUD — the noise springs any nearby untriggered encounter. Without these, bump-spamming the
        # door converged on success with zero downside, gutting the trust-gated key path (the
        # differentiator's objective gate).
        s.clock.advance(0.1)
        r = self.rules.ability_check(s.player, "STR", door.force_dc)
        if r.success:
            self._open_door(door, door.force_text or f"You force {door.name} open by main strength.")
        else:
            self._emit(NarrationEvent(text=door.locked_text or
                                      f"{door.name} holds fast — it needs its key, or a mightier effort."))
            noisy = next((e for e in s.encounters
                          if not e.triggered and e.trigger_pos
                          and self._dist(door.pos, e.trigger_pos) <= 12), None)
            if noisy is not None:
                self._emit(NarrationEvent(text=s.flavor.force_noise))
                self._enter_combat(noisy)   # submit_action resumes NPC turns right after

    def _open_door(self, door, how: str) -> None:
        s = self.state
        door.locked = False
        self._emit(NarrationEvent(text=how, data={"sfx": "door"}))
        if door.opens_quest:                               # data-linked objective, not a literal id
            for q in s.quests:
                if q.id == door.opens_quest:
                    q.state = "done"
        s.flags[f"{door.id}_open"] = True
        if door.outro:
            self._emit(NarrationEvent(text=door.outro))

    # ---- shared movement / occupancy helpers ----
    def _occupied(self, pos, exclude_id: str | None = None) -> bool:
        s = self.state
        pos = tuple(pos)
        if pos == tuple(s.player.pos) and exclude_id != s.player.id:
            return True
        # DEAD followers no longer block (mirrors the enemy `alive` check below — a corpse is not a
        # wall); a downed-but-alive body still does, for the length of the fight it fell in.
        if any(f.pos and tuple(f.pos) == pos and f.id != exclude_id and not f.dead for f in s.followers):
            return True
        if any(n.pos and tuple(n.pos) == pos for n in s.npcs):
            return True
        # A LOCKED door blocks everyone here (NPC/follower/enemy steps + combat movement); only the
        # player's exploration bump (_move_player) may interact with it to try opening.
        if any(d.locked and tuple(d.pos) == pos for d in s.doors):
            return True
        return any(en.alive and en.pos and tuple(en.pos) == pos and en.id != exclude_id
                   for e in s.encounters for en in e.enemies)

    def _step_toward(self, mover, dest) -> None:
        s = self.state
        opts = [(mover.pos[0] + dx, mover.pos[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        opts = [c for c in opts if s.world_map.walkable(*c) and not self._occupied(c, mover.id)]
        if opts:
            mover.pos = min(opts, key=lambda c: self._dist(c, dest))

    def _advance_followers(self, vacated) -> None:
        """Party follow = a single-file SNAKE: each companion steps into the cell the one ahead just
        vacated (the head into the player's OLD cell), so the party trails the player's EXACT path —
        always directly behind in the direction of travel, never lagging off to the side. Falls back
        to a greedy gap-close only if the trail cell is momentarily blocked (e.g. a bystander NPC
        was just pushed into it)."""
        s = self.state
        vacated = tuple(vacated)
        for f in s.followers:
            if not (f.alive and f.pos):
                continue
            cur = tuple(f.pos)
            if vacated != cur and s.world_map.walkable(*vacated) and not self._occupied(vacated, f.id):
                f.pos = vacated
            else:
                for _ in range(6):          # trail cell blocked — close the gap greedily instead
                    if self._dist(f.pos, s.player.pos) <= 1:
                        break
                    before = tuple(f.pos)
                    self._step_toward(f, s.player.pos)
                    if tuple(f.pos) == before:
                        break
            vacated = cur                   # the next companion trails into where THIS one just was

    def _maybe_trigger_encounter(self) -> None:
        s = self.state
        for e in s.encounters:
            if e.triggered or not e.trigger_pos:
                continue
            if self._dist(s.player.pos, e.trigger_pos) <= 2:
                self._enter_combat(e)
                return

    def _step_toward_tile(self, src, dst, explored=None):
        """First step (dx,dy) toward the REACHABLE cell nearest `dst`, over walkable tiles the player
        has SEEN (`explored`, default the live set), treating living enemies as blockers. Robust when
        `dst` is a wall/occupied/unexplored — the player still closes to the explored frontier.
        Returns None if boxed in / already there."""
        from collections import deque
        s = self.state
        explored = s.explored if explored is None else explored
        src, dst = tuple(src), tuple(dst)
        blocked = {tuple(en.pos) for e in s.encounters for en in e.enemies if en.alive and en.pos}
        prev = {src: None}
        order = [src]
        q = deque([src])
        while q:
            cx, cy = q.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (cx + dx, cy + dy)
                if nb in prev or not s.world_map.walkable(*nb):
                    continue
                if nb in blocked and nb != dst:
                    continue
                # Fog of war: only auto-walk through terrain you've SEEN — the clicked tile included.
                # (No destination exemption: clicking into the dark walks you to the explored
                # frontier, never ONTO an unexplored cell.)
                if f"{nb[0]},{nb[1]}" not in explored:
                    continue
                prev[nb] = (cx, cy)
                order.append(nb)
                q.append(nb)
        best = min(order, key=lambda c: self._dist(c, dst))
        if best == src:
            return None
        cur = best
        while prev[cur] != src:
            cur = prev[cur]
        return (cur[0] - src[0], cur[1] - src[1])

    def _move_to(self, tx: int, ty: int) -> None:
        """Click-to-move: walk the player toward tile (tx,ty), stepping via _move_player (which handles
        doors, the follower trail, and encounter triggers). A click on an UNEXPLORED tile is REJECTED
        outright (owner feedback 2026-07-07: selecting a spot you've never seen shouldn't do anything —
        explore by walking, not by clicking into the black). The path is limited to terrain explored AT
        CLICK TIME (frozen) — revealing new ground as you walk does NOT auto-extend the trip, so
        clicking far only takes you to the explored frontier. Stops on arrival, a blocked step, or when
        combat starts."""
        s = self.state
        if f"{tx},{ty}" not in s.explored:        # a spot you've never seen isn't a place you can pick
            return
        frozen = set(s.explored)                  # what was known when you clicked; don't extend it
        for _ in range(400):
            if tuple(s.player.pos) == (tx, ty) or s.mode == Mode.combat:
                return
            step = self._step_toward_tile(s.player.pos, (tx, ty), explored=frozen)
            if step is None:
                return
            before = tuple(s.player.pos)
            self._move_player(*step)
            if tuple(s.player.pos) == before:     # bumped a door/wall or nothing changed — stop
                return

    # ---- fog of war (FOV) ----
    def _recompute_fov(self) -> None:
        """Recompute the tiles the player can SEE (within the sight radius + line of sight; walls and
        void block), and fold them into the ever-explored set. Called at start + after each move."""
        s = self.state
        if not getattr(s, "player", None) or not s.player.pos:
            self._visible = set()
            return
        px, py = int(s.player.pos[0]), int(s.player.pos[1])
        wm = s.world_map
        r = _SIGHT_RADIUS
        vis = set()
        for y in range(py - r, py + r + 1):
            for x in range(px - r, px + r + 1):
                if not wm.in_bounds(x, y) or (x - px) ** 2 + (y - py) ** 2 > r * r:
                    continue
                if self._has_los(px, py, x, y):
                    vis.add((x, y))
        self._visible = vis
        for (x, y) in vis:
            s.explored.add(f"{x},{y}")

    def _has_los(self, x0: int, y0: int, x1: int, y1: int) -> bool:
        """Line of sight: blocked if any tile BETWEEN the two is opaque (wall/void). The endpoint may
        be opaque (you still see the wall face that bounds a room)."""
        wm = self.state.world_map
        for (x, y) in _bresenham(x0, y0, x1, y1)[1:-1]:
            if wm.tile(x, y) in ("#", " "):
                return False
        return True

    def _speaker_pos(self, slug: str):
        """Where the named character stands right now — as an NPC placement or a follower."""
        s = self.state
        n = next((n for n in s.npcs if n.slug == slug and n.pos), None)
        if n is not None:
            return n.pos
        f = next((f for f in s.followers if f.mind_slug == slug and f.pos), None)
        return f.pos if f is not None else None

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
        # SERVER-side gating (the view's adjacency check is a convenience, not the authority):
        # an explicit target must actually be in speaking range, and the dead don't answer.
        follower = next((f for f in s.followers if f.mind_slug == slug), None)
        if follower is not None and follower.down:
            self._emit(NarrationEvent(text=f"{follower.name} cannot hear you."))
            return
        pos = self._speaker_pos(slug)
        if pos is None or self._dist(pos, s.player.pos) > 2:
            self._emit(NarrationEvent(text="There is no one close enough to speak to."))
            return
        name = self.minds.characters[slug].name
        reply = await self.minds.talk(slug, action.text, self._situation(slug))
        self._say(name, slug, reply)
        s.talk_counts[slug] = s.talk_counts.get(slug, 0) + 1   # the recruit gate reads this
        s.campaign_log.add(s.clock.value, f'The traveler said to {name}: "{action.text}"', tags=["talk", slug])
        # Stage directions -> the DM narrates them IF a storyteller would (owner design): the
        # action beats are never shown as text, but a substantial visible gesture is offered to
        # the narrator, who describes it aloud or stays silent. Narrative relevance only.
        _, gesture = _split_speech(reply)
        if len(gesture) > 15:
            try:
                # Hard cap: a hung narrator call must never hold the reply batch hostage (the
                # same latency class the voice pipeline was rebuilt to eliminate).
                told = await asyncio.wait_for(
                    self.dm.narrate_gesture(name, gesture, scene=self._scene_text()), timeout=6)
                if told:
                    self._emit(NarrationEvent(text=told))
            except Exception:                    # noqa: BLE001 — narration is an enhancement
                pass

    async def _recruit(self, action: PlayerAction) -> None:
        """Ask an adjacent NPC to join — a social flow, not a command (owner design 2026-07-06):
        the ASK only truly lands once you've genuinely talked (per-NPC `recruit_min_talks`, plus an
        optional quest flag — both observable WORLD facts, authored as data). Asked too soon, the
        world affords no join yet: the mind still answers IN CHARACTER (and remembers being asked),
        it just isn't offered the choice to come — the offer hasn't been earned. Once earned, the
        NPC DECIDES via choose_action, grounded in how they've come to regard the traveler — one
        you've helped comes along; one you've wronged won't. The gate bounds the AFFORDANCE, never
        the mind's answer (that stays the engine's — never deterministic)."""
        s = self.state
        npc = next((n for n in s.npcs if n.slug == action.target_id), None)
        # Server-side range gate: an explicit target must actually be BESIDE you — the view's
        # adjacency check is a convenience, not the authority (a raw wire client could name anyone).
        # An EXPLICIT target out of range REFUSES outright (mirroring _talk) — silently redirecting
        # to whoever happens to be adjacent would plant the "asked me along" memory in the WRONG mind.
        if npc is not None and (not npc.pos or self._dist(npc.pos, s.player.pos) > 1):
            self._emit(NarrationEvent(text="No one beside you to ask along."))
            return
        if npc is None:                     # no explicit target: fall back to whoever is adjacent
            npc = min((n for n in s.npcs if n.pos and self._dist(n.pos, s.player.pos) <= 1),
                      key=lambda n: self._dist(n.pos, s.player.pos), default=None)
        if npc is None:
            self._emit(NarrationEvent(text="No one beside you to ask along."))
            return
        talks = s.talk_counts.get(npc.slug, 0)
        gate_met = talks >= max(0, int(npc.recruit_min_talks)) and (
            not npc.recruit_requires_flag or s.flags.get(npc.recruit_requires_flag, False))
        if not gate_met:
            # Premature ask: a real conversational beat. The afforded options carry no join —
            # the mind picks how to hold the stranger at arm's length, in its own voice, and the
            # moment is planted in its memory (an early ask can COLOR how trust grows).
            choice = await self.minds.act(npc.slug, self._situation(
                npc.slug, recent=[s.flavor.recruit_prompt]),
                ["Wave the request off — you two have barely spoken",
                 "Hear the traveler out, but promise nothing yet"])
            self._say(npc.name, npc.slug, choice.get("reason") or "...")
            await self.minds.remember(
                npc.slug, "The traveler asked me to come along before we'd hardly spoken.",
                kind="player_event", actor="player", player_role="caused", magnitude=0.3,
                t=s.clock.value)
            s.campaign_log.add(s.clock.value, f"The traveler asked {npc.name} along too soon.",
                               tags=["recruit", npc.slug])
            return
        choice = await self.minds.act(npc.slug, self._situation(
            npc.slug, recent=[self.state.flavor.recruit_prompt]),
            ["Go with the traveler", "Stay here"])
        self._say(npc.name, npc.slug, choice.get("reason") or "...")
        if "go" in (choice.get("action") or "").lower():
            self._make_follower(npc)
            self._emit(NarrationEvent(text=f"{npc.name} falls in beside you."))
            self._grant_on_recruit(npc)

    def _grant_on_recruit(self, npc) -> None:
        """The differentiator meets progression — DATA-DRIVEN, no slice literals in the core: an NPC
        that carries an `on_recruit_grant` only chooses to JOIN if it has come to trust the player,
        and on joining it hands that item over (often the objective key). An NPC you've alienated
        won't join, so that path stays shut — a real consequence, authored entirely in content."""
        item = getattr(npc, "on_recruit_grant", None)
        s = self.state
        if item is None or s.has_item(item.id):
            return
        s.player.inventory.append(item.model_copy(deep=True))
        if npc.on_recruit_line:
            self._say(npc.name, npc.slug, npc.on_recruit_line)
        self._emit(NarrationEvent(text=f"{npc.name} presses {item.name} into your palm."))
        # If this item unlocks a door tied to a quest, mark that quest active (linked by data).
        for d in s.doors:
            if d.key_item == item.id and d.opens_quest:
                for q in s.quests:
                    if q.id == d.opens_quest and q.state == "open":
                        q.state = "active"

    def _objective_key_ids(self) -> set[str]:
        """Item ids the DM must never hand out as loot — the keys to the slice's gated doors. Read
        from data, so it protects whatever THIS slice's objective key is (keystone, sigil, passcard)."""
        return {d.key_item for d in self.state.doors if d.key_item}

    def _grant_item(self, name: str, kind: str = "misc") -> str:
        """DM callback: loot found through a free-form action becomes a REAL item — but never an
        objective key (that gate is game-owned, not the DM's to hand out). Refusal is by DATA (the
        slice's door keys), not a hard-coded item name. Returns '' on refusal (the DM tool loop
        reads falsy = refused and tells the model plainly — see dm.py). The guard matches by
        CONTAINMENT both ways, so a decoy like 'a black keystone' -> 'a-black-keystone' can't slip
        past an exact-id check."""
        iid = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")[:40] or "item"
        if any(k in iid or iid in k for k in self._objective_key_ids()):
            return ""
        from .state import Item
        self.state.player.inventory.append(Item(id=iid, name=name, kind=kind))
        self.state.campaign_log.add(self.state.clock.value, f"The traveler took {name}.", tags=["loot"])
        return name

    def _make_follower(self, npc) -> None:
        from .state import Follower, Stats
        char = self.minds.characters.get(npc.slug)
        sheet = ((char.game_data if char else {}) or {}).get("srd5", {}).get("sheet", {})
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
        # The dead witness nothing: drop targets whose combatant has fallen (a corpse's mind must
        # not keep accreting player deeds), and unknown slugs (robustness against a raw wire client).
        dead = {f.mind_slug for f in self.state.followers if f.dead}
        dead |= {en.mind_slug for e in self.state.encounters for en in e.enemies if en.mind_slug and en.dead}
        targets = [t for t in targets if t in self.minds.engines and t not in dead]
        if not targets:
            return
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
    # ---- combat (turn-based, driven by srd.combat.CombatEngine) -----------------------------------
    def _all_combatants(self) -> list:
        """Everyone the initiative order can name — player + ALL followers + ALL enemies (including the
        down/dead, so `advance_turn` can look them up by id and skip corpses). The order itself is fixed
        at combat start; the engine reads `.dead` to skip."""
        s = self.state
        return [s.player] + list(s.followers) + [en for e in s.encounters for en in e.enemies]

    def _living_enemies(self) -> list:
        return [en for e in self.state.encounters for en in e.enemies if en.alive]

    def _fight_encounter(self):
        """The encounter THIS fight is scoped to (None out of combat / legacy save without the id)."""
        cs = self.state.combat
        if cs is None or not cs.encounter_id:
            return None
        return next((e for e in self.state.encounters if e.id == cs.encounter_id), None)

    def _fight_enemies(self) -> list:
        """Living enemies OF THE CURRENT FIGHT. Victory, targeting, and labels all scope here — a
        slice with several encounters must never demand killing never-triggered enemies across the
        map (they aren't in the initiative order and get no turns). Falls back to the global list
        only when the fight carries no encounter id (defensive)."""
        enc = self._fight_encounter()
        if enc is None:
            return self._living_enemies()
        return [en for en in enc.enemies if en.alive]

    def _is_enemy(self, c) -> bool:
        return any(en.id == c.id for e in self.state.encounters for en in e.enemies)

    def _enter_combat(self, encounter) -> None:
        """Spring an encounter: roll initiative over player + living followers + living enemies, and open
        the turn on the TOP of the order. This is setup ONLY — `submit_action` calls `_resume_combat()`
        immediately after, which runs any NPC turns that precede the player's (the player may not win
        initiative)."""
        from .state import CombatState
        encounter.triggered = True
        combatants = ([self.state.player] + [f for f in self.state.followers if f.alive]
                      + [e for e in encounter.enemies if e.alive])
        order = self.combat_engine.roll_initiative(combatants)
        self.state.combat = CombatState(order=order, encounter_id=encounter.id)
        self.combat_engine.begin_combat(self.state.combat, combatants)
        self.state.mode = Mode.combat
        self._emit(ModeChangedEvent(mode=Mode.combat))
        label = _enemy_label([e for e in encounter.enemies])
        self._emit(CombatEvent(text=self.state.flavor.combat_start.format(enemies=label), data={"sfx": "alarm"}))

    def _attack(self, attacker, target) -> None:
        """One attack through the combat engine (the attacker's own weapon profile = data). Narrates the
        beat: hit/crit/miss, damage, and whether the target drops (unconscious) or is slain."""
        r = self.combat_engine.attack(attacker, target)
        # data carries WHO/WHOM/HOW MUCH so the renderer can stage visible effects (lunge, hit
        # flash, floating damage) — mechanical facts already narrated in the text, never the mind.
        beat = {"attacker": attacker.id, "target": target.id, "damage": r.damage,
                "crit": r.critical == "hit"}
        if r.hit:
            verb = "crits" if r.critical == "hit" else "hits"
            self._emit(CombatEvent(text=f"{attacker.name} {verb} {target.name} for {r.damage}.",
                                   data={"sfx": "crit" if r.critical == "hit" else "hit", **beat}))
        else:
            self._emit(CombatEvent(text=f"{attacker.name} misses {target.name}.",
                                   data={"sfx": "miss", **beat}))
        if r.target_dead:
            self._emit(CombatEvent(text=f"{target.name} is slain.",
                                   data={"sfx": "dead", "target": target.id}))
        elif r.target_down:
            self._emit(CombatEvent(text=f"{target.name} drops.",
                                   data={"sfx": "down", "target": target.id}))

    def _advance_combat_turn(self):
        """End the current turn and open the next (engine authority). When the order wraps to a new round,
        advance the game clock: a multi-round fight IS elapsed narrative time, which the engine differences
        for temporal decay — a fight followed by a conversation must not read as simultaneous. (state.py:
        the clock 'advances in rounds during combat'.)"""
        cs = self.state.combat
        before = cs.round
        nxt = self.combat_engine.advance_turn(cs, self._all_combatants())
        if cs.round > before:
            self.state.clock.advance(0.1)          # narrative time gained per completed combat round
        return nxt

    async def _resume_combat(self) -> None:
        """Run the initiative order until it's the (conscious) player's turn or the fight is over. Enemies
        and followers act on their turns; a downed PC-like rolls a death save on its. Everything that
        happens between two of the player's turns resolves here — the player only ever acts on THEIR
        turn (handed back to the view when `current()` is the conscious player)."""
        s = self.state
        eng = self.combat_engine
        for _ in range(500):                       # guard against a pathological non-terminating order
            if s.mode != Mode.combat or s.combat is None:
                return
            if not self._fight_enemies():
                self._end_combat(victory=True); return
            combatants = self._all_combatants()
            cur = eng.current(s.combat, combatants)
            if cur is None:
                self._end_combat(victory=True); return
            if cur.dead:
                self._advance_combat_turn(); continue
            if cur.down:                           # unconscious but not dead -> death save on its turn
                outcome = self._death_save_turn(cur)
                if cur.id == s.player.id and s.player.dead:
                    self._on_player_death(); return
                if outcome == "revive":            # nat 20: they wake at 1 HP AND get their turn (RAW)
                    eng.begin_turn(s.combat, cur)
                    if cur.id == s.player.id:
                        return                     # the revived player acts — hand control to the view
                    await self._npc_turn(cur)
                    if s.player.dead:
                        self._on_player_death(); return
                self._advance_combat_turn(); continue
            if cur.id == s.player.id:
                return                             # the conscious player's turn: hand control to the view
            await self._npc_turn(cur)              # an enemy or a follower takes its whole turn
            if s.player.dead:                      # e.g. an enemy's blow was massive-damage instant death
                self._on_player_death(); return
            self._advance_combat_turn()
        # Guard exhausted — only reachable if the player has been unconscious for 500 straight turns with
        # the fight unable to resolve (e.g. the whole party is downed-stable and the last enemies are
        # physically walled off from every body, so they can never land a finishing blow). NEVER strand
        # the player in `combat` with no turn to act on: resolve deterministically. Resolution is
        # PARTY-AWARE, not player-only: a stalemate is a DEFEAT only when the WHOLE party has fallen —
        # keying on the player alone would read as "you died" while a conscious ally still stands (and
        # would be an outright wrong-defeat if an ally-revival mechanic is ever added). If anyone on the
        # party is still up, just end the unwinnable fight instead.
        if s.mode == Mode.combat:
            party_up = s.player.alive or any(f.alive for f in s.followers)
            if not party_up:
                self._on_player_death()
            else:
                self._end_combat(victory=not self._fight_enemies())

    async def _combat_action(self, action: PlayerAction) -> None:
        """Apply the player's intent on THEIR turn only, spending the action economy. Movement is 5 ft
        per tile from `movement_left`; attacking an adjacent foe spends the action. The turn ends on an
        explicit `wait`/space, or automatically once no full step of movement remains AND there is nothing
        left to attack (the action is spent, or no foe is adjacent to spend it on). While a bump-attack is
        still possible the turn stays open. `wait` always ends the turn. Then `_resume_combat` runs the
        NPC turns."""
        s = self.state
        cs = s.combat
        if cs is None:
            return
        cur = self.combat_engine.current(cs, self._all_combatants())
        if cur is None or cur.id != s.player.id or not s.player.alive:
            return                                 # stray input outside the player's turn — ignore it
        ended = False
        if action.kind == "wait":
            ended = True
        elif action.kind == "move_to":
            self._player_combat_to(action.tx, action.ty)
        elif action.kind == "move":
            self._player_combat_step(action.dx, action.dy)
        elif action.kind == "use":
            # Quaffing mid-fight is a real combat choice: it SPENDS the action.
            if cs.action_used:
                self._emit(CombatEvent(text=s.flavor.combat_no_time))
            elif self._use_item(action.target_id):
                cs.action_used = True
        else:
            # A non-combat intent (talk/do/recruit/look) mid-fight: tell the player instead of
            # swallowing it silently — they typed a whole line and nothing happened. Slice-pure
            # (the line is WorldFlavor data).
            self._emit(CombatEvent(text=s.flavor.combat_no_time))
            return
        if not self._fight_enemies():
            self._end_combat(victory=True); return
        if not ended and cs.movement_left < 5:
            # No full step of movement remains: auto-end only once there's nothing left to attack either
            # (action spent, or no adjacent foe). Keeps the turn open while a bump-attack is still viable.
            adjacent_foe = any(e.pos and self._dist(s.player.pos, e.pos) == 1 for e in self._fight_enemies())
            if cs.action_used or not adjacent_foe:
                ended = True
        if ended:
            self._advance_combat_turn()
            await self._resume_combat()

    def _player_combat_step(self, dx: int, dy: int) -> None:
        """A single orthogonal step for the player in combat: bump an adjacent foe to attack it (spends
        the action), else walk one tile (spends 5 ft of movement)."""
        s = self.state
        cs = s.combat
        if abs(dx) + abs(dy) != 1:          # server authority: unit steps only (no ranged "bumps")
            return
        tx, ty = s.player.pos[0] + dx, s.player.pos[1] + dy
        foe = next((e for e in self._fight_enemies() if e.pos and tuple(e.pos) == (tx, ty)), None)
        if foe is not None:
            if not cs.action_used:
                self._attack(s.player, foe)
                cs.action_used = True
            return
        if cs.movement_left >= 5 and s.world_map.walkable(tx, ty) and not self._occupied((tx, ty), s.player.id):
            s.player.pos = (tx, ty)
            cs.movement_left -= 5
            self._recompute_fov()

    def _player_combat_to(self, tx: int, ty: int) -> None:
        """Click-to-move in combat: a foe on the tile = attack it when adjacent (else close on it); an
        empty tile = walk toward it, spending 5 ft per step until movement runs out or the path blocks.
        Stops one tile short of a foe (click the foe again to bump-attack). Movement caps the reach, so
        clicking far never teleports."""
        s = self.state
        cs = s.combat
        cell = (tx, ty)
        if f"{tx},{ty}" not in s.explored:        # same fog rule as exploration: unseen = unclickable
            return
        foe = next((e for e in self._fight_enemies() if e.pos and tuple(e.pos) == cell), None)
        if foe is not None and self._dist(s.player.pos, cell) == 1:
            if not cs.action_used:
                self._attack(s.player, foe)
                cs.action_used = True
            return
        for _ in range(40):
            if cs.movement_left < 5 or tuple(s.player.pos) == cell:
                return
            step = self._step_toward_tile(s.player.pos, cell)
            if step is None:
                return
            nx, ny = s.player.pos[0] + step[0], s.player.pos[1] + step[1]
            if any(e.pos and tuple(e.pos) == (nx, ny) for e in self._fight_enemies()):
                return                             # next cell is the foe — stop adjacent, don't walk in
            if not s.world_map.walkable(nx, ny) or self._occupied((nx, ny), s.player.id):
                return
            s.player.pos = (nx, ny)
            cs.movement_left -= 5
            self._recompute_fov()

    async def _npc_turn(self, cur) -> None:
        """Resolve one non-player combatant's whole turn — an enemy stat-block or a companion mind."""
        if self._is_enemy(cur):
            self._enemy_act(cur)
        else:
            await self._follower_act(cur)

    def _enemy_act(self, enemy) -> None:
        """A generic enemy: close on the nearest CONSCIOUS mark (up to its speed) and attack if adjacent.
        If nothing conscious remains, it finishes the nearest downed mark (a melee hit on the helpless is
        an auto-crit) — which ends the fight instead of stalling on a party that's already fallen."""
        s = self.state
        if not enemy.pos:
            return
        candidates = [s.player] + [f for f in s.followers]
        # Only ever target a mark that has a position (defensive — _dist would blow up on pos=None).
        marks = ([m for m in candidates if m.alive and m.pos]
                 or [m for m in candidates if m.down and not m.dead and m.pos])
        if not marks:
            return
        tgt = min(marks, key=lambda t: self._dist(enemy.pos, t.pos))
        for _ in range(max(1, int(getattr(enemy, "speed", 30) or 30) // 5)):
            if self._dist(enemy.pos, tgt.pos) <= 1:
                break
            before = tuple(enemy.pos)
            self._step_toward(enemy, tgt.pos)
            if tuple(enemy.pos) == before:
                break
        if self._dist(enemy.pos, tgt.pos) <= 1:
            self._attack(enemy, tgt)

    async def _follower_act(self, follower) -> None:
        """A companion's turn. Their STANCE (fight / guard / hang back / flee) is decided ONCE per fight
        by their engine mind — grounded in how they regard the traveler — and VOICED (emitted through
        `_say`, which the server synthesizes via Hume). It's the sharpest differentiator: an ally you've
        helped spends blood for you; one you've wronged won't. Executing the stance each turn is
        deterministic; only the one-time decision is a mind call."""
        s = self.state
        cs = s.combat
        if not follower.alive or not follower.pos:
            return
        stance = cs.ally_stance.get(follower.mind_slug)
        if stance is None:
            alarm = s.flavor.combat_alarm.format(enemies=_enemy_label(self._fight_enemies()))
            choice = await self.minds.act(follower.mind_slug, self._situation(follower.mind_slug, recent=[alarm]),
                ["Fight beside the traveler", "Guard the traveler", "Hang back", "Flee the fight"])
            stance = (choice.get("action") or "").lower()
            cs.ally_stance[follower.mind_slug] = stance
            self._say(follower.name, follower.mind_slug, choice.get("reason") or stance)   # voiced downstream
        foes = [e for e in self._fight_enemies() if e.pos]
        # Dispatch the HOLD stances first: "Flee the fight" CONTAINS the word "fight", so the old
        # substring test sent a fleeing ally into melee every round while they voiced refusal —
        # inverting the differentiator. A wronged ally who won't fight must actually not fight.
        holds = "flee" in stance or "hang" in stance or "guard" in stance
        if not holds and ("fight" in stance or "beside" in stance) and foes:
            tgt = min(foes, key=lambda e: self._dist(follower.pos, e.pos))
            for _ in range(max(1, int(getattr(follower, "speed", 30) or 30) // 5)):
                if self._dist(follower.pos, tgt.pos) <= 1:
                    break
                before = tuple(follower.pos)
                self._step_toward(follower, tgt.pos)
                if tuple(follower.pos) == before:
                    break
            if self._dist(follower.pos, tgt.pos) <= 1:
                self._attack(follower, tgt)
        # guard / hang back / flee -> the follower holds: a wronged ally simply won't fight for you

    def _death_save_turn(self, c) -> str:
        """A downed PC-like spends its turn on a death saving throw; narrate the swing (and the pips).
        Returns the outcome ('' if no roll happened) so the turn loop can grant a revived combatant
        their turn. Pips are ASCII (+/x) — the client's fallback font may lack check/cross glyphs."""
        res = self.combat_engine.death_save(c)
        if not res.get("rolled"):
            return ""
        outcome = res.get("outcome") or ""
        if outcome == "revive":
            self._emit(CombatEvent(text=f"{c.name} gasps back to consciousness!"))
        elif outcome == "dead":
            self._emit(CombatEvent(text=f"{c.name} goes still — gone."))
        elif outcome == "stable":
            self._emit(CombatEvent(text=f"{c.name} steadies, clinging to life."))
        else:
            self._emit(CombatEvent(
                text=f"{c.name} fights for life ({res.get('successes', 0)}+/{res.get('failures', 0)}x).",
                data={"sfx": "save"}))
        return outcome

    def _on_player_death(self) -> None:
        """Defeat is a TERMINAL state, not a stuck combat: leave combat mode, set game_over, and stop
        accepting further actions (submit_action guards on the flag). Without this the player is trapped
        in combat forever — a corpse that can still 'act' while enemies keep rolling."""
        s = self.state
        s.flags["game_over"] = True
        s.mode = Mode.exploration
        s.combat = None
        s.clock.advance(0.1)                       # credit the fight's final (partial) round of time
        self._emit(ModeChangedEvent(mode=Mode.exploration))
        self._emit(CombatEvent(text=s.flavor.defeat_text))

    def _end_combat(self, victory: bool) -> None:
        s = self.state
        # Enemy label BEFORE we leave combat, scoped to THE fight's encounter (not every encounter
        # the slice fielded — another pack across the map is none of this label's business).
        enc = self._fight_encounter()
        label = _enemy_label(list(enc.enemies) if enc is not None
                             else [en for e in s.encounters for en in e.enemies])
        # No one lies dying once the dust settles. There is no heal/rest mechanic yet, so leaving a
        # party member at 0 HP would strand a permanent ghost: unconscious forever (auto-crit bait),
        # skipped by the follow-snake, never again in an initiative order. They come to at 1 HP —
        # battered, alive, playable. A downed MINDED foe instead stabilizes where it fell: defeated
        # but alive for the story (a named adversary who survives is fuel for metamorphosis).
        for c in [s.player] + list(s.followers):
            if c.hp <= 0 and not c.dead:
                c.hp = 1
                c.stable = False
                c.death_save_successes = 0
                c.death_save_failures = 0
                if "unconscious" in c.conditions:
                    c.conditions.remove("unconscious")
                self._emit(CombatEvent(text=f"{c.name} comes to — battered, but breathing."))
        if enc is not None:
            for en in enc.enemies:
                if en.hp <= 0 and not en.dead and en.mind_slug:
                    en.stable = True
        s.mode = Mode.exploration
        s.combat = None
        # Credit the fight's final (partial) round: per-round ticks land on a wrap, but victory/defeat
        # returns before the last wrap, so a one-round skirmish would otherwise register zero elapsed
        # time. The clock is only ever differenced monotonically, so a small over-credit is harmless.
        s.clock.advance(0.1)
        self._emit(ModeChangedEvent(mode=Mode.exploration))
        if victory:
            self._emit(CombatEvent(text=s.flavor.combat_victory.format(enemies=label), data={"sfx": "victory"}))
            if enc is not None:
                self._award_victory(enc)

    def _award_victory(self, enc) -> None:
        """The mechanical SPOILS of a won fight — XP (with level-ups) and loot, all rolled by the
        rules layer (srd.progression / srd.loot), never narrated into existence. Mechanical readouts
        are guardrail-permitted (the character sheet is game-owned; only the MIND is private)."""
        from .srd import loot as srd_loot
        from .srd import progression
        s = self.state
        if not enc.enemies:                        # a degenerate empty encounter pays nothing
            return
        # Per-enemy CR (a hand-authored foe without one defaults to 0.25 INDIVIDUALLY, so a mixed
        # bestiary+authored pack pays for every combatant, not just the stat-blocked ones).
        crs = [float(en.cr) if en.cr is not None else 0.25 for en in enc.enemies]
        xp = progression.xp_for_crs(crs)
        if xp > 0:
            ups = progression.award_xp(s.player, xp)
            self._emit(CombatEvent(text=f"Hard-won: {xp} exp."))
            for up in ups:
                self._emit(CombatEvent(
                    text=f"You've grown — level {up['level']} (+{up['hp_gain']} HP).", data={"sfx": "levelup"}))
        spoils = srd_loot.roll_loot(crs, self.rules.rng)
        if spoils.get("gold"):
            s.player.gold += int(spoils["gold"])
        from .state import Item
        for it in spoils.get("items", []):
            s.player.inventory.append(Item(id=it["id"], name=it["name"],
                                           kind=it.get("kind", "misc"), data=it.get("data", {})))
        if spoils.get("trinket"):
            # truncate BEFORE stripping so a cut at a dash can't leave a trailing '-' run
            tid = "".join(c if c.isalnum() else "-" for c in spoils["trinket"].lower())[:40].strip("-")
            s.player.inventory.append(Item(id=tid or "trinket", name=spoils["trinket"], kind="misc"))
        desc = srd_loot.describe(spoils)
        if desc:
            self._emit(CombatEvent(text=f"Among the fallen: {desc}.", data={"sfx": "loot"}))
            s.campaign_log.add(s.clock.value, f"The traveler claimed {desc}.", tags=["loot"])
