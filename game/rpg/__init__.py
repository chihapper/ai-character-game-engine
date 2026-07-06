"""`game/rpg/` — the renderer-agnostic Python game-core for the D&D-style AI-DM RPG.

Drives the character engine (the MIND) through its public seam; owns the WORLD. Built and proven
once with a disposable tcod dev view (Phase A), then rendered by a Godot 4.x native desktop client
over local IPC (Phase B) — the logic never changes, only the thin renderer.

See docs/godot-game-build-plan.md (the spec) and docs/godot-build-step0-inspection.md.

Current scaffold (Phase A, steps 1-2): the renderer-agnostic state model, the deterministic rules
core, and the `GameSession` boundary. Still to come: characters (reskinned from the tuned cast),
engine integration (one Engine per named NPC, depth flags via per-Engine caps override), the DM
orchestrator, procedural dungeon gen, the tcod dev view, and world save/load.
"""
from __future__ import annotations

from .minds import Minds, full_depth_caps, reskin
from .rules import AttackResult, CheckResult, D20Rules, RulesEngine
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
]
