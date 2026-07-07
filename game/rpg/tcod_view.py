"""Disposable tcod/ASCII dev view (Phase A) — a thin renderer over the `GameSession`.

Keep it THIN: it only draws the `StateSnapshot`, streams events into a message log, and turns
keypresses into `PlayerAction`s. All game logic stays in the Python core; this whole file is
throwaway once the Godot client (Phase B) consumes the same `GameSession`.

Run:  .venv/Scripts/python.exe -m game.rpg.play
Keys: arrows / hjkl / wasd = move (bump into an enemy to attack) · x = do (type any action, Enter)
      · t = talk (type a line, Enter) · f = free/help the one you face (a consequential deed) ·
      r = recruit the one you face · g = toggle enemy HP in combat · PgUp/PgDn (or wheel) = scroll
      the log · . = wait in exploration / end your turn in combat · q = quit
No mouse here (click-to-move is the Godot client's): combat is turn-based — on your turn the
movement keys step/bump-attack and '.' ends the turn.
"""
from __future__ import annotations

import asyncio
import os

import numpy as np
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
_ENT = {"player": (255, 255, 255), "npc": (95, 205, 225), "follower": (120, 220, 120),
        "enemy": (220, 90, 90), "door": (205, 150, 70)}
_LOG_ROWS = 14
_MOVE = {
    tcod.event.KeySym.UP: (0, -1), tcod.event.KeySym.DOWN: (0, 1),
    tcod.event.KeySym.LEFT: (-1, 0), tcod.event.KeySym.RIGHT: (1, 0),
    tcod.event.KeySym.k: (0, -1), tcod.event.KeySym.j: (0, 1),
    tcod.event.KeySym.h: (-1, 0), tcod.event.KeySym.l: (1, 0),
    tcod.event.KeySym.w: (0, -1), tcod.event.KeySym.s: (0, 1),
    tcod.event.KeySym.a: (-1, 0), tcod.event.KeySym.d: (1, 0),
}
# US-layout shifted symbols, for building typed text from KeyDown keycodes (SDL3 doesn't emit
# TextInput events unless text input is explicitly started, so we read chars off KeyDown instead).
_SHIFT_SYM = {"1": "!", "2": "@", "3": "#", "4": "$", "5": "%", "6": "^", "7": "&", "8": "*",
              "9": "(", "0": ")", "-": "_", "=": "+", "[": "{", "]": "}", "\\": "|", ";": ":",
              "'": '"', ",": "<", ".": ">", "/": "?", "`": "~"}


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
        self.scroll = 0                  # log scrollback offset (0 = newest pinned to bottom)
        self.loop = asyncio.new_event_loop()
        # The map is STATIC — bake its glyphs+colours into numpy arrays ONCE (from the SNAPSHOT, the
        # only seam), then bulk-assign per frame. Fog of war is applied per render as a numpy mask
        # over the baked layers (rather than rebaking on StateChanged): renders only happen after
        # input events (the loop blocks on tcod.event.wait), and the mask build is O(tiles seen) +
        # bulk array ops, so per-frame cost stays trivial and the view stays stateless about fog.
        snap = game.get_state()
        self.map_h, self.map_w = snap.map_height, snap.map_width
        self._map_ch = np.zeros((self.map_h, self.map_w), dtype=np.int32)
        self._map_fg = np.zeros((self.map_h, self.map_w, 3), dtype=np.uint8)
        for y, row in enumerate(snap.tiles):
            for x, c in enumerate(row):
                self._map_ch[y, x] = ord(c)
                self._map_fg[y, x] = _TILE.get(c, (100, 100, 100))
        self._map_fg_dim = (self._map_fg * 0.35).astype(np.uint8)   # explored-but-unseen memory
        self._note("Keys: move=arrows/hjkl/wasd (bump enemy=attack)  x=do  t=talk  f=help  r=recruit  "
                   "g=enemy HP  PgUp/PgDn=scroll  .=wait/end turn  q=quit")

    def _note(self, text: str, colour=(200, 200, 190)) -> None:
        self.log.append((text, colour))
        self.log = self.log[-80:]
        self.scroll = 0                  # snap to newest whenever something new happens

    def _drain(self) -> None:
        for ev in self.game.drain_events():         # the public seam — never the core's queue
            if isinstance(ev, NarrationEvent):
                self._note(ev.text, (170, 170, 210))
            elif isinstance(ev, DialogueEvent):
                # Show ONLY the spoken line (fall back to full text if the core didn't split).
                # Stage directions (`action`) are never shown as text — the DM voices them if relevant.
                self._note(f"{ev.npc}: {ev.speech or ev.text}", (230, 210, 120))
            elif isinstance(ev, CombatEvent):
                self._note(ev.text, (220, 140, 100))
            elif isinstance(ev, ModeChangedEvent):
                self._note(f"— {ev.mode.value.upper()} —", (220, 90, 90))

    def _act(self, action: PlayerAction) -> None:
        self.loop.run_until_complete(self.game.submit_action(action))
        self._drain()

    # --- the adjacent person (NPC or follower) the player faces; EntityView has .id (slug) + .name ---
    def _facing(self):
        snap = self.game.get_state()
        px, py = snap.player.pos
        near = [e for e in snap.entities if e.kind in ("npc", "follower") and e.pos
                and abs(e.pos[0] - px) + abs(e.pos[1] - py) <= 1]
        return min(near, key=lambda e: abs(e.pos[0] - px) + abs(e.pos[1] - py), default=None)

    def _fog_mask(self, keys: list[str]) -> np.ndarray:
        """Boolean (h, w) mask from the snapshot's "x,y" tile keys."""
        m = np.zeros((self.map_h, self.map_w), dtype=bool)
        for k in keys:
            xs, ys = k.split(",")
            x, y = int(xs), int(ys)
            if 0 <= x < self.map_w and 0 <= y < self.map_h:
                m[y, x] = True
        return m

    def render(self, console: tcod.console.Console) -> None:
        console.clear()
        snap = self.game.get_state()
        # baked map through the fog: visible = full colour, explored-but-unseen = dim, else black
        vis = self._fog_mask(snap.visible)
        exp = self._fog_mask(snap.explored) | vis
        console.ch[:self.map_h, :self.map_w] = np.where(exp, self._map_ch, ord(" "))
        fg = np.where(vis[..., None], self._map_fg, self._map_fg_dim)
        fg[~exp] = 0
        console.fg[:self.map_h, :self.map_w] = fg
        # entities (few) draw on top — the snapshot already fogs them server-side, so draw them all.
        # In combat the acting combatant gets a highlighted cell (the initiative "cursor").
        cur = snap.combat_turn
        for e in snap.entities:
            if not e.pos:
                continue
            console.print(e.pos[0], e.pos[1], e.name[0], fg=_ENT.get(e.kind, (200, 200, 200)),
                          bg=(70, 70, 20) if cur == e.id else None)
            if e.kind == "enemy" and snap.show_enemy_hp and e.hp is not None:
                console.print(e.pos[0] + 1, e.pos[1], f"{e.hp}/{e.max_hp}", fg=(220, 90, 90))
            if e.down:                       # downed ally: death-save pips (+=success x=failure)
                pips = "+" * e.death_successes + "x" * e.death_failures
                console.print(e.pos[0] + 1, e.pos[1], f"[{pips or 'down'}]", fg=(200, 80, 80))
        console.print(snap.player.pos[0], snap.player.pos[1], "@", fg=_ENT["player"],
                      bg=(70, 70, 20) if cur == snap.player.id else None)
        # status line — in combat, the turn readout (round / whose turn / movement / action economy)
        p = snap.player
        if snap.mode == Mode.combat and cur:
            names = {e.id: e.name for e in snap.entities}
            names[p.id] = p.name
            act = "action SPENT" if snap.combat_action_used else "action ready"
            status = (f" HP {p.hp}/{p.max_hp}  Round {snap.combat_round} — {names.get(cur, cur)}'s turn"
                      f" · move {snap.combat_movement} ft · {act} ")
        else:
            obj = f"  |  {snap.objective}" if snap.objective else ""
            status = f" HP {p.hp}/{p.max_hp}  {snap.mode.value}  t={snap.clock:.1f}  items:{len(snap.inventory)}{obj} "
        console.print(0, self.map_h, status.ljust(console.width)[:console.width], fg=(255, 255, 255), bg=(40, 40, 50))
        # message log (scrollable): wrap the whole log, then show a window controlled by scroll
        all_lines: list[tuple[str, tuple]] = []
        for text, col in self.log:
            for w in _wrap(text, console.width):
                all_lines.append((w, col))
        self.scroll = max(0, min(self.scroll, max(0, len(all_lines) - _LOG_ROWS)))
        end = len(all_lines) - self.scroll
        window = all_lines[max(0, end - _LOG_ROWS):end]
        top = self.map_h + 1
        for i, (text, col) in enumerate(window):
            console.print(0, top + i, text[:console.width], fg=col)
        if self.scroll > 0:                          # scrollback indicator on the status row
            tag = f"[+{self.scroll} PgUp/PgDn]"
            console.print(max(0, console.width - len(tag)), self.map_h, tag, fg=(255, 220, 120), bg=(40, 40, 50))


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
        prompt = f"{label}{buf}"
        avail = console.width - 1                     # keep the cursor visible: show the tail that fits
        shown = prompt[-avail:] if len(prompt) > avail else prompt
        console.print(0, view.map_h, (shown + "_").ljust(console.width),
                      fg=(255, 255, 255), bg=(30, 60, 30))
        context.present(console)
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if not isinstance(event, tcod.event.KeyDown):
                continue
            sym = event.sym
            if sym == tcod.event.KeySym.RETURN:
                return buf.strip()
            if sym == tcod.event.KeySym.ESCAPE:
                return None
            if sym == tcod.event.KeySym.BACKSPACE:
                buf = buf[:-1]
                continue
            code = int(sym)                      # SDL keycode == ASCII base for printable keys
            if 32 <= code <= 126:
                ch = chr(code)
                if event.mod & tcod.event.Modifier.SHIFT:
                    ch = ch.upper() if ch.isalpha() else _SHIFT_SYM.get(ch, ch)
                buf += ch


def run(game, title: str = "") -> None:
    view = _View(game)
    tileset = _tileset()
    snap = game.get_state()
    w = max(64, snap.map_width)
    h = snap.map_height + 1 + _LOG_ROWS
    console = tcod.console.Console(w, h, order="C")
    # Window title from the snapshot's open objective (slice data via the seam — never the core's
    # internals), unless the caller names the window itself.
    title = title or snap.objective or "RPG dev view"
    with tcod.context.new(columns=w, rows=h, tileset=tileset, title=title) as context:
        if hasattr(game, "begin"):                    # opening DM scene — the world speaks first
            view.render(console); context.present(console)   # show the map immediately
            view.loop.run_until_complete(game.begin())
            view._drain()
        while True:
            view.render(console)
            context.present(console)
            for event in tcod.event.wait():
                if isinstance(event, tcod.event.Quit):
                    return
                if isinstance(event, tcod.event.MouseWheel):
                    view.scroll = max(0, view.scroll + event.y)   # wheel up = older lines
                    continue
                if not isinstance(event, tcod.event.KeyDown):
                    continue
                sym = event.sym
                if sym == tcod.event.KeySym.q:
                    return
                if sym == tcod.event.KeySym.PAGEUP:
                    view.scroll += _LOG_ROWS - 1
                    continue
                if sym == tcod.event.KeySym.PAGEDOWN:
                    view.scroll = max(0, view.scroll - (_LOG_ROWS - 1))
                    continue
                if sym in _MOVE:
                    dx, dy = _MOVE[sym]
                    view._act(PlayerAction(kind="move", dx=dx, dy=dy))
                elif sym == tcod.event.KeySym.PERIOD:
                    view._act(PlayerAction(kind="wait"))
                elif sym == tcod.event.KeySym.g:
                    view._act(PlayerAction(kind="toggle_enemy_hp"))
                elif sym == tcod.event.KeySym.t:
                    who = view._facing()
                    if not who:
                        view._note("No one close enough to speak to.", (150, 150, 150))
                        break
                    line = _prompt_line(view, console, context, f"Say to {who.name}: ")
                    if line:
                        view._act(PlayerAction(kind="talk", target_id=who.id, text=line))
                elif sym == tcod.event.KeySym.f:
                    who = view._facing()
                    if not who:
                        view._note("No one beside you to help.", (150, 150, 150))
                        break
                    view._note(f"You move to help {who.name}.", (150, 200, 150))
                    view.loop.run_until_complete(view.game.remember_player_deed(
                        f"The traveler stepped in to help {who.name}, sharing supplies and asking nothing in return.",
                        targets=[who.id], player_role="caused", magnitude=0.8))
                    view._drain()
                elif sym == tcod.event.KeySym.r:
                    who = view._facing()
                    if not who:
                        view._note("No one beside you to ask along.", (150, 150, 150))
                        break
                    view._act(PlayerAction(kind="recruit", target_id=who.id))
                elif sym == tcod.event.KeySym.x:
                    line = _prompt_line(view, console, context, "You try to: ")
                    if line:
                        view._act(PlayerAction(kind="do", text=line))
