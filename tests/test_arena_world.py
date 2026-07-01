"""The arena world model + perception (game/arena/) — pure state math that was actively regressing
during playtests (marker collisions, vanishing @). Coordinates are ground truth; named places are a
derived view; perception is first-person and never leaks coordinates."""
from pathlib import Path

from game.arena.perception import perceive, render_player_view, to_situation
from game.arena.world import load_world

MAP = Path(__file__).resolve().parents[1] / "game" / "arena" / "maps" / "ferry_inn.yaml"


def world():
    return load_world(MAP)


def test_placements_land_in_their_regions():
    w = world()
    assert w.region_of(w.entities["player"].pos) == "the door"
    assert w.region_of(w.entities["corvin-ashgrave-inworld"].pos) == "the hearth"


def test_move_exact_is_authoritative():
    w = world()
    w.move("player", (9, 1))
    assert w.entities["player"].pos == (9, 1)
    assert w.region_of((9, 1)) == "the bar"  # region DERIVED from the coordinate


def test_move_to_region_picks_a_free_cell():
    w = world()
    w.move_to_region("player", "the hearth")  # Corvin already holds the hearth centre
    p, c = w.entities["player"].pos, w.entities["corvin-ashgrave-inworld"].pos
    assert p != c, "two bodies must share a place, never a cell"
    assert w.region_of(p) == "the hearth"


def test_dist_is_chebyshev():
    w = world()
    assert w.dist((0, 0), (3, 1)) == 3
    assert w.dist((2, 2), (2, 2)) == 0


def test_perception_is_first_person_and_updates_with_movement():
    w = world()
    p = perceive(w, "player", ref_of=lambda e: e)
    far = next(o for o in p.others if o["ref"] == "corvin-ashgrave-inworld")
    assert far["proximity"] == "across the room"
    w.move_to_region("player", "the hearth")
    p2 = perceive(w, "player", ref_of=lambda e: e)
    near = next(o for o in p2.others if o["ref"] == "corvin-ashgrave-inworld")
    assert near["distance"] <= 2  # crossing the room changed the derived proximity


def test_player_view_names_places_never_coordinates():
    w = world()
    view = render_player_view(perceive(w, "player", ref_of=lambda e: e))
    assert "the door" in view
    for e in w.entities.values():  # no raw grid cells in anything the player reads
        assert f"[{e.pos[0]},{e.pos[1]}]" not in view
        assert f"({e.pos[0]}, {e.pos[1]})" not in view


def test_situation_carries_elapsed_time():
    w = world()
    sit = to_situation(perceive(w, "corvin-ashgrave-inworld", clock=6.0, elapsed=2.0,
                                ref_of=lambda e: e))
    assert sit.clock == 6.0
    assert any("2" in str(v) for v in sit.extra.values())  # the time-jump is part of the percept
