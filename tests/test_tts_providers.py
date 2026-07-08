"""The TTS provider registry — the single source of truth for pick-your-TTS + BYO-key."""
from __future__ import annotations

import os
from types import SimpleNamespace

from orchestrator import tts_providers as R


def test_ready_vs_coming_soon():
    ready = {p.name for p in R.ready_providers()}
    assert ready == {"hume", "inworld"}, "only the verified providers ship ready"
    statuses = {p.name: p.status for p in R.list_providers()}
    for late in ("elevenlabs", "cartesia", "fish", "chatterbox"):
        assert statuses[late] == R.COMING_SOON


def test_list_is_ready_first():
    order = [p.ready for p in R.list_providers()]
    assert order == sorted(order, reverse=True), "ready providers list before coming-soon"


def test_caps_drive_behavior_not_names():
    # the pipeline's batch decision is a declared capability, not `provider == "inworld"`
    assert R.caps("inworld").batch is True
    assert R.caps("hume").batch is False
    assert R.caps("hume").continuation is True
    assert R.caps("inworld").continuation is False


def test_unknown_provider_falls_back_to_default():
    assert R.get_provider("does-not-exist").name == "inworld"
    assert R.caps("does-not-exist").batch is True  # resolved to the inworld default


def test_missing_keys_reports_the_env_var():
    hume = R.get_provider("hume")
    assert hume.missing_keys(SimpleNamespace(hume_api_key="")) == ["HUME_API_KEY"]
    assert hume.missing_keys(SimpleNamespace(hume_api_key="sk-xyz")) == []
    # a local provider needs no key
    assert R.get_provider("chatterbox").missing_keys(SimpleNamespace()) == []


def test_public_dict_shape():
    d = R.get_provider("hume").public_dict()
    assert d["name"] == "hume" and d["status"] == "ready"
    assert d["requires_keys"] == ["HUME_API_KEY"]
    assert "capabilities" in d and d["capabilities"]["continuation"] is True


def test_set_provider_key_writes_env_and_refreshes(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    R.set_provider_key("elevenlabs", "byo-test-key")
    assert os.environ["ELEVENLABS_API_KEY"] == "byo-test-key"
    from orchestrator.config import get_settings
    assert get_settings().elevenlabs_api_key == "byo-test-key"
