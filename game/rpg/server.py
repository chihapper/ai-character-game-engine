"""Local WebSocket session server — the Phase B IPC seam.

Godot connects here and drives the SAME `RpgGame` GameSession the tcod dev view drove in-process.
All game logic + the engine stay in Python; Godot is a pure renderer over the wire. One connection =
one game. Each client message yields a batch of server messages that always ENDS with a `snapshot`
(errors included — the batch invariant holds on every path once a game exists). VOICE rides outside
the batch: dialogue text ships immediately; each line's Hume audio follows as its own `voice`
message once synthesis lands (a per-connection worker, in spoken order) — the world never waits on TTS.

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
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")

import websockets  # noqa: E402

from orchestrator.memory.base_store import atomic_write_text, quarantine  # noqa: E402

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
    voice_msg,
)
from .state import GameState, Mode  # noqa: E402
from .voice import stream_line, wire_rate  # noqa: E402

SAVE_DIR = Path(".saves")

# One ACTIVE game per save file, process-wide: the client's auto-reconnect (or a second client)
# can otherwise race two RpgGames onto the same .saves file with interleaved last-writer-wins
# autosaves (world divergence while the minds remember everything). Newest claimant WINS — a
# reconnect IS the same player coming back — and the old connection stops autosaving.
_ACTIVE_GAMES: dict[str, object] = {}


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
        """The saved world for this slice+seed, or None (missing / unreadable). An unreadable save
        is QUARANTINED (moved aside loudly) rather than left in place to be silently overwritten by
        the next autosave — the evidence survives."""
        p = _save_path(msg.slice, msg.seed)
        if not p.exists():
            return None
        try:
            return GameState.from_json(p.read_text(encoding="utf-8"))
        except Exception as exc:                     # noqa: BLE001 — a corrupt save must not brick starts
            print(f"[rpg-server] unreadable save {p}: {exc}")
            quarantine(p, str(exc))
            return None

    def _autosave(self) -> None:
        """Persist the WORLD after a handled message — exploration only (never a mid-combat or
        game-over snapshot), best-effort (a full disk must not kill the session). ATOMIC (tmp +
        fsync + replace): a crash mid-write can no longer truncate the only save — the mind stores
        got this guarantee long ago; the world save deserves the same. Skipped when another
        connection has since claimed this save file (adopt-newest)."""
        g = self.game
        if g is None or self._save_to is None:
            return
        if _ACTIVE_GAMES.get(str(self._save_to)) is not self:
            return                                   # a newer connection owns this save now
        if g.state.mode != Mode.exploration or g.state.flags.get("game_over"):
            return
        try:
            atomic_write_text(self._save_to, g.state.to_json())
        except Exception as exc:                     # noqa: BLE001
            print(f"[rpg-server] autosave failed: {exc}")

    def _autosave_fresh(self) -> None:
        """Unconditional first save of a brand-new world (mode gating doesn't apply — the game
        hasn't started yet; we just need the fresh state ON DISK so resume can't resurrect the
        abandoned one)."""
        if self.game is None or self._save_to is None:
            return
        try:
            atomic_write_text(self._save_to, self.game.state.to_json())
        except Exception as exc:                     # noqa: BLE001
            print(f"[rpg-server] fresh-start save failed: {exc}")

    async def handle(self, data: dict) -> list[dict]:
        msg = parse_client(data)                     # raises ValidationError on a bad shape
        if isinstance(msg, StartMsg):
            save_to = _save_path(msg.slice, msg.seed)
            loaded = self._load_save(msg) if msg.resume else None
            if loaded is not None:
                game = RpgGame.resume(slice=msg.slice, seed=msg.seed, state=loaded,
                                      reply_model=self.reply_model, dm_model=self.dm_model)
            else:
                game = RpgGame.new(slice=msg.slice, seed=msg.seed,
                                   reply_model=self.reply_model, dm_model=self.dm_model)
            # Commit the switch ONLY after construction succeeded — a failed start (unknown slice)
            # must leave the old game and its save target untouched.
            self.game = game
            self._save_to = save_to
            _ACTIVE_GAMES[str(save_to)] = self       # newest claimant wins; older ones stop saving
            if not msg.resume:
                # A FRESH start replaces the old save IMMEDIATELY — otherwise a link drop before
                # the first action would silently resurrect the world the player just abandoned.
                self._autosave_fresh()
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
        """Serialize the queued events. Voice is NOT synthesized here (it used to be, serially —
        which froze the reply text and the snapshot behind a multi-second Hume round-trip, the
        owner-felt latency issue): dialogue text ships immediately, and the connection's voice
        worker sends the audio as follow-up `voice` messages once synthesis lands."""
        return [event_msg(ev) for ev in self.game.drain_events()]


async def serve(host: str = "127.0.0.1", port: int = 8787, *,
                reply_model: str | None = None, dm_model: str | None = None,
                voice: bool = False) -> None:
    # Session hardening: a shared token is REQUIRED when binding beyond loopback (any LAN peer
    # could otherwise drive the game, burn LLM/TTS credits, and pollute persistent NPC minds).
    token = os.environ.get("RPG_TOKEN", "")
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        print("[rpg-server] WARNING: binding beyond loopback without RPG_TOKEN — any LAN peer "
              "can drive this game. Set RPG_TOKEN and pass it as the first message's `token`.")

    async def handler(ws) -> None:
        conn = RpgConnection(reply_model=reply_model, dm_model=dm_model, voice=voice)
        authed = not token                            # loopback default: no token configured
        send_lock = asyncio.Lock()                    # one writer at a time (batch vs voice worker)
        voice_q: asyncio.Queue = asyncio.Queue()

        async def voice_worker() -> None:
            """Synthesize + send voice AFTER the text is already on the wire — one line at a time,
            in spoken order, STREAMED: chunks go out as Hume produces them (coalesced to >=~0.5s
            per message so the client isn't spammed), so the first sentence is playing while the
            rest is still synthesizing. Best-effort with a per-chunk cap: a hung TTS request skips
            the REST of that line's voice instead of freezing the queue (voice skipped > world
            frozen). The client pushes chunks into one continuous audio stream — arrival order is
            playback order, which this worker's one-line-at-a-time loop guarantees."""
            rate = wire_rate()
            min_send = rate * 2 // 2                  # ~0.5 s of s16le mono per message, minimum
            while True:
                e = await voice_q.get()
                buf = bytearray()

                async def _flush() -> None:
                    if buf:
                        async with send_lock:
                            await ws.send(json.dumps(voice_msg(
                                slug=e.get("slug", ""), npc=e.get("npc", ""),
                                pcm=bytes(buf), rate=rate)))
                        buf.clear()

                agen = stream_line(e["text"], e.get("slug", ""))
                try:
                    while True:
                        try:
                            chunk = await asyncio.wait_for(agen.__anext__(), timeout=30)
                        except StopAsyncIteration:
                            break
                        buf += chunk
                        if len(buf) >= min_send:
                            await _flush()
                    await _flush()                    # the tail below the coalesce threshold
                except websockets.exceptions.ConnectionClosed:
                    return
                except Exception as exc:              # noqa: BLE001 — voice is an enhancement
                    print(f"[rpg-server] voice line cut short: {exc}")
                finally:
                    # Deterministic cleanup on EVERY exit (timeout/close/error): an abandoned
                    # async generator can hold the Hume HTTP stream open until GC gets to it.
                    try:
                        await agen.aclose()
                    except Exception:                 # noqa: BLE001
                        pass

        vtask = asyncio.create_task(voice_worker()) if voice else None
        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                    if not authed:
                        if isinstance(data, dict) and data.get("token") == token:
                            authed = True
                        else:
                            await ws.send(json.dumps(error_msg("unauthorized: send the RPG_TOKEN "
                                                               "as `token` on your first message")))
                            await ws.close(code=4401, reason="unauthorized")
                            return
                    outs = await conn.handle(data)
                except Exception as e:                # never drop the connection on one bad message
                    outs = await conn.recover(e)
                async with send_lock:
                    for o in outs:
                        await ws.send(json.dumps(o))
                if voice:                             # queue synth AFTER the text batch went out
                    for o in outs:
                        ev = o.get("event", {}) if o.get("t") == "event" else {}
                        if ev.get("type") == "dialogue" and (ev.get("text") or "").strip():
                            voice_q.put_nowait(ev)
        finally:
            if vtask is not None:
                vtask.cancel()
            # Land the mind side of persistence on disconnect: in-flight background reflections
            # flush to each character's own store (the world already autosaved per action).
            if conn.game is not None:
                try:
                    await conn.game.minds.flush()
                except Exception as exc:              # noqa: BLE001
                    print(f"[rpg-server] mind flush on disconnect failed: {exc}")

    # origins=[None]: reject BROWSER handshakes outright (a webpage open on this machine could
    # otherwise hijack the session via cross-site WebSocket — Godot's WebSocketPeer sends no
    # Origin header, so the real client passes; browsers always send one and are refused).
    async with websockets.serve(handler, host, port, max_size=2 ** 22, origins=[None]):
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
