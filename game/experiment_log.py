"""Embodiment-experiment run log (#30).

Appends a row to the RUNS table in docs/embodiment-experiment.md when a playthrough starts, and
fills the metric columns post-hoc. It edits ONLY the content between the
`<!-- RUNS_TABLE_START -->` / `<!-- RUNS_TABLE_END -->` markers, so the static protocol above is
never touched. Pure file I/O + markdown-table editing — no engine imports — so it's trivially
testable in isolation (pass `doc=` a temp copy). See docs/embodiment-experiment.md.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# One lock for every table edit: start/update are unlocked read-modify-write cycles over a shared
# markdown file — two concurrent runs (or a run-start racing a finalize) silently dropped rows.
_IO_LOCK = threading.Lock()

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "embodiment-experiment.md"
_START = "<!-- RUNS_TABLE_START -->"
_END = "<!-- RUNS_TABLE_END -->"

# Column order == the RUNS table. run_id is the key; metric columns fill in post-hoc.
COLUMNS = ["run_id", "started", "condition", "scenario", "characters",
           "models", "transcript", "outcome", "rr_judge", "emergence", "human_note"]


def _cell(v) -> str:
    """A safe single markdown cell: no pipes/newlines; empty -> em-dash (means 'pending')."""
    s = "" if v is None else str(v)
    s = s.replace("|", "/").replace("\n", " ").strip()
    return s or "—"


def _row(values: dict) -> str:
    return "| " + " | ".join(_cell(values.get(c)) for c in COLUMNS) + " |"


def _split(text: str):
    """(before, block, after) around the markers. Raises if the markers are missing."""
    if _START not in text or _END not in text:
        raise RuntimeError(f"RUNS markers not found in {DOC_PATH.name}; cannot log runs")
    before, rest = text.split(_START, 1)
    block, after = rest.split(_END, 1)
    return before, block, after


def _data_rows(block: str) -> list[str]:
    """Existing data rows between the markers (skip the header + separator rows)."""
    out = []
    for ln in block.splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and cells[0] == "run_id":              # header row
            continue
        if cells and set("".join(cells)) <= set("-: "):  # separator row
            continue
        out.append(s)
    return out


def _block(rows: list[str]) -> str:
    header = "| " + " | ".join(COLUMNS) + " |"
    sep = "| " + " | ".join("---" for _ in COLUMNS) + " |"
    return "\n" + "\n".join([header, sep] + rows) + "\n"


def _cells_of(row: str) -> dict:
    cells = [c.strip() for c in row.strip("|").split("|")]
    return dict(zip(COLUMNS, cells + [""] * (len(COLUMNS) - len(cells))))


def start_run(*, condition: str, scenario: str, characters, models,
              transcript: str = "", doc: Path | str = DOC_PATH) -> str:
    """Append a run-start row; return the generated run_id."""
    doc = Path(doc)
    ts = datetime.now()
    run_id = f"{condition}-{ts.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:3]}"
    chars = characters if isinstance(characters, str) else ", ".join(characters)
    mdls = models if isinstance(models, str) else " ".join(str(m) for m in models)
    values = {"run_id": run_id, "started": ts.strftime("%Y-%m-%d %H:%M:%S"),
              "condition": condition, "scenario": scenario, "characters": chars,
              "models": mdls, "transcript": transcript, "outcome": "(in progress)"}
    with _IO_LOCK:
        before, block, after = _split(doc.read_text(encoding="utf-8"))
        rows = _data_rows(block) + [_row(values)]
        doc.write_text(before + _START + _block(rows) + _END + after, encoding="utf-8")
    return run_id


def update_run(run_id: str, *, doc: Path | str = DOC_PATH, **fields) -> bool:
    """Set named columns (outcome/rr_judge/emergence/human_note/transcript/...) for `run_id`.
    Returns True if the row was found."""
    doc = Path(doc)
    with _IO_LOCK:
        before, block, after = _split(doc.read_text(encoding="utf-8"))
        rows = _data_rows(block)
        found = False
        for i, r in enumerate(rows):
            values = _cells_of(r)
            if values.get("run_id") == run_id:
                for k, v in fields.items():
                    if k in COLUMNS:
                        values[k] = _cell(v)
                rows[i] = _row(values)
                found = True
                break
        if found:
            doc.write_text(before + _START + _block(rows) + _END + after, encoding="utf-8")
    return found


def finalize_run(run_id: str, outcome: str, *, doc: Path | str = DOC_PATH, **fields) -> bool:
    """Close out a run row with its outcome (and optionally metrics)."""
    return update_run(run_id, doc=doc, outcome=outcome, **fields)
