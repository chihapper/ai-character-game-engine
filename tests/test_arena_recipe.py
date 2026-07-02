"""Pure unit tests over the arena's load-bearing game logic (pre-Unity review batch): the
reaction recipe's routing, the name-discipline trio, observed-phrase conjugation, proximity
tiers, world-move failure, and the per-engine capability threading that the review found broken.
No LLM, no filesystem: games are built with __new__ + hand-set state, engines are stubs."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from game.arena.game import ArenaGame
from game.arena.perception import _proximity
from game.arena.world import Entity, Region, World
from orchestrator.config import EngineCaps, Settings


# ---- fixtures (no I/O) --------------------------------------------------------------------

def bare_game(**engines) -> ArenaGame:
    """An ArenaGame with ONLY the state the name/reaction logic touches — no files, no LLM."""
    g = ArenaGame.__new__(ArenaGame)
    g.scenario = {}
    g.cast = list(engines)
    g.known_names = {}
    g.handles = {s: f"the {s.split('-')[0]} one" for s in engines}
    g.here_because = {}
    g.engines = engines
    g.clock = 0.0
    g.history = []
    g.transcript_path = None
    g.player_handle = "the stranger just in from the storm"
    return g


def mind(name: str, **hooks) -> SimpleNamespace:
    return SimpleNamespace(character=SimpleNamespace(name=name), **hooks)


def small_world() -> World:
    w = World(6, 3, [Region("east", (0, 0, 2, 2)), Region("west", (3, 0, 5, 2))])
    w.entities["player"] = Entity("player", (0, 0), kind="player")
    w.entities["npc"] = Entity("npc", (5, 2))
    return w


# ---- name discipline ----------------------------------------------------------------------

def test_scrub_replaces_narration_but_not_quoted_speech():
    g = bare_game(**{"della-fenwick": mind("Della Fenwick")})
    g.handles["della-fenwick"] = "the ferrywoman"
    out = g._scrub_names('Della wipes the bar. "Name\'s Della," she says.')
    assert out == 'the ferrywoman wipes the bar. "Name\'s Della," she says.'


def test_first_last_leak_collapses_to_one_handle():
    g = bare_game(**{"della-fenwick": mind("Della Fenwick")})
    g.handles["della-fenwick"] = "the ferrywoman"
    assert g._scrub_names("Della Fenwick nods.") == "the ferrywoman nods."


def test_names_learn_only_from_quoted_speech():
    g = bare_game(**{"della-fenwick": mind("Della Fenwick")})
    g._maybe_learn_name("della-fenwick", "Della nods at the stranger.")  # narration slip
    assert "della-fenwick" not in g.known_names
    g._maybe_learn_name("della-fenwick", '"Name\'s Della," she says.')  # spoken introduction
    assert g.known_names["della-fenwick"] == "Della"


def test_common_word_nickname_cannot_false_introduce():
    g = bare_game(**{"edwin-hale": mind('Edwin "Pockets" Hale')})
    g._maybe_learn_name("edwin-hale", '"Hale and hearty, that\'s me!" he laughs.')
    g._maybe_learn_name("edwin-hale", '"My pockets are empty," he shrugs.')
    assert "edwin-hale" not in g.known_names  # case-sensitive: hale/pockets-the-words don't teach
    g._maybe_learn_name("edwin-hale", '"They call me Pockets," he grins.')
    assert g.known_names["edwin-hale"] == "Pockets"


def test_scrub_case_sensitive_leaves_common_words_alone():
    g = bare_game(**{"edwin-hale": mind('Edwin "Pockets" Hale')})
    text = "He pockets the coin and looks hale enough."
    assert g._scrub_names(text) == text


# ---- observed-phrase conjugation -----------------------------------------------------------

@pytest.mark.parametrize("conseq,expected", [
    ("stoke the peat fire", "stokes the peat fire"),      # plain +s
    ("watch the storm", "watches the storm"),             # +es ending
    ("crosses to the bar", "crosses to the bar"),         # already third person
    ("turn to watch the door", "turns to watch the door"),
])
def test_as_observed_conjugation(conseq, expected):
    assert ArenaGame._as_observed(conseq) == expected


# ---- proximity tiers ------------------------------------------------------------------------

@pytest.mark.parametrize("d,tier", [
    (0, "right beside you"), (1, "close by"), (2, "a few steps off"),
    (3, "a few steps off"), (4, "across the room"), (9, "across the room"),
])
def test_proximity_tiers(d, tier):
    assert _proximity(d) == tier


# ---- world movement --------------------------------------------------------------------------

def test_move_to_unknown_region_fails_without_moving():
    w = small_world()
    before = w.entities["player"].pos
    assert w.move_to_region("player", "the moon") is False
    assert w.entities["player"].pos == before


def test_move_to_region_avoids_occupied_cells():
    w = small_world()
    assert w.move_to_region("player", "west") is True
    assert w.entities["player"].pos != w.entities["npc"].pos
    assert w.region_of(w.entities["player"].pos) == "west"


# ---- reaction recipe routing (stubbed minds, real thresholds) --------------------------------

def test_reaction_routing_by_appraised_salience():
    sal = {"speaker": 0.95, "mover": 0.80, "quiet": 0.20, "edge": 0.74}
    calls = {"respond": [], "choose": [], "remember": []}

    def stub(slug):
        async def remember(fact, **kw):
            calls["remember"].append((slug, kw.get("magnitude"), kw.get("kind")))
            return sal[slug]
        async def respond(req, **kw):
            calls["respond"].append(slug)
            return '"Watch yourself."'
        async def choose_action(sit, opts, **kw):
            calls["choose"].append(slug)
            return {"action": opts[0], "reason": "keeping an eye on it"}
        return mind(slug.title(), remember=remember, respond=respond, choose_action=choose_action)

    g = bare_game(**{s: stub(s) for s in sal})
    g.world = small_world()
    for i, s in enumerate(sal):
        g.world.entities[s] = Entity(s, (i, 1))

    asyncio.run(g._react_to_player("crosses to the bar", magnitude=0.1))

    appraisals = [c for c in calls["remember"] if c[2] == "player_event"]
    own_acts = [c for c in calls["remember"] if c[2] == "decision"]
    assert len(appraisals) == 4 and all(m == 0.1 for _, m, _ in appraisals)
    # the mover ENACTED a choice -> the mind is told it did (the anti-confabulation write)
    assert [s for s, _, _ in own_acts] == ["mover"]
    assert calls["respond"] == ["speaker"]          # >= SPEAK_SALIENCE -> words
    assert calls["choose"] == ["mover"]             # REACT..SPEAK -> a grounded action beat
    kinds = [e["kind"] for e in g.history]
    assert kinds.count("dialogue") == 1 and kinds.count("npc_act") == 1
    assert all(s not in calls["respond"] + calls["choose"] for s in ("quiet", "edge"))


# ---- per-engine capability threading (the C00 regression) ------------------------------------

def test_reflect_on_turn_honors_caller_wants_over_globals(monkeypatch):
    """EngineCaps-enabled surfaces pass want-flags explicitly; the judgment prompt must include
    the relationship/intent blocks even when the process globals are all False."""
    from orchestrator import salience

    captured = {}

    async def fake_complete(system, prompt, **kw):
        captured["system"] = system
        return ('{"importance": 0.7, "relationship": {"affection_delta": 0.1, "trust_delta": 0.1, '
                '"respect_delta": 0.0, "mood": "warm"}, "intent": "keep them close"}')

    monkeypatch.setattr(salience, "complete", fake_complete)
    rel = SimpleNamespace(affection=0.5, trust=0.5, respect=0.5,
                          scar_affection=0.0, scar_trust=0.0, scar_respect=0.0)
    intent = SimpleNamespace(intent="")
    char = SimpleNamespace(name="Della")
    monkeypatch.setattr(salience, "_character_summary", lambda c: c.name)

    importance, commit, rel_upd, intent_upd = asyncio.run(salience.reflect_on_turn(
        char, "hello", "well met", relationship=rel, intent=intent,
        want_commit=False, want_rel=True, want_intent=True, want_salience=True))
    assert '"relationship"' in captured["system"] and '"intent"' in captured["system"]
    assert rel_upd and rel_upd["d_affection"] == pytest.approx(0.1)
    assert intent_upd == "keep them close"


def test_reflect_on_turn_explicit_empty_intent_clears(monkeypatch):
    from orchestrator import salience

    async def fake_complete(system, prompt, **kw):
        return '{"importance": 0.4, "intent": ""}'

    monkeypatch.setattr(salience, "complete", fake_complete)
    monkeypatch.setattr(salience, "_character_summary", lambda c: c.name)
    _, _, _, intent_upd = asyncio.run(salience.reflect_on_turn(
        SimpleNamespace(name="D"), "u", "a", intent=SimpleNamespace(intent="old aim"),
        want_commit=False, want_rel=False, want_intent=True, want_salience=True))
    assert intent_upd == ""  # an explicit empty aim must CLEAR, not silently keep, the old one


def test_intent_state_set_empty_clears():
    from orchestrator.memory.intent import IntentState
    st = IntentState(intent="find out who sent them")
    st.set("")
    assert st.intent == ""


def test_engine_caps_overrides_and_new_field():
    s = Settings(relationship_state=False, intent_state=False, background_reflection=False)
    caps = EngineCaps.from_settings(s, relationship_state=True, background_reflection=True,
                                    recent_happenings_window=6.0)
    assert caps.relationship_state and caps.background_reflection
    assert caps.recent_happenings_window == 6.0
    assert caps.intent_state is False  # non-overridden fields keep the settings value
