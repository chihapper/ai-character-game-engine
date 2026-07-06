"""Disposable tcod/ASCII dev view (Phase A) — a thin renderer over the `GameSession`.

Keep it THIN: it only draws the `StateSnapshot`, streams events into a message log, and turns
keypresses into `PlayerAction`s. All game logic stays in the Python core; this whole file is
throwaway once the Godot client (Phase B) consumes the same `GameSession`.

Run:  .venv/Scripts/python.exe -m game.rpg.play
Keys: arrows / hjkl / wasd = move · t = talk (type a line, Enter) · f = free/help the one you
      face (a consequential deed) · g = toggle enemy HP in combat · . = wait · q = quit
"""
from __future__ import annotations

import asyncio
import os

import tcod

from .session import (
    CombatEvent,
    DialogueEvent,
    ModeChangedEvent,
    NarrationEvent,
    PlayerAction,
)
from .state import Mode

# tile glyph -> colour
_TILE = {
    "#": (60, 55, 50), ".": (120, 110, 100), "+": (150, 120, 80),
    ">": (230, 200, 80), "<": (230, 200, 80), " ": (20, 20, 20),
}
_ENT = {"player": (255, 255, 255), "npc": (95, 205, 225), "follower": (120, 220, 120), "enemy": (220, 90, 90)}
_LOG_ROWS = 11
_MOVE = {
    tcod.event.KeySym.UP: (0, -1), tcod.event.KeySym.DOWN: (0, 1),
    tcod.event.KeySym.LEFT: (-1, 0), tcod.event.KeySym.RIGHT: (1, 0),
    tcod.event.KeySym.k: (0, -1), tcod.event.KeySym.j: (0, 1),
    tcod.event.KeySym.h: (-1, 0), tcod.event.KeySym.l: (1, 0),
    tcod.event.KeySym.w: (0, -1), tcod.event.KeySym.s: (0, 1),
    tcod.event.KeySym.a: (-1, 0), tcod.event.KeySym.d: (1, 0),
}


def _tileset():
    for path in ("C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf",
                 "/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        if os.path.exists(path):
            return tcod.tileset.load_truetype_font(path, 16, 16)
    raise RuntimeError("No monospace TTF found for the tcod dev view — set one in _tileset().")


class _View:
    def __init__(self, game) -> None:
        self.game = game
        self.log: list[tuple[str, tuple[int, int, int]]] = []
        self.loop = asyncio.new_event_loop()
        self._note("You descend into the Sunken Vault. (t: talk  f: free/help  arrows: move  q: quit)")

    def _note(self, text: str, colour=(200, 200, 190)) -> None:
        self.log.append((text, colour))
        self.log = self.log[-40:]

    def _drain(self) -> None:
        g = self.game
        while not g._events.empty():
            ev = g._events.get_nowait()
            if isinstance(ev, NarrationEvent):
                self._note(ev.text, (170, 170, 210))
            elif isinstance(ev, DialogueEvent):
                self._note(f"{ev.npc}: {ev.text}", (230, 210, 120))
            elif isinstance(ev, CombatEvent):
                self._note(ev.text, (220, 140, 100))
            elif isinstance(ev, ModeChangedEvent):
                self._note(f"— {ev.mode.value.upper()} —", (220, 90, 90))

    def _act(self, action: PlayerAction) -> None:
        self.loop.run_until_complete(self.game.submit_action(action))
        self._drain()

    # --- the one NPC the player currently faces (adjacent) ---
    def _facing_npc(self):
        s = self.game.state
        px, py = s.player.pos
        near = [n for n in s.npcs if n.pos and abs(n.pos[0] - px) + abs(n.pos[1] - py) <= 1]
        return near[0] if near else None

    def render(self, console: tcod.console.Console) -> None:
        console.clear()
        snap = self.game.get_state()
        # map
        for y, row in enumerate(snap.tiles):
            for x, ch in enumerate(row):
                console.print(x, y, ch, fg=_TILE.get(ch, (100, 100, 100)))
        # entities
        for e in snap.entities:
            if e.pos:
                console.print(e.pos[0], e.pos[1], e.name[0], fg=_ENT.get(e.kind, (200, 200, 200)))
        console.print(snap.player.pos[0], snap.player.pos[1], "@", fg=_ENT["player"])
        # status line
        p = snap.player
        status = f" HP {p.hp}/{p.max_hp}  {snap.mode.value}  t={snap.clock:.1f} "
        console.print(0, snap.map_height, status.ljust(console.width), fg=(255, 255, 255), bg=(40, 40, 50))
        # message log (wrapped, newest at bottom)
        top = snap.map_height + 1
        lines: list[tuple[str, tuple]] = []
        for text, col in self.log:
            for w in _wrap(text, console.width):
                lines.append((w, col))
        for i, (text, col) in enumerate(lines[-_LOG_ROWS:]):
            console.print(0, top + i, text[:console.width], fg=col)


def _wrap(text: str, width: int) -> list[str]:
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line); line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out or [""]


def _prompt_line(view: _View, console, context, label: str) -> str | None:
    """Blocking single-line text entry drawn in the status row."""
    buf = ""
    while True:
        view.render(console)
        console.print(0, view.game.get_state().map_height, f"{label}{buf}_".ljust(console.width),
                      fg=(255, 255, 255), bg=(30, 60, 30))
        context.present(console)
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if isinstance(event, tcod.event.TextInput):
                buf += event.text
            elif isinstance(event, tcod.event.KeyDown):
                if event.sym == tcod.event.KeySym.RETURN:
                    return buf.strip()
                if event.sym == tcod.event.KeySym.ESCAPE:
                    return None
                if event.sym == tcod.event.KeySym.BACKSPACE:
                    buf = buf[:-1]


def run(game) -> None:
    view = _View(game)
    tileset = _tileset()
    w = max(64, game.state.world_map.width)
    h = game.state.world_map.height + 1 + _LOG_ROWS
    console = tcod.console.Console(w, h, order="C")
    with tcod.context.new(columns=w, rows=h, tileset=tileset, title="The Sunken Vault") as context:
        while True:
            view.render(console)
            context.present(console)
            for event in tcod.event.wait():
                if isinstance(event, tcod.event.Quit):
                    return
                if not isinstance(event, tcod.event.KeyDown):
                    continue
                sym = event.sym
                if sym == tcod.event.KeySym.q:
                    return
                if sym in _MOVE:
                    dx, dy = _MOVE[sym]
                    view._act(PlayerAction(kind="move", dx=dx, dy=dy))
                elif sym == tcod.event.KeySym.PERIOD:
                    view._act(PlayerAction(kind="wait"))
                elif sym == tcod.event.KeySym.g:
                    view._act(PlayerAction(kind="toggle_enemy_hp"))
                elif sym == tcod.event.KeySym.t:
                    npc = view._facing_npc()
                    if not npc:
                        view._note("No one close enough to speak to.", (150, 150, 150))
                        break
                    line = _prompt_line(view, console, context, f"Say to {npc.name}: ")
                    if line:
                        view._act(PlayerAction(kind="talk", target_id=npc.slug, text=line))
                elif sym == tcod.event.KeySym.f:
                    npc = view._facing_npc()
                    if not npc:
                        view._note("No one beside you to help.", (150, 150, 150))
                        break
                    view._note(f"You move to help {npc.name}.", (150, 200, 150))
                    view.loop.run_until_complete(view.game.remember_player_deed(
                        f"The traveler stepped in to help {npc.name}, sharing supplies and asking nothing in return.",
                        targets=[npc.slug], player_role="caused", magnitude=0.8))
                    view._drain()
