"""The #30 lab-notebook logger (game/experiment_log.py) — user-flagged as VITAL. Marker-bounded
edits only; the protocol text above the RUNS table must never be touched."""
import shutil
from pathlib import Path

import pytest

from game import experiment_log as L

REAL_DOC = Path(__file__).resolve().parents[1] / "docs" / "embodiment-experiment.md"


@pytest.fixture
def doc(tmp_path):
    d = tmp_path / "exp.md"
    shutil.copy(REAL_DOC, d)
    return d


def test_start_update_finalize_roundtrip(doc):
    protocol_before = doc.read_text(encoding="utf-8").split(L._START)[0]
    r1 = L.start_run(condition="CTRL-TEXT", scenario="ferry-crossing",
                     characters=["della", "corvin"], models="reply=x", doc=doc)
    r2 = L.start_run(condition="TREAT-EMBODIED", scenario="ferry-crossing",
                     characters=["della"], models="reply=y", doc=doc)
    assert r1 != r2
    assert L.update_run(r1, transcript=f".game_runs/{r1}.jsonl", doc=doc)
    assert L.finalize_run(r1, "he was hidden at dawn", rr_judge="0.91", doc=doc)
    text = doc.read_text(encoding="utf-8")
    assert text.split(L._START)[0] == protocol_before        # protocol untouched
    assert text.count(L._START) == 1 and text.count(L._END) == 1
    row1 = next(ln for ln in text.splitlines() if ln.startswith(f"| {r1} "))
    assert "he was hidden at dawn" in row1 and "0.91" in row1
    row2 = next(ln for ln in text.splitlines() if ln.startswith(f"| {r2} "))
    assert "(in progress)" in row2                            # r1's edits never touched r2


def test_unknown_run_is_a_noop(doc):
    before = doc.read_text(encoding="utf-8")
    assert L.update_run("does-not-exist", outcome="nope", doc=doc) is False
    assert doc.read_text(encoding="utf-8") == before


def test_cells_are_sanitized(doc):
    rid = L.start_run(condition="MID-RICHTEXT", scenario="s", characters="a|b",
                      models="x\ny", doc=doc)
    row = next(ln for ln in doc.read_text(encoding="utf-8").splitlines()
               if ln.startswith(f"| {rid} "))
    assert row.count("|") == len(L.COLUMNS) + 1               # pipes/newlines can't break the table


def test_missing_markers_raise(tmp_path):
    bad = tmp_path / "no-markers.md"
    bad.write_text("nothing here", encoding="utf-8")
    with pytest.raises(RuntimeError):
        L.start_run(condition="X", scenario="y", characters=[], models="", doc=bad)
