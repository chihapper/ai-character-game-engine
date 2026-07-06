"""Renderer-agnostic game state (Pydantic v2) for the D&D-style RPG game-core.

Pure DATA — no pixels, no rendering, and NO engine imports. Both the tcod dev view (Phase A)
and the Godot client (Phase B) consume this through `GameSession`. The engine owns the MIND;
these models are the WORLD the game owns (see docs/engine-game-contract.md and
docs/godot-game-build-plan.md). The character MIND is never stored here — each engine character
auto-persists at `.memory/<slug>.jsonl`; the game persists this WORLD state separately.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

Pos = tuple[int, int]
ABILITIES: tuple[str, ...] = ("STR", "DEX", "CON", "INT", "WIS", "CHA")


class Mode(str, Enum):
    exploration = "exploration"   # free-flow real-time default
    combat = "combat"             # turn-based, entered on encounter/aggression


class Stats(BaseModel):
    STR: int = 10
    DEX: int = 10
    CON: int = 10
    INT: int = 10
    WIS: int = 10
    CHA: int = 10

    def mod(self, ability: str) -> int:
        """The d20 ability modifier: (score - 10) // 2."""
        return (getattr(self, ability.upper()) - 10) // 2


class Item(BaseModel):
    id: str
    name: str
    kind: str = "misc"                       # weapon | armor | consumable | key | misc
    data: dict = Field(default_factory=dict)  # kind-specific (damage_dice, ac, ...)


class Combatant(BaseModel):
    """The GAME-owned character SHEET — mechanical stats that can fight (player, follower, enemy).
    NEVER the mind. A named NPC additionally has an Engine keyed by `mind_slug`; a generic enemy
    leaves it None (a pure stat-block, no persistent psychology — for cost and scale)."""
    id: str
    name: str
    max_hp: int = 1
    hp: int = 1
    ac: int = 10
    stats: Stats = Field(default_factory=Stats)
    conditions: list[str] = Field(default_factory=list)
    pos: Pos | None = None
    initiative: int | None = None
    mind_slug: str | None = None             # engine character slug IF this combatant has a mind

    @property
    def alive(self) -> bool:
        return self.hp > 0


class PlayerCharacter(Combatant):
    level: int = 1
    xp: int = 0
    gold: int = 0
    skills: dict[str, int] = Field(default_factory=dict)
    inventory: list[Item] = Field(default_factory=list)


class Follower(Combatant):
    """A companion NPC in the party — MECHANICAL stats for the party UI (HP, conditions). Its
    MIND still lives in its Engine, so `mind_slug` is always set for a follower."""


class Enemy(Combatant):
    """A hostile combatant. Generic ones are pure stat-blocks (`mind_slug` None); a named/recurring
    adversary is promoted to an Engine mind by setting `mind_slug`."""
    kind: str = "enemy"                      # "goblin", "bandit", ...


class NpcPlacement(BaseModel):
    """A named engine-character placed in the world (its mind lives in an Engine keyed by `slug`).
    `game_data` is the open, namespaced bag the engine stores but never interprets
    (register_game_extension) — world role, faction, disposition-to-others, etc."""
    slug: str
    name: str
    handle: str = ""                         # how strangers refer to them before a name is learned
    pos: Pos | None = None
    game_data: dict = Field(default_factory=dict)


class Encounter(BaseModel):
    id: str
    enemies: list[Enemy] = Field(default_factory=list)
    trigger_pos: Pos | None = None           # step here (or into `region`) to spring it
    region: str = ""
    triggered: bool = False


class QuestThread(BaseModel):
    id: str
    title: str
    state: str = "open"                      # open | active | done | failed
    notes: list[str] = Field(default_factory=list)


class CampaignEvent(BaseModel):
    """One entry in the DM's lightweight campaign log — memory WITHOUT being a character."""
    t: float
    text: str
    tags: list[str] = Field(default_factory=list)


class CampaignLog(BaseModel):
    """The DM orchestrator's own memory: a simple keyword/recency log over WORLD events, so it can
    call back ('the crossroads where you spared the bandit'). Deliberately NOT the engine's RR
    memory — that is per-character and lives in each mind."""
    events: list[CampaignEvent] = Field(default_factory=list)

    def add(self, t: float, text: str, tags: list[str] | None = None) -> None:
        self.events.append(CampaignEvent(t=t, text=text, tags=tags or []))

    def recent(self, n: int = 8) -> list[CampaignEvent]:
        return self.events[-n:]

    def search(self, keyword: str, limit: int = 5) -> list[CampaignEvent]:
        k = keyword.lower()
        hits = [e for e in reversed(self.events) if k in e.text.lower()]
        return hits[:limit]


class GameClock(BaseModel):
    """The game's own OPAQUE unit; the engine only DIFFERENCES it (temporal decay, issue #5).
    Advances in narrative time during exploration and in rounds during combat."""
    value: float = 0.0

    def advance(self, dt: float) -> float:
        self.value += dt
        return self.value


class WorldMap(BaseModel):
    """A tile grid behind ONE model — the map-source abstraction feeds both a PROCEDURAL generator
    (dungeons) and AUTHORED maps (towns) here, so the renderer + core don't care which. Terrain
    only; movable entities live in `GameState`."""
    width: int
    height: int
    tiles: list[str]                         # `height` rows of `width` chars: '#' wall '.' floor '+' door '>' '<' stairs
    seed: int | None = None
    source: str = "procedural"               # procedural | authored
    stairs_down: Pos | None = None
    stairs_up: Pos | None = None

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def tile(self, x: int, y: int) -> str:
        return self.tiles[y][x] if self.in_bounds(x, y) else "#"

    def walkable(self, x: int, y: int) -> bool:
        return self.tile(x, y) in (".", "+", ">", "<")


class CombatState(BaseModel):
    round: int = 1
    order: list[str] = Field(default_factory=list)   # combatant ids in initiative order
    turn_index: int = 0
    show_enemy_hp: bool = False               # player-toggle — mechanical readout is allowed (guardrail #5)

    def current(self) -> str | None:
        return self.order[self.turn_index] if self.order else None


class GameState(BaseModel):
    """The whole durable WORLD state — the save/load target. The MIND is NOT here (each engine
    character auto-persists its own memory). This model is game-owned and never touches the mind
    store."""
    mode: Mode = Mode.exploration
    clock: GameClock = Field(default_factory=GameClock)
    player: PlayerCharacter
    world_map: WorldMap
    npcs: list[NpcPlacement] = Field(default_factory=list)
    followers: list[Follower] = Field(default_factory=list)
    encounters: list[Encounter] = Field(default_factory=list)
    quests: list[QuestThread] = Field(default_factory=list)
    campaign_log: CampaignLog = Field(default_factory=CampaignLog)
    combat: CombatState | None = None

    # --- save/load (WORLD only; never the mind store) ---
    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, data: str) -> "GameState":
        return cls.model_validate_json(data)


class EntityView(BaseModel):
    """A renderable entity in a `StateSnapshot` — id/name/pos/kind, plus hp ONLY when the game
    allows it (follower HP always; enemy HP only when `show_enemy_hp`). NEVER psychological state."""
    id: str
    name: str
    pos: Pos | None
    kind: str                                 # player | npc | follower | enemy
    hp: int | None = None
    max_hp: int | None = None


class StateSnapshot(BaseModel):
    """What `GameSession.get_state()` hands a renderer — a RENDERABLE projection of `GameState`.
    Excludes the mind entirely (guardrail #5: no psychological readout — feelings are felt through
    behavior/dialogue/voice). Mechanical stats only."""
    mode: Mode
    clock: float
    player: PlayerCharacter
    map_width: int
    map_height: int
    tiles: list[str]
    entities: list[EntityView] = Field(default_factory=list)
    combat_order: list[str] = Field(default_factory=list)
    combat_turn: str | None = None
    show_enemy_hp: bool = False
