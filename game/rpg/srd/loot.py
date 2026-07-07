"""Original loot tables as data — the game grants what these return.

The table structure, drop design, and all trinket prose in `data/loot.json` are original; no
published random-treasure table is reproduced or adapted. A few generic equipment names and the
healing-draught dice tiers are adapted from SRD 5.1 items (attributed — see LICENSE-SRD.md).
Tables are banded by the threat just beaten — band0 is copper-and-string fodder scraps, band3 is
veteran spoils — and `roll_loot` is the one entry point: gold always rolls, an item may drop, a
trinket (pure flavor) sometimes rides along. Deterministic for a given `random.Random`, so a
seeded harness run replays.

Item dicts returned here map 1:1 onto `game.rpg.state.Item` kwargs (id / name / kind / data);
ids are kebab-case ascii. Ids deliberately avoid any word a slice could use for a gated-door
objective item, so a loot grant can never collide with that game-owned refusal guard
(`RpgGame._grant_item`). This module rolls and describes; it never touches game state — the
game layer decides when to call it (combat victory) and narrates the `describe(...)` line.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from .dice import Dice

_PATH = Path(__file__).resolve().parent / "data" / "loot.json"
_TABLES: dict | None = None

TRINKET_CHANCE = 0.35        # flavor finds are common enough to feel alive, rare enough to land
SECOND_DROP_CHANCE = 0.30    # band2+ only: tougher fights can shake loose a second item


def load() -> dict:
    """The loot tables, read from `data/loot.json` once and cached for the process."""
    global _TABLES
    if _TABLES is None:
        _TABLES = json.loads(_PATH.read_text(encoding="utf-8"))
    return _TABLES


def band_for(max_cr: float) -> str:
    """Map the toughest defeated CR to a table band: <1 fodder, 1-2, 3-4, 5+ veteran."""
    if max_cr < 1:
        return "band0"
    if max_cr < 3:
        return "band1"
    if max_cr < 5:
        return "band2"
    return "band3"


def roll_loot(crs: list[float], rng: random.Random) -> dict:
    """Roll victory spoils for a defeated group of CRs.

    Returns ``{"gold": int, "items": [{id, name, kind, data}, ...], "trinket": str | None}``.
    Gold always rolls (banded dice); an item drops per the band's `drop_chance` (one weighted
    pick, with a second lower-chance pick possible on band2+); a trinket has its own modest
    chance. Same seed -> same loot: every draw comes from the passed-in `rng`.
    """
    band_name = band_for(max(crs) if crs else 0.0)
    band = load()[band_name]
    gold = Dice(rng).roll(band["coins"])

    items: list[dict] = []
    pool = band["items"]
    weights = [int(it.get("weight", 1)) for it in pool]

    def _pick() -> dict:
        it = rng.choices(pool, weights=weights, k=1)[0]
        return {"id": it["id"], "name": it["name"], "kind": it.get("kind", "misc"),
                "data": dict(it.get("data") or {})}

    if rng.random() < float(band["drop_chance"]):
        items.append(_pick())
        if band_name in ("band2", "band3") and rng.random() < SECOND_DROP_CHANCE:
            second = _pick()
            if second["id"] == items[0]["id"]:   # no double drops of the same item — re-pick once
                second = _pick()
            if second["id"] != items[0]["id"]:
                items.append(second)

    trinket = rng.choice(band["trinkets"]) if rng.random() < TRINKET_CHANCE else None
    return {"gold": int(gold), "items": items, "trinket": trinket}


def describe(loot: dict) -> str:
    """One narratable line for a loot roll — '12 gold, a healing draught, and a wolf-tooth charm
    on a leather cord'. Empty loot -> '' (the game narrates nothing). No trailing period."""
    parts: list[str] = []
    gold = int(loot.get("gold") or 0)
    if gold > 0:
        parts.append(f"{gold} gold")
    parts.extend(it["name"] for it in loot.get("items") or [])
    trinket = loot.get("trinket")
    if trinket:
        parts.append(trinket)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"
