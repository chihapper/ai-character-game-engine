"""The game-side action vocabulary: given the world + an agent, enumerate the CONCRETE actions the
place currently affords (the bounded set the engine's `choose_action` picks from), and execute the
chosen one against the world. The engine never sees these definitions — only their labels — so it
stays game-agnostic; the meaning + effects live here.

Each action carries a `type`/`cost` (action / bonus / move / reaction) so a future ACTION ECONOMY
(docs §14) can layer on without repainting — nothing spends a budget yet."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .world import World


@dataclass
class Action:
    label: str                       # the exact string the engine chooses by, and the player sees
    kind: str                        # "move" | "approach" | "use" | "watch" | "wait"
    apply: Callable[[World, str], str]   # (world, agent_id) -> short consequence phrase
    type: str = "action"             # economy-ready: action | bonus | move | reaction
    cost: int = 1


def _adjacent_cell(world: World, target_pos, mover: str | None = None) -> tuple[int, int]:
    tx, ty = target_pos
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        x, y = tx + dx, ty + dy
        if 0 <= x < world.w and 0 <= y < world.h and not world.occupied((x, y), exclude=mover):
            return (x, y)
    return (tx, ty)


def available(world: World, agent_id: str, *, ref_of) -> list[Action]:
    """The concrete, bounded set of things `agent_id` can do from where they stand right now."""
    me = world.entities[agent_id]
    here = world.region_of(me.pos)
    acts: list[Action] = []

    # cross to another named place (movement). Moving CLEARS the stance — a body that walks away
    # from the door stops being "just in from the storm, dripping"; a stale stance was anchoring
    # NPCs to the placement image ("the dripping stranger by the door") after the player had moved.
    for r in world.regions:
        if r.name != here:
            acts.append(Action(f"cross to {r.name}", "move",
                               lambda w, a, rn=r.name: (w.move_to_region(a, rn),
                                                        _set_stance(w, a, ""),
                                                        f"crosses to {rn}")[2],
                               type="move"))

    # move nearer to a present person you're not already beside (movement)
    for eid, e in world.entities.items():
        if eid != agent_id and world.dist(me.pos, e.pos) > 1:
            acts.append(Action(f"move nearer to {ref_of(eid)}", "approach",
                               lambda w, a, tid=eid: (w.move(a, _adjacent_cell(w, w.entities[tid].pos, a)),
                                                      _set_stance(w, a, ""),
                                                      f"moves nearer to {ref_of(tid)}")[2],
                               type="move"))

    # use a fixture you can actually reach (same region) — physical affordances
    for f in world.fixtures.values():
        if f.present and world.region_of(f.pos) == here:
            for aff in f.affords:
                if aff == "watch":
                    continue  # watching is a gaze, handled below (any distance)
                label = f"{aff} {f.name}"
                acts.append(Action(label, "use",
                                   lambda w, a, lbl=label: _set_stance(w, a, lbl),
                                   type="action"))

    # watch anything/anyone you can see — a gaze, no movement, any distance
    # stance is the observable state ("watching X"); the consequence phrase is the act itself
    # ("turn to watch X"), so logs read "you turn to watch X" / observers see "turns to watch X"
    for f in world.fixtures.values():
        if f.present and "watch" in f.affords:
            acts.append(Action(f"watch {f.name}", "watch",
                               lambda w, a, n=f.name: (_set_stance(w, a, f"watching {n}"),
                                                       f"turn to watch {n}")[1],
                               type="bonus", cost=0))
    for eid in world.entities:
        if eid != agent_id:
            acts.append(Action(f"watch {ref_of(eid)}", "watch",
                               lambda w, a, ref=ref_of(eid): (_set_stance(w, a, f"watching {ref}"),
                                                              f"turn to watch {ref}")[1],
                               type="bonus", cost=0))

    # hold where you are
    acts.append(Action("stay where you are, watchful", "wait",
                       lambda w, a: "stays where they are", type="action", cost=0))
    return acts


def _set_stance(world: World, agent_id: str, stance: str) -> str:
    world.entities[agent_id].stance = stance
    return stance


def execute(world: World, agent_id: str, label: str, actions: list[Action]) -> str | None:
    """Apply the chosen action (matched by exact label) to the world. Returns a consequence phrase,
    or None if the label isn't among the afforded actions (should not happen — the seam bounds it)."""
    act = next((a for a in actions if a.label == label), None)
    if act is None:
        return None
    return act.apply(world, agent_id)
