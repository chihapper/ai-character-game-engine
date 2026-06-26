"""Re-score a character's stored long-term memories with character-aware salience.

Memories written before salience scoring existed (or before a profile/model change) keep
their old flat `importance`. This re-rates each one *for this character* and rewrites the
store, so recall reflects what THEY would actually find memorable. The original is backed
up to `<store>.jsonl.bak` first.

Usage:
    python -m tools.backfill_salience <character-slug>
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from orchestrator.character_store import load_character
from orchestrator.config import get_settings
from orchestrator.memory.long_term import _safe_name
from orchestrator.salience import score_salience_text


async def backfill(slug: str) -> None:
    character = load_character(slug)
    path = Path(get_settings().memory_dir) / f"{_safe_name(character.memory_namespace)}.jsonl"
    if not path.exists():
        print(f"No memory store for '{slug}' at {path}")
        return

    records = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"Re-scoring {len(records)} memories for {character.name} (model: "
          f"{get_settings().salience_model})...\n")

    backup = path.with_name(path.name + ".bak")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    for r in records:
        old = float(r.get("importance", 0.5))
        new = await score_salience_text(character, r.get("text", ""))
        r["importance"] = new
        flag = "   <-- big change" if abs(new - old) >= 0.3 else ""
        print(f"  {old:.2f} -> {new:.2f}  {r.get('text','')[:56]!r}{flag}")

    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8"
    )
    print(f"\nDone — {len(records)} memories re-scored. Backup: {backup.name}")
    print("Reconnect in the browser to pick up the new importances.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m tools.backfill_salience <character-slug>")
        sys.exit(1)
    asyncio.run(backfill(sys.argv[1]))
