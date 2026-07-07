"""Local WebSocket session server — the Phase B IPC seam.

Godot connects here and drives the SAME `RpgGame` GameSession the tcod dev view drove in-process.
All game logic + the engine stay in Python; Godot is a pure renderer over the wire. One connection =
one game. Each client message yields a batch of server messages that always ENDS with a `snapshot`
(errors included — the batch invariant holds on every path once a game exists).

WORLD persistence: the world autosaves to `.saves/<slice>-<seed>.json` after each action (in
exploration only — never mid-combat), and a `start` with `resume=true` continues from that save.
Minds persist on their own (each engine character owns its memory namespace); in-flight reflections
are flushed when the connection closes.

    .venv/Scripts/python.exe -m game.rpg.server        # ws://127.0.0.1:8787
Env: RPG_HOST (127.0.0.1), RPG_PORT (8787), RPG_MODEL (claude-haiku-4-5),
     RPG_VOICE (1; 0 = text-only even with a Hume key).
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path

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
from .state import GameState, Mode  # noqa: E402
from .voice import synth_line  # noqa: E402

SAVE_DIR = Path(".saves")


def _save_path(slice_name: str, seed: int) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in slice_name)
    return SAVE_DIR / f"{safe}-{seed}.json"


class RpgConnection:
    """One connected client's session. Holds the game; each `handle` returns the server messages to
    send back (drained events, then the fresh snapshot)."""

    def __init__(self, *, reply_model: str | None = None, dm_model: str | None = None,
                 voice: bool = False) -> None:
        self.reply_model = reply_model
        self.dm_model = dm_model
        self.voice = voice
        self.game: RpgGame | None = None
        self._save_to: Path | None = None            # set on start; autosave target for this session

    def _load_save(self, msg: StartMsg) -> GameState | None:
        """The saved world for this slice+seed, or None (missing / unreadable — fall back to fresh)."""
        p = _save_path(msg.slice, msg.seed)
        if not p.exists():
            return None
        try:
            return GameState.from_json(p.read_text(encoding="utf-8"))
        except Exception as exc:                     # noqa: BLE001 — a corrupt save must not brick starts
            print(f"[rpg-server] ignoring unreadable save {p}: {exc}")
            return None

    def _autosave(self) -> None:
        """Persist the WORLD after a handled message — exploration only (never a mid-combat or
        game-over snapshot), best-effort (a full disk must not kill the session)."""
        g = self.game
        if g is None or self._save_to is None:
            return
        if g.state.mode != Mode.exploration or g.state.flags.get("game_over"):
            return
        try:
            self._save_to.parent.mkdir(parents=True, exist_ok=True)
            self._save_to.write_text(g.state.to_json(), encoding="utf-8")
        except Exception as exc:                     # noqa: BLE001
            print(f"[rpg-server] autosave failed: {exc}")

    async def handle(self, data: dict) -> list[dict]:
        msg = parse_client(data)                     # raises ValidationError on a bad shape
        if isinstance(msg, StartMsg):
            self._save_to = _save_path(msg.slice, msg.seed)
            loaded = self._load_save(msg) if msg.resume else None
            if loaded is not None:
                self.game = RpgGame.resume(slice=msg.slice, seed=msg.seed, state=loaded,
                                           reply_model=self.reply_model, dm_model=self.dm_model)
            else:
                self.game = RpgGame.new(slice=msg.slice, seed=msg.seed,
                                        reply_model=self.reply_model, dm_model=self.dm_model)
            await self.game.begin()                  # the world speaks first (recaps on a resume)
            return await self._emit_events() + [snapshot_msg(self.game.get_state())]
        if self.game is None:
            return [error_msg("send a 'start' message before anything else")]
        if isinstance(msg, StateReqMsg):
            return [snapshot_msg(self.game.get_state())]
        if isinstance(msg, ActionMsg):
            await self.game.submit_action(msg.action)
        elif isinstance(msg, DeedMsg):
            await self.game.remember_player_deed(msg.fact, targets=msg.targets,
                                                 player_role=msg.player_role, magnitude=msg.magnitude)
        self._autosave()
        return await self._emit_events() + [snapshot_msg(self.game.get_state())]

    async def recover(self, err: Exception) -> list[dict]:
        """The error batch STILL honors the ends-with-a-snapshot invariant (and drains any events
        queued before the exception into THIS batch, not the next action's) — otherwise the client's
        world view goes stale and orphaned events get misattributed."""
        outs: list[dict] = []
        try:
            if self.game is not None:
                outs += await self._emit_events()
        except Exception:                            # noqa: BLE001 — recovery must not raise
            pass
        outs.append(error_msg(f"{type(err).__name__}: {err}"))
        try:
            if self.game is not None:
                outs.append(snapshot_msg(self.game.get_state()))
        except Exception:                            # noqa: BLE001
            pass
        return outs

    async def _emit_events(self) -> list[dict]:
        """Serialize the queued events, and (if voice is on) synthesize Hume audio for each NPC line,
        attaching it as base64 PCM + sample rate. Voice is best-effort — a synth failure just yields a
        text-only dialogue event."""
        out: list[dict] = []
        for ev in self.game.drain_events():
            msg = event_msg(ev)
            e = msg["event"]
            if self.voice and e.get("type") == "dialogue" and (e.get("text") or "").strip():
                pcm, rate = await synth_line(e["text"], e.get("slug", ""))
                if pcm:
                    e["audio_b64"] = base64.b64encode(pcm).decode("ascii")
                    e["rate"] = rate
            out.append(msg)
        return out


async def serve(host: str = "127.0.0.1", port: int = 8787, *,
                reply_model: str | None = None, dm_model: str | None = None,
                voice: bool = False) -> None:
    async def handler(ws) -> None:
        conn = RpgConnection(reply_model=reply_model, dm_model=dm_model, voice=voice)
        try:
            async for raw in ws:
                try:
                    outs = await conn.handle(json.loads(raw))
                except Exception as e:                # never drop the connection on one bad message
                    outs = await conn.recover(e)
                for o in outs:
                    await ws.send(json.dumps(o))
        finally:
            # Land the mind side of persistence on disconnect: in-flight background reflections
            # flush to each character's own store (the world already autosaved per action).
            if conn.game is not None:
                try:
                    await conn.game.minds.flush()
                except Exception as exc:              # noqa: BLE001
                    print(f"[rpg-server] mind flush on disconnect failed: {exc}")

    async with websockets.serve(handler, host, port, max_size=2 ** 22):
        print(f"[rpg-server] listening on ws://{host}:{port}  (one game per connection; voice={voice})")
        await asyncio.Future()                        # run forever


def main() -> None:
    host = os.environ.get("RPG_HOST", "127.0.0.1")
    port = int(os.environ.get("RPG_PORT", "8787"))
    model = os.environ.get("RPG_MODEL", "claude-haiku-4-5")
    # Voice defaults ON when a Hume key is present; RPG_VOICE=0 forces text-only.
    from orchestrator.config import get_settings
    voice = os.environ.get("RPG_VOICE", "1") != "0" and bool(get_settings().hume_api_key)
    asyncio.run(serve(host, port, reply_model=model, dm_model=model, voice=voice))


if __name__ == "__main__":
    main()
