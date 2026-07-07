"""`game/rpg/` — the renderer-agnostic Python game-core for the SRD-based (d20-system) AI-DM RPG.

Drives the character engine (the MIND) through its public seam; owns the WORLD. Built and proven
once with a disposable tcod dev view (Phase A), then rendered by a Godot 4.x native desktop client
over local IPC (Phase B) — the logic never changes, only the thin renderer.

See docs/godot-game-build-plan.md (the spec) and docs/godot-build-step0-inspection.md.

Current state: Phase A complete (state model, rules core, reskinned cast, engine integration —
one Engine per named NPC with a per-Engine caps override — GM narrator, procedural dungeon gen,
tcod dev view); Phase B live (local WebSocket server + Godot 4.7 client: sprites, portrait speech
card, streamed Hume voice, synthesized SFX/ambience); ALL SIX SRD rules phases wired (mechanics,
turn-based combat, bestiary, encounter scaling, loot, progression to level 6); world autosave +
resume live (.saves/<slice>-<seed>.json via game/rpg/server.py); recruit-through-conversation,
camp rest, and GM-narrated stage directions shipped. Known-deferred RAW/equip/ranged items are
task-tracked.
"""
from __future__ import annotations

from .content import build_first_slice, characters
from .dungeon import Dungeon, generate_dungeon, render_ascii
from .game import RpgGame
from .minds import Minds, full_depth_caps, reskin
# AttackResult lives in srd.combat now (rules.py's combat members were superseded + deleted).
from .rules import CheckResult, D20Rules, RulesEngine
from .srd.combat import AttackResult
from .session import (
    CombatEvent,
    DialogueEvent,
    GameEvent,
    GameSession,
    MapUpdateEvent,
    ModeChangedEvent,
    NarrationEvent,
    PlayerAction,
    StateChangedEvent,
)
from .state import (
    ABILITIES,
    CampaignLog,
    Combatant,
    CombatState,
    Encounter,
    Enemy,
    EntityView,
    Follower,
    GameClock,
    GameState,
    Item,
    Mode,
    NpcPlacement,
    PlayerCharacter,
    QuestThread,
    Stats,
    StateSnapshot,
    WorldMap,
)

__all__ = [
    # state
    "ABILITIES", "Mode", "Stats", "Item", "Combatant", "PlayerCharacter", "Follower", "Enemy",
    "NpcPlacement", "Encounter", "QuestThread", "CampaignLog", "GameClock", "WorldMap",
    "CombatState", "GameState", "EntityView", "StateSnapshot",
    # rules
    "RulesEngine", "D20Rules", "CheckResult", "AttackResult",
    # session
    "GameSession", "PlayerAction", "GameEvent", "NarrationEvent", "DialogueEvent",
    "MapUpdateEvent", "CombatEvent", "ModeChangedEvent", "StateChangedEvent",
    # minds (engine integration)
    "Minds", "reskin", "full_depth_caps",
    # dungeon + content
    "Dungeon", "generate_dungeon", "render_ascii", "build_first_slice", "characters",
    # core loop
    "RpgGame",
]
