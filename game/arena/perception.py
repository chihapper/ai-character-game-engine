"""Perception — derive an agent's FIRST-PERSON percept from the authoritative world, and render it as
the engine's `Situation`. This replaces DM-invented scene description: the character perceives only
what its position affords (who's here + how far + their OBSERVABLE stance, the fixtures in reach,
elapsed time) — grounded, consistent, observation-only. Named places, never coordinates."""
from __future__ import annotations

from dataclasses import dataclass, field

from orchestrator.context import Situation

from .world import World


def _proximity(d: int) -> str:
    if d <= 0:
        return "right beside you"
    if d <= 1:
        return "close by"
    if d <= 3:
        return "a few steps off"
    return "across the room"


@dataclass
class Percept:
    """What one agent perceives right now — the derived, first-person view of the world."""
    agent_id: str
    region: str
    others: list[dict] = field(default_factory=list)   # {ref, region, proximity, stance, distance}
    fixtures: list[dict] = field(default_factory=list)  # {name, region, affords}
    clock: float = 0.0
    elapsed: float | None = None


def perceive(world: World, agent_id: str, *, clock: float = 0.0, elapsed=None, ref_of=None) -> Percept:
    """Build `agent_id`'s percept. `ref_of(other_id) -> str` decides how each other is referred to
    (a name once learned, else an appearance handle; the player as 'the newcomer' etc.)."""
    ref_of = ref_of or (lambda eid: eid)
    me = world.entities[agent_id]
    others = []
    for eid, e in world.entities.items():
        if eid == agent_id:
            continue
        d = world.dist(me.pos, e.pos)
        others.append({"ref": ref_of(eid), "region": world.region_of(e.pos),
                       "proximity": _proximity(d), "stance": e.stance, "distance": d})
    others.sort(key=lambda o: o["distance"])
    fixtures = [{"name": f.name, "region": world.region_of(f.pos), "affords": f.affords}
                for f in world.fixtures.values() if f.present]
    return Percept(agent_id, world.region_of(me.pos), others, fixtures, clock, elapsed)


def to_situation(p: Percept, *, unit: str = "hours") -> Situation:
    """Render a percept into the `Situation` the character reasons from (engine-side, unchanged engine)."""
    present = []
    for o in p.others:
        bits = [o["ref"]]
        if o["stance"]:
            bits.append(f"— {o['stance']}")
        bits.append(f"({o['region']}, {o['proximity']})")
        present.append(" ".join(bits))
    extra = {}
    afford = "; ".join(f"{f['name']} [{', '.join(f['affords'])}]" for f in p.fixtures if f["affords"])
    if afford:
        extra["What this place affords"] = afford
    if p.elapsed:
        extra["Time just passed"] = f"{p.elapsed:g} {unit}"
    return Situation(location=p.region, present=present, extra=extra, clock=p.clock)


def render_player_view(p: Percept) -> str:
    """The player-facing view — a faithful readout of the player's percept in named places."""
    lines = [f"You're at {p.region}."]
    for o in p.others:
        stance = f", {o['stance']}" if o["stance"] else ""
        lines.append(f"- {o['ref']} — {o['region']}, {o['proximity']}{stance}")
    if p.fixtures:
        lines.append("Within reach: " + ", ".join(f["name"] for f in p.fixtures))
    return "\n".join(lines)
