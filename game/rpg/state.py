"""Renderer-agnostic game state (Pydantic v2) for the SRD-based (d20-system) RPG game-core.

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
    # Attack PROFILE — data, not hard-coded in the loop, so a slice can field a brute (1d12 STR), an
    # archer (1d6 DEX), a biter (1d4), etc. The combat loop reads these; it names no dice itself.
    damage_dice: str = "1d4"
    attack_ability: str = "STR"
    damage_type: str = ""                    # "slashing" | "piercing" | "fire" | ... ('' = untyped)
    # --- 5e sheet (SRD-based rules system) — all optional so existing content stays valid. The
    # srd.mechanics functions read these; monsters set `cr`, characters use `level` (subclass). ---
    saving_throw_profs: list[str] = Field(default_factory=list)   # abilities proficient in saves
    skill_profs: list[str] = Field(default_factory=list)          # proficient skills
    expertise: list[str] = Field(default_factory=list)            # skills with DOUBLE proficiency
    resistances: list[str] = Field(default_factory=list)          # damage types taken at half
    immunities: list[str] = Field(default_factory=list)           # damage types ignored
    vulnerabilities: list[str] = Field(default_factory=list)      # damage types taken double
    condition_immunities: list[str] = Field(default_factory=list)
    speed: int = 30                          # feet per turn
    size: str = "medium"                     # tiny | small | medium | large | huge | gargantuan
    creature_type: str = ""                  # humanoid | undead | beast | construct | ...
    cr: float | None = None                  # monster Challenge Rating (drives PB + XP); None = uses level
    hit_dice: str = ""                       # e.g. "2d6" — for HP generation
    prof_bonus: int | None = None            # explicit proficiency-bonus override (else from level/cr)
    # --- combat status (turn-based engine, srd.combat) ---
    dead: bool = False                       # truly dead (vs unconscious at 0 HP making death saves)
    death_save_successes: int = 0            # 0-3; 3 -> stable
    death_save_failures: int = 0             # 0-3; 3 -> dead
    stable: bool = False                     # unconscious but no longer rolling death saves

    @property
    def alive(self) -> bool:
        """Can act this turn: has HP and isn't dead. An unconscious PC at 0 HP is NOT 'alive' for
        acting (they make death saves), but is not `dead` either."""
        return self.hp > 0 and not self.dead

    @property
    def down(self) -> bool:
        """At 0 HP or dead — out of the fight for now (may still be revivable if not `dead`)."""
        return self.hp <= 0 or self.dead


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
    on_recruit_grant: Item | None = None     # item this NPC hands the player IF they choose to join
    on_recruit_line: str = ""                # what they say handing it over (their voice, not the DM's)
    # The SOCIAL GATE on asking them to join (owner design: companionship is earned through
    # conversation, not commanded). These gate the ASK's availability — an observable world fact
    # (how much you've actually talked; an optional quest flag) — never the mind's ANSWER, which
    # stays the engine's to make. A guarded character needs more talk than a warm one (data).
    recruit_min_talks: int = 2               # real exchanges required before a join ask lands
    recruit_requires_flag: str = ""          # optional quest/world flag that must be set ('' = none)


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


class Door(BaseModel):
    """An interactive world feature that blocks a cell until opened. A locked door needs a specific
    key item in the player's inventory — that gating is GAME-enforced, never the DM's to hand-wave.
    All narration is DATA (authored per slice) so the core substitutes text without naming keystones,
    stairs, or a Vault: a slice's 'door' could be a warded gate, a sealed airlock, or a barred hatch."""
    id: str
    pos: Pos
    name: str = "a heavy door"
    locked: bool = True
    key_item: str = ""                        # item id that opens it ('' = openable by hand)
    force_dc: int = 18                        # STR DC to force it WITHOUT the key (0 = unforceable)
    opens_quest: str = ""                     # quest id this door completes when opened
    open_text: str = ""                       # narrated when it opens with the key (falls back generic)
    locked_text: str = ""                     # narrated when it won't budge without the key
    force_text: str = ""                      # narrated when it's forced open by a STR check
    outro: str = ""                           # optional slice-completion line emitted after it opens


class CombatState(BaseModel):
    round: int = 1
    order: list[str] = Field(default_factory=list)   # combatant ids in initiative order
    turn_index: int = 0
    # THE fight is one encounter's: victory / targeting / labels scope to this encounter, so a slice
    # with several encounters never demands killing never-triggered enemies across the map.
    encounter_id: str = ""
    show_enemy_hp: bool = False               # player-toggle — mechanical readout is allowed (guardrail #5)
    ally_stance: dict[str, str] = Field(default_factory=dict)   # mind_slug -> chosen stance (decided ONCE / fight)
    # per-turn action economy (reset at the start of each combatant's turn)
    action_used: bool = False
    bonus_used: bool = False
    movement_left: int = 0                     # feet of movement remaining this turn
    reacted: dict[str, bool] = Field(default_factory=dict)   # id -> used its reaction this round

    def current(self) -> str | None:
        return self.order[self.turn_index] if self.order else None


class WorldFlavor(BaseModel):
    """Per-SLICE narrative flavor the CORE reads instead of authoring any prose itself. This is what
    lets an entirely different slice (biome, enemies, objective) be built as pure DATA: the game-core
    never says 'the Sunken Vault' or 'goblins' — it interpolates from here. `{enemies}` in the combat
    lines is filled with the live encounter's enemy label so a slice never mis-names its foes.

    All fields default to a neutral dungeon so an un-flavored slice still reads sensibly."""
    theme: str = "a dark place"                           # short tag, e.g. "the Sunken Vault"
    world_frame: str = ("You are in a dangerous place of stone and shadow, no easy way out. This is a "
                        "world of blades and lantern-light, not of any modern place.")  # fed to each NPC mind
    location_label: str = "a dark chamber"                # Situation.location for the minds
    time_label: str = "in the dark"                       # Situation.game_time (display only)
    scene_prose: str = "The player stands in the dark, a guttering torch the only light."  # base the DM narrates from
    dm_setting: str = "a grim, torch-lit dungeon crawl"   # one-line setting the DM system prompt keys off
    combat_start: str = ("Steel rings out — {enemies} rush from the dark! "
                         "(move into one to attack · g: toggle their HP)")
    combat_victory: str = "The {enemies} are down. Quiet settles back over the dark."
    combat_alarm: str = "{enemies} have set on the traveler — steel is out in the dark."  # recent-event to allies
    recruit_prompt: str = "The traveler asks you to come with them, deeper into the dark."  # recent-event on recruit
    defeat_text: str = "You fall in the dark, and it closes over you. Your story ends here. (press q to quit)"
    combat_no_time: str = "No time for that — steel is out."   # feedback for a non-combat action mid-fight
    force_noise: str = "The clamor rings out into the dark."   # a failed door-forcing draws attention
    rest_text: str = "You make a cold camp and take what rest the dark allows."   # narrated on a rest
    rest_ambush: str = "Something heard you settle — shapes move at the edge of the light."  # rest drew danger
    # Baseline VOICE acting direction for the scene (Hume Octave `description`, <=100 chars):
    # without it, a line with no stage business of its own reads neutral-natural — nothing told
    # the voice it was standing in a dungeon (owner-heard 2026-07-09). A line's own tags/business
    # still override this; it is the floor, not the ceiling.
    voice_mood: str = "speaking low and wary, tension under the words, alert to the dark around"


class GameState(BaseModel):
    """The whole durable WORLD state — the save/load target. The MIND is NOT here (each engine
    character auto-persists its own memory). This model is game-owned and never touches the mind
    store."""
    mode: Mode = Mode.exploration
    clock: GameClock = Field(default_factory=GameClock)
    flavor: WorldFlavor = Field(default_factory=WorldFlavor)   # per-slice prose the core reads (never authors)
    player: PlayerCharacter
    world_map: WorldMap
    npcs: list[NpcPlacement] = Field(default_factory=list)
    followers: list[Follower] = Field(default_factory=list)
    encounters: list[Encounter] = Field(default_factory=list)
    doors: list[Door] = Field(default_factory=list)
    quests: list[QuestThread] = Field(default_factory=list)
    flags: dict[str, bool] = Field(default_factory=dict)   # game/quest flags (e.g. inner_door_open)
    talk_counts: dict[str, int] = Field(default_factory=dict)  # slug -> real exchanges (the recruit gate reads this)
    explored: set[str] = Field(default_factory=set)        # "x,y" tiles the player has ever seen (fog of war)
    campaign_log: CampaignLog = Field(default_factory=CampaignLog)
    combat: CombatState | None = None

    def has_item(self, item_id: str) -> bool:
        return any(it.id == item_id for it in self.player.inventory)

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
    # combat readout (mechanical, allowed): who's down + their death-save pips (shown for a downed
    # follower/PC-like so the view can draw ✓/✗ tallies). 0/False out of combat or when up.
    down: bool = False
    death_successes: int = 0
    death_failures: int = 0


class StateSnapshot(BaseModel):
    """What `GameSession.get_state()` hands a renderer — a RENDERABLE projection of `GameState`.
    Excludes the mind entirely (guardrail #5: no psychological readout — feelings are felt through
    behavior/dialogue/voice). Mechanical stats only."""
    mode: Mode
    clock: float
    player: PlayerCharacter
    objective: str = ""
    inventory: list[str] = Field(default_factory=list)
    map_width: int
    map_height: int
    tiles: list[str]
    entities: list[EntityView] = Field(default_factory=list)
    combat_order: list[str] = Field(default_factory=list)
    combat_turn: str | None = None            # id of the combatant acting right now (None out of combat)
    combat_round: int = 0                     # 1-based round counter (0 out of combat)
    combat_movement: int = 0                  # feet of movement the current combatant has left
    combat_action_used: bool = False          # has the current combatant spent its action this turn
    show_enemy_hp: bool = False
    visible: list[str] = Field(default_factory=list)       # "x,y" tiles lit right now (fog of war)
    explored: list[str] = Field(default_factory=list)      # "x,y" tiles ever seen (dim, remembered)
