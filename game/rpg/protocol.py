"""The Godot <-> Python wire protocol — one JSON contract both ends target.

Transport is a local WebSocket (see `server.py`); this module owns only the MESSAGE SHAPES, so the
core stays transport-agnostic (swap to stdio/pipes later without touching game logic). Every message
is a JSON object with a `t` (type) tag.

  Client -> Server:  start | action | deed | state
  Server -> Client:  snapshot | event | voice | error

`snapshot` carries a full `StateSnapshot` (mechanical only — no mind readout, guardrail #5). `event`
carries one game event (narration / dialogue / combat / mode_changed / state_changed). A batch of
server messages always ENDS with a `snapshot`, so a client can read until it sees one.

`voice` rides OUTSIDE the batch: dialogue TEXT goes out immediately with its batch, and the Hume
audio for each line follows as its own `voice` message once synthesis finishes (in spoken order) —
so the world never freezes waiting on TTS. A client that ignores `voice` is simply silent.
"""
from __future__ import annotations

import base64
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

from .session import GameEvent, PlayerAction
from .state import StateSnapshot


# ---- Client -> Server -----------------------------------------------------------------------------
class StartMsg(BaseModel):
    """Begin (or restart) a game with a named slice + seed. Server replies with the opening events
    and the first snapshot. `resume=True` continues from the saved WORLD state for this slice+seed
    if one exists (minds persist on their own); `resume=False` always starts a fresh expedition."""
    t: Literal["start"] = "start"
    slice: str = "vault"
    seed: int = 1337
    resume: bool = False


class ActionMsg(BaseModel):
    """Apply one player intent (move / talk / recruit / do / look / wait / toggle_enemy_hp)."""
    t: Literal["action"] = "action"
    action: PlayerAction


class DeedMsg(BaseModel):
    """A consequential player deed toward named NPCs (the 'help/free/rob' seam the tcod view's 'f'
    key uses) — world->mind, then the reaction recipe runs game-side."""
    t: Literal["deed"] = "deed"
    fact: str
    targets: list[str]
    player_role: str = "caused"
    magnitude: float = 0.6


class StateReqMsg(BaseModel):
    """Ask for a fresh snapshot without changing anything."""
    t: Literal["state"] = "state"


ClientMsg = Annotated[Union[StartMsg, ActionMsg, DeedMsg, StateReqMsg], Field(discriminator="t")]
_client_adapter: TypeAdapter = TypeAdapter(ClientMsg)


def parse_client(data: dict):
    """Validate + parse an inbound client message (raises pydantic ValidationError on a bad shape)."""
    return _client_adapter.validate_python(data)


# ---- Server -> Client -----------------------------------------------------------------------------
def snapshot_msg(snap: StateSnapshot) -> dict:
    # mode="json" coerces enums -> values and tuples -> lists, so json.dumps never chokes.
    return {"t": "snapshot", "snapshot": snap.model_dump(mode="json")}


def event_msg(ev: GameEvent) -> dict:
    # `audio` (raw PCM on an in-process DialogueEvent) is excluded from JSON; over the wire the
    # voice for a dialogue line follows as its own `voice` message (see voice_msg below) so the
    # TEXT is never held back by synthesis.
    return {"t": "event", "event": ev.model_dump(mode="json", exclude={"audio"})}


def voice_msg(*, slug: str, npc: str, pcm: bytes, rate: int) -> dict:
    """The Hume audio for one already-delivered dialogue line — sent as a follow-up, outside the
    action batch. base64 PCM (s16le mono); the client sizes its inbound buffer for this (8 MiB)."""
    return {"t": "voice", "slug": slug, "npc": npc,
            "audio_b64": base64.b64encode(pcm).decode("ascii"), "rate": int(rate)}


def error_msg(message: str) -> dict:
    return {"t": "error", "message": message}
