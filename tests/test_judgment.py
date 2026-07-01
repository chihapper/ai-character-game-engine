"""The shared judgment parsing/salvage (orchestrator/judgment.py) — pure, no network. Truncated
model output must yield every complete field rather than losing the whole judgment."""
from orchestrator.judgment import model_for, parse_json, salvage_json

TRUNCATED = ('{"reflection": "a long thought", "changed": true, "weight": 0.7, '
             '"new_goals": ["keep the act alive", "find Theo"], "world_action": "he stands and cro')


def test_salvage_recovers_complete_fields():
    d = salvage_json(TRUNCATED)
    assert d["reflection"] == "a long thought"
    assert d["changed"] is True
    assert d["weight"] == 0.7
    assert d["new_goals"] == ["keep the act alive", "find Theo"]
    assert "world_action" not in d  # cut mid-string: absent, never corrupted


def test_salvage_unescapes_strings():
    assert salvage_json('{"a": "he said \\"go\\""')["a"] == 'he said "go"'


def test_parse_json_prefers_clean_then_salvages():
    assert parse_json('noise {"a": 1} noise') == {"a": 1}
    assert parse_json(TRUNCATED)["changed"] is True
    assert parse_json("no json at all") is None
    assert parse_json("") is None


def test_model_for_roles_resolve_and_override_wins():
    for role in ("salience", "deliberation", "reflection"):
        assert isinstance(model_for(role), str) and model_for(role)
    assert model_for("salience", "override-model") == "override-model"
