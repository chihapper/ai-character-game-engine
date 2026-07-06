"""The `GameSession` interface + the event / action types — the ONE boundary both renderers
consume: in-process for the tcod dev view (Phase A), over local IPC for the Godot client
(Phase B). The game-core never knows which renderer is attached, and never emits pixels — only
DATA. `get_state()` returns a renderable snapshot; `submit_action()` takes player intent;
`events()` streams what happened.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Literal

from pydantic import BaseModel, Field

from .state import Mode, StateSnapshot


# ---- player intent (from the view) --------------------------------------------
class PlayerAction(BaseModel):
    """One intent from the view. `kind` selects the fields that matter; the core validates per
    kind. Free-flow in exploration; one action per turn in combat."""
    kind: Literal["move", "talk", "recruit", "do", "look", "attack", "use", "wait", "toggle_enemy_hp", "advance"]
    dx: int = 0                  # move
    dy: int = 0
    target_id: str = ""          # talk / attack / use-on
    text: str = ""               # the player's spoken line (talk) or free-form action text
    item_id: str = ""            # use


# ---- events (to the view) -----------------------------------------------------
class GameEvent(BaseModel):
    type: str


class NarrationEvent(GameEvent):
    """DM narration — the world's voice (text in the MVP)."""
    type: Literal["narration"] = "narration"
    text: str


class DialogueEvent(GameEvent):
    """An NPC line — spoken by that NPC's `Engine.respond`, NOT the DM. `audio` is optional
    Hume-voiced PCM the renderer plays (in-process only; over IPC audio rides a side channel)."""
    type: Literal["dialogue"] = "dialogue"
    npc: str                     # display name
    slug: str
    text: str
    audio: bytes | None = None


class MapUpdateEvent(GameEvent):
    type: Literal["map_update"] = "map_update"


class CombatEvent(GameEvent):
    type: Literal["combat"] = "combat"
    text: str
    data: dict = Field(default_factory=dict)


class ModeChangedEvent(GameEvent):
    type: Literal["mode_changed"] = "mode_changed"
    mode: Mode


class StateChangedEvent(GameEvent):
    type: Literal["state_changed"] = "state_changed"


class GameSession(ABC):
    """The linchpin that makes the renderer swappable. Both the tcod view and the Godot client
    consume exactly this — never the core's internals."""

    @abstractmethod
    def get_state(self) -> StateSnapshot:
        """A renderable projection of world state (mechanical only — no mind)."""

    @abstractmethod
    async def submit_action(self, action: PlayerAction) -> None:
        """Apply a player intent. Drives world state + (for talk/consequences) the NPC engines."""

    @abstractmethod
    def events(self) -> AsyncIterator[GameEvent]:
        """An async stream of narration / dialogue / map / combat / mode events for the view."""
