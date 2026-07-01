"""The authoritative world model. A grid (cells) under the hood for position and distance; NAMED
regions overlay it so everything downstream speaks in places ("the hearth"), never coordinates.
This is ground truth — perception (perception.py) derives from it; nothing invents world facts."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Region:
    """A named area of the grid (inclusive rect)."""
    name: str
    rect: tuple[int, int, int, int]  # x0, y0, x1, y1

    def contains(self, x: int, y: int) -> bool:
        x0, y0, x1, y1 = self.rect
        return x0 <= x <= x1 and y0 <= y <= y1

    def center(self) -> tuple[int, int]:
        x0, y0, x1, y1 = self.rect
        return ((x0 + x1) // 2, (y0 + y1) // 2)


@dataclass
class Fixture:
    """A thing in the world with affordances (what can be done with/at it)."""
    name: str
    pos: tuple[int, int]
    affords: list[str] = field(default_factory=list)
    present: bool = True  # can appear/vanish (e.g. the warrant nailed up at a later beat)


@dataclass
class Entity:
    """A body in the world — an NPC or the player. `stance` is OBSERVABLE activity/posture (authored
    ground truth), never inner state."""
    id: str
    pos: tuple[int, int]
    kind: str = "npc"   # "npc" | "player"
    stance: str = ""


@dataclass
class World:
    """The grid IS the ground truth. Every entity's `pos` (x, y cell) is the single source of position
    truth; a "region" is only ever DERIVED from it (`region_of`) for presentation — named places never
    replace or override the coordinates. Distance, line-of-sight, and (later) tactics all read `pos`."""
    w: int
    h: int
    regions: list[Region] = field(default_factory=list)
    fixtures: dict[str, Fixture] = field(default_factory=dict)
    entities: dict[str, Entity] = field(default_factory=dict)

    # ---- queries ----
    def region_of(self, pos) -> str:
        for r in self.regions:
            if r.contains(*pos):
                return r.name
        return "the taproom"

    def region(self, name: str) -> Region | None:
        return next((r for r in self.regions if r.name == name), None)

    def dist(self, a, b) -> int:
        """Grid steps between two cells (Chebyshev — diagonal counts as one)."""
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

    def region_names(self) -> list[str]:
        return [r.name for r in self.regions]

    # ---- mutation ----
    def place(self, id: str, region_name: str, *, kind: str = "npc", stance: str = "") -> None:
        r = self.region(region_name)
        pos = r.center() if r else (self.w // 2, self.h // 2)
        self.entities[id] = Entity(id, pos, kind, stance)

    def move(self, id: str, pos) -> None:
        """Move an entity to an EXACT cell. `pos` (coordinates) is authoritative — this is the precise
        mechanic; regions are only derived from the result. Use this to preserve grid precision."""
        if id in self.entities:
            self.entities[id].pos = (int(pos[0]), int(pos[1]))

    def move_to_region(self, id: str, region_name: str) -> bool:
        """Convenience: move to a region's centre (coarse). Still just sets an authoritative `pos`;
        the region is not stored. Returns False if the region is unknown."""
        r = self.region(region_name)
        if not r or id not in self.entities:
            return False
        self.entities[id].pos = r.center()
        return True


def load_world(map_path) -> World:
    """Build a World from a map YAML (size, regions, fixtures, placements) and apply the initial
    placements. Placements reference cast slugs (a scenario concern) + the player."""
    data = yaml.safe_load(Path(map_path).read_text(encoding="utf-8"))
    world = World(w=data["size"][0], h=data["size"][1],
                  regions=[Region(r["name"], tuple(r["rect"])) for r in data.get("regions", [])])
    for f in data.get("fixtures", []):
        pos = tuple(f["pos"]) if "pos" in f else (world.region(f.get("region", "")) or Region("", (0, 0, 0, 0))).center()
        world.fixtures[f["name"]] = Fixture(f["name"], pos, f.get("affords", []), f.get("present", True))
    for eid, spec in data.get("placements", {}).items():
        world.place(eid, spec["region"], kind=("player" if eid == "player" else "npc"),
                    stance=spec.get("stance", ""))
    return world
