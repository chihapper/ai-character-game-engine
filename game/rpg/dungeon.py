"""Procedural dungeon generation — one source behind the `WorldMap` map-source abstraction.

Pure Python + a SEEDED RNG (deterministic / replayable). Classic rooms-and-corridors: place
non-overlapping rooms, connect each new room to the previous with an L-corridor (connected by
construction), then stamp up/down stairs. Phase A ships one dungeon; the AUTHORED-map path (e.g.
Tiled) plugs into the same `WorldMap` later. (BSP / cellular-automata variants can live behind this
same `generate_dungeon` signature.)
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from .state import Pos, WorldMap

WALL, FLOOR, DOOR, DOWN, UP = "#", ".", "+", ">", "<"


def _dist(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _assert_connected(world_map, spawns) -> None:
    """The core generation RULE, ENFORCED: every walkable cell is reachable from the up-stair (no
    marooned pockets), and every spawn anchor is walkable + reachable. A generator that ever violated
    this would silently ship an uncompletable map — so we fail loudly at generation instead. (This is
    the concrete form of "a set of rules that ensures whatever you generate doesn't break the game".)"""
    wm = world_map
    start = tuple(wm.stairs_up or (spawns[0] if spawns else (0, 0)))
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (x + dx, y + dy)
            if nb not in seen and wm.walkable(*nb):
                seen.add(nb)
                q.append(nb)
    floors = sum(1 for y in range(wm.height) for x in range(wm.width) if wm.walkable(x, y))
    if len(seen) != floors:
        raise AssertionError(f"generator produced a disconnected map: "
                             f"{floors - len(seen)} of {floors} floor cells unreachable from the up-stair")
    for p in spawns:
        if tuple(p) not in seen:
            raise AssertionError(f"spawn anchor {tuple(p)} is unreachable")


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
            # Connect to the NEAREST already-placed room (not the previously-placed one): shorter,
            # more natural corridors, and since every new room attaches to an existing one the graph
            # stays a spanning tree = fully connected by construction.
            nearest = min(rooms, key=lambda r: _dist(r.center, room.center))
            _carve_corridor(grid, nearest.center, room.center, rng)
        rooms.append(room)
        if len(rooms) >= max_rooms:
            break

    if not rooms:                                # degenerate; carve a fallback room
        room = Room(1, 1, min(room_max, width - 2), min(room_max, height - 2))
        _carve_room(grid, room)
        rooms.append(room)

    # A few EXTRA corridors between nearby rooms add loops (better flow than a pure tree — a lone
    # spanning tree forces backtracking; a couple of loops is the TinyKeep/MST + a-few-edges idea).
    for _ in range(max(0, len(rooms) // 4)):
        if len(rooms) < 2:
            break
        a, b = rng.sample(rooms, 2)
        if _dist(a.center, b.center) <= room_max * 4:
            _carve_corridor(grid, a.center, b.center, rng)

    # Entrance = the player's start room; EXIT = the room FARTHEST from it (not just the last placed),
    # so the objective is a real journey across the map rather than next door to the start.
    up = rooms[0].center
    down = max((r.center for r in rooms), key=lambda c: _dist(c, up))
    grid[up[1]][up[0]] = UP
    grid[down[1]][down[0]] = DOWN

    world_map = WorldMap(width=width, height=height, tiles=["".join(row) for row in grid],
                         seed=seed, source="procedural", stairs_up=up, stairs_down=down)
    _assert_connected(world_map, [r.center for r in rooms])
    return Dungeon(world_map=world_map, rooms=rooms)


# --------------------------------------------------------------------------------------------------
# A SECOND generator behind the same contract (returns a Dungeon whose .world_map has '#/./>/<' tiles
# and whose .spawns lists reachable anchor cells). Organic caverns via cellular automata — proof that
# the map-source abstraction isn't wedded to rooms-and-corridors. A slice picks its generator; the
# game-core is unchanged.
# --------------------------------------------------------------------------------------------------

def _wall_count(grid, x, y, w, h) -> int:
    c = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= w or ny >= h or grid[ny][nx] == WALL:
                c += 1
    return c


def _ca_step(grid, w, h) -> list[list[str]]:
    new = [[WALL] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if x == 0 or y == 0 or x == w - 1 or y == h - 1:
                new[y][x] = WALL                       # keep a solid border
            else:
                new[y][x] = WALL if _wall_count(grid, x, y, w, h) >= 5 else FLOOR
    return new


def _largest_floor_region(grid, w, h) -> set[Pos]:
    """The biggest 4-connected blob of floor — everything else becomes wall, so the map is one
    connected cave (no marooned pockets the player can never reach)."""
    seen: set[Pos] = set()
    best: set[Pos] = set()
    for y in range(h):
        for x in range(w):
            if grid[y][x] == FLOOR and (x, y) not in seen:
                stack = [(x, y)]
                region = {(x, y)}
                seen.add((x, y))
                while stack:
                    cx, cy = stack.pop()
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] == FLOOR and (nx, ny) not in seen:
                            seen.add((nx, ny)); region.add((nx, ny)); stack.append((nx, ny))
                if len(region) > len(best):
                    best = region
    return best


def _spread_anchors(cells: list[Pos], n: int) -> list[Pos]:
    """Farthest-point sampling: spawn anchors spread across the cave (deterministic — no RNG), so
    the player, NPCs, encounter, and objective don't clump in one chamber."""
    if len(cells) <= n:
        return list(cells)
    anchors = [min(cells, key=lambda c: (c[0] + c[1], c))]      # deterministic start (top-left-most)
    while len(anchors) < n:
        nxt = max(cells, key=lambda c: (min(abs(c[0] - a[0]) + abs(c[1] - a[1]) for a in anchors), c))
        if nxt in anchors:
            break
        anchors.append(nxt)
    return anchors


def generate_caverns(*, width: int = 72, height: int = 36, seed: int | None = None,
                     fill_prob: float = 0.46, steps: int = 5, anchors: int = 8) -> Dungeon:
    """An organic cave system (cellular automata). Same signature/return contract as
    `generate_dungeon`, so content can request it and the core never knows the difference."""
    rng = random.Random(seed)
    grid = [[WALL] * width for _ in range(height)]
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            grid[y][x] = WALL if rng.random() < fill_prob else FLOOR
    for _ in range(steps):
        grid = _ca_step(grid, width, height)

    region = _largest_floor_region(grid, width, height)
    if len(region) < anchors + 2:                      # degenerate cave; carve a fallback chamber
        room = Room(1, 1, min(room_max_fallback(width), width - 2), min(room_max_fallback(height), height - 2))
        _carve_room(grid, room)
        region = set(room.inner_cells())
    grid = [[FLOOR if (x, y) in region else WALL for x in range(width)] for y in range(height)]

    pts = _spread_anchors(sorted(region), anchors)
    rooms = [Room(x, y, 1, 1) for (x, y) in pts]        # 1x1 anchor 'rooms' feed the .spawns contract
    # Entrance = the player's start anchor; EXIT = the anchor FARTHEST from it. (Was `pts[-1]`, the
    # last farthest-point pick, which is a gap-filler and often lands NEAR the entrance — the reason
    # cavern entrances/exits looked clustered.)
    up = pts[0]
    down = max(pts, key=lambda p: _dist(p, up))
    grid[up[1]][up[0]] = UP
    grid[down[1]][down[0]] = DOWN

    world_map = WorldMap(width=width, height=height, tiles=["".join(row) for row in grid],
                         seed=seed, source="procedural", stairs_up=up, stairs_down=down)
    _assert_connected(world_map, pts)
    return Dungeon(world_map=world_map, rooms=rooms)


def room_max_fallback(dim: int) -> int:
    return max(6, dim // 3)


def render_ascii(world_map: WorldMap, marks: dict[Pos, str] | None = None) -> str:
    """Debug/print helper: the raw map with optional entity marks (e.g. {(x,y): '@'})."""
    marks = marks or {}
    rows = [list(row) for row in world_map.tiles]
    for (x, y), ch in marks.items():
        if world_map.in_bounds(x, y):
            rows[y][x] = ch
    return "\n".join("".join(r) for r in rows)
