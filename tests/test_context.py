"""Context assembly (orchestrator/context.py) — pure string/dataclass work: the arena query, the
Situation channel, and per-turn context rendering."""
from orchestrator.character_store import load_character
from orchestrator.context import (RespondRequest, Situation, build_arena_query,
                                  render_recent_happenings, render_situation, render_turn_context)


def test_situation_from_dict_clock_and_emptiness():
    assert Situation.from_dict(None) is None
    assert Situation.from_dict({}) is None
    sit = Situation.from_dict({"clock": 3})
    assert sit is not None and sit.clock == 3.0      # clock-only survives (decay needs it)
    assert Situation.from_dict({"t": 2.5}).clock == 2.5


def test_render_situation_displays_fields_but_never_bare_clock():
    assert render_situation(Situation(clock=4.0)) == ""  # nothing displayable -> no section
    out = render_situation(Situation(location="the hearth", present=["the ferrywoman"], clock=4.0))
    assert "the hearth" in out and "the ferrywoman" in out and "4.0" not in out


def test_arena_query_folds_trigger_goals_and_stance():
    char = load_character("joren-pike")
    req = RespondRequest(player_input="what do you make of the stranger?",
                         situation=Situation(location="the taproom"))
    q = build_arena_query(req, char, [{"role": "user", "content": "earlier line"}],
                          relationship_hint="wary of the newcomer")
    assert "stranger" in q and "wary of the newcomer" in q and "earlier line" in q
    explicit = RespondRequest(player_input="x", retrieval_query="override query")
    assert build_arena_query(explicit, char) == "override query"


def test_turn_context_composes_sections_in_order():
    out = render_turn_context(
        memories=["the bridge burned"], beliefs=["the player keeps their word"],
        goals=["rebuild the mill"], relationship="", intent="",
        recent_happenings=render_recent_happenings(["the mill flooded"], ["shuttered the shop"]),
        situation=Situation(location="the bakery"))
    assert out.index("the mill flooded") < out.index("the bridge burned")  # working memory leads
    assert "the player keeps their word" in out and "rebuild the mill" in out
    assert "the bakery" in out
    assert render_turn_context() == ""  # nothing dynamic -> empty
