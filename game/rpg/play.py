"""Play the Sunken Vault in the terminal (Phase A dev view).

    .venv/Scripts/python.exe -m game.rpg.play

Env: RPG_SEED (default 1337), RPG_MODEL (default claude-haiku-4-5). Needs a display + a monospace
TTF (see tcod_view._tileset) and ANTHROPIC_API_KEY in .env for the NPC minds.
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")

from game.rpg.game import RpgGame  # noqa: E402
from game.rpg.tcod_view import run  # noqa: E402


def main() -> None:
    seed = int(os.environ.get("RPG_SEED", "1337"))
    model = os.environ.get("RPG_MODEL", "claude-haiku-4-5")
    print(f"[sunken-vault] seed={seed} reply_model={model} — opening the dev view...")
    run(RpgGame.new(seed=seed, reply_model=model))


if __name__ == "__main__":
    main()
