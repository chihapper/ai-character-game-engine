"""Local WebSocket session server — the Phase B IPC seam.

Godot connects here and drives the SAME `RpgGame` GameSession the tcod dev view drove in-process.
All game logic + the engine stay in Python; Godot is a pure renderer over the wire. One connection =
one game. Each client message yields a batch of server messages that always ENDS with a `snapshot`.

    .venv/Scripts/python.exe -m game.rpg.server        # ws://127.0.0.1:8787
Env: RPG_HOST (127.0.0.1), RPG_PORT (8787), RPG_MODEL (claude-haiku-4-5).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")

import websockets  # noqa: E402

from .game import RpgGame  # noqa: E402
from .protocol import (  # noqa: E402
    ActionMsg,
    DeedMsg,
    StartMsg,
    StateReqMsg,
    error_msg,
    event_msg,
    parse_client,
    snapshot_msg,
)


class RpgConnection:
    """One connected client's session. Holds the game; each `handle` returns the server messages to
    send back (drained events, then the fresh snapshot)."""

    def __init__(self, *, reply_model: str | None = None, dm_model: str | None = None) -> None:
        self.reply_model = reply_model
        self.dm_model = dm_model
        self.game: RpgGame | None = None

    async def handle(self, data: dict) -> list[dict]:
        msg = parse_client(data)                     # raises ValidationError on a bad shape
        if isinstance(msg, StartMsg):
            self.game = RpgGame.new(slice=msg.slice, seed=msg.seed,
                                    reply_model=self.reply_model, dm_model=self.dm_model)
            await self.game.begin()                  # the world speaks first
            return self._drain() + [snapshot_msg(self.game.get_state())]
        if self.game is None:
            return [error_msg("send a 'start' message before anything else")]
        if isinstance(msg, StateReqMsg):
            return [snapshot_msg(self.game.get_state())]
        if isinstance(msg, ActionMsg):
            await self.game.submit_action(msg.action)
        elif isinstance(msg, DeedMsg):
            await self.game.remember_player_deed(msg.fact, targets=msg.targets,
                                                 player_role=msg.player_role, magnitude=msg.magnitude)
        return self._drain() + [snapshot_msg(self.game.get_state())]

    def _drain(self) -> list[dict]:
        return [event_msg(ev) for ev in self.game.drain_events()]


async def serve(host: str = "127.0.0.1", port: int = 8787, *,
                reply_model: str | None = None, dm_model: str | None = None) -> None:
    async def handler(ws) -> None:
        conn = RpgConnection(reply_model=reply_model, dm_model=dm_model)
        async for raw in ws:
            try:
                outs = await conn.handle(json.loads(raw))
            except Exception as e:                    # never drop the connection on one bad message
                outs = [error_msg(f"{type(e).__name__}: {e}")]
            for o in outs:
                await ws.send(json.dumps(o))

    async with websockets.serve(handler, host, port, max_size=2 ** 22):
        print(f"[rpg-server] listening on ws://{host}:{port}  (one game per connection)")
        await asyncio.Future()                        # run forever


def main() -> None:
    host = os.environ.get("RPG_HOST", "127.0.0.1")
    port = int(os.environ.get("RPG_PORT", "8787"))
    model = os.environ.get("RPG_MODEL", "claude-haiku-4-5")
    asyncio.run(serve(host, port, reply_model=model, dm_model=model))


if __name__ == "__main__":
    main()
