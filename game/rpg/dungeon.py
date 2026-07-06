"""Procedural dungeon generation — one source behind the `WorldMap` map-source abstraction.

Pure Python + a SEEDED RNG (deterministic / replayable). Classic rooms-and-corridors: place
non-overlapping rooms, connect each new room to the previous with an L-corridor (connected by
construction), then stamp up/down stairs. Phase A ships one dungeon; the AUTHORED-map path (e.g.
Tiled) plugs into the same `WorldMap` later. (BSP / cellular-automata variants can live behind this
same `generate_dungeon` signature.)
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .state import Pos, WorldMap

WALL, FLOOR, DOOR, DOWN, UP = "#", ".", "+", ">", "<"


@dataclass
class Room:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> Pos:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def intersects(self, other: "Room", pad: int = 1) -> bool:
        return (self.x - pad <= other.x + other.w and self.x + self.w + pad >= other.x
                and self.y - pad <= other.y + other.h and self.y + self.h + pad >= other.y)

    def inner_cells(self) -> list[Pos]:
        return [(x, y) for y in range(self.y, self.y + self.h) for x in range(self.x, self.x + self.w)]


def _carve_room(grid: list[list[str]], room: Room) -> None:
    for x, y in room.inner_cells():
        grid[y][x] = FLOOR


def _carve_corridor(grid: list[list[str]], a: Pos, b: Pos, rng: random.Random) -> None:
    (x1, y1), (x2, y2) = a, b
    if rng.random() < 0.5:                       # horizontal then vertical, or vice versa
        _h_line(grid, x1, x2, y1); _v_line(grid, y1, y2, x2)
    else:
        _v_line(grid, y1, y2, x1); _h_line(grid, x1, x2, y2)


def _h_line(grid, x1, x2, y):
    for x in range(min(x1, x2), max(x1, x2) + 1):
        if grid[y][x] == WALL:
            grid[y][x] = FLOOR


def _v_line(grid, y1, y2, x):
    for y in range(min(y1, y2), max(y1, y2) + 1):
        if grid[y][x] == WALL:
            grid[y][x] = FLOOR


@dataclass
class Dungeon:
    world_map: WorldMap
    rooms: list[Room]

    @property
    def spawns(self) -> list[Pos]:
        """Room centers — stable spawn anchors for the player / NPCs / encounter."""
        return [r.center for r in self.rooms]


def generate_dungeon(*, width: int = 64, height: int = 32, seed: int | None = None,
                     max_rooms: int = 10, room_min: int = 4, room_max: int = 9,
                     tries: int = 120) -> Dungeon:
    rng = random.Random(seed)
    grid = [[WALL] * width for _ in range(height)]
    rooms: list[Room] = []

    for _ in range(tries):
        w = rng.randint(room_min, room_max)
        h = rng.randint(room_min, room_max)
        x = rng.randint(1, width - w - 1)
        y = rng.randint(1, height - h - 1)
        room = Room(x, y, w, h)
        if any(room.intersects(r) for r in rooms):
            continue
        _carve_room(grid, room)
        if rooms:
            _carve_corridor(grid, rooms[-1].center, room.center, rng)
        rooms.append(room)
        if len(rooms) >= max_rooms:
            break

    if not rooms:                                # degenerate; carve a fallback room
        room = Room(1, 1, min(room_max, width - 2), min(room_max, height - 2))
        _carve_room(grid, room)
        rooms.append(room)

    up = rooms[0].center
    down = rooms[-1].center
    grid[up[1]][up[0]] = UP
    grid[down[1]][down[0]] = DOWN

    world_map = WorldMap(width=width, height=height, tiles=["".join(row) for row in grid],
                         seed=seed, source="procedural", stairs_up=up, stairs_down=down)
    return Dungeon(world_map=world_map, rooms=rooms)


def render_ascii(world_map: WorldMap, marks: dict[Pos, str] | None = None) -> str:
    """Debug/print helper: the raw map with optional entity marks (e.g. {(x,y): '@'})."""
    marks = marks or {}
    rows = [list(row) for row in world_map.tiles]
    for (x, y), ch in marks.items():
        if world_map.in_bounds(x, y):
            rows[y][x] = ch
    return "\n".join("".join(r) for r in rows)
