"""SRD-derived + original creature stat blocks as DATA — phase 3 of the game-layer rules system.

The bestiary is a pure-content JSON file (`data/bestiary.json`) plus this thin query/factory layer.
Stat NUMBERS derive from the SRD 5.1 under CC-BY-4.0 (see LICENSE-SRD.md at the repo root — game
mechanics aren't copyrightable and the data grant is attributed there); all PROSE (names of original
creatures, every `blurb`) is our own wording. A few creatures (e.g. the cinder-husk, the
vault-drowned) are entirely original.

Entries are keyed by slug and carry `tags` ("dungeon", "cavern", "undead", "water", "fire", ...)
so a slice can pull a themed palette with `slugs(tags=[...], max_cr=...)` instead of hand-building
`Enemy` objects in `content.py`. `make_enemy` is the one factory: it maps an entry onto the
game-owned `Enemy` sheet (`game/rpg/state.py`), including the attack profile, resist/immune/vuln
lists, and a proficiency bonus derived from CR via `mechanics.proficiency_bonus_for_cr`.

Treat `load()`'s dict as read-only — it is cached module-wide; `make_enemy` copies what it takes.

Known-unconsumed data: each entry's `attack.ranged` flag is carried for the future ranged-combat
pass but is NOT yet threaded into the combat engine (`Combatant` has no ranged field; every
shipped fight is adjacent melee) — do not rely on it having any effect yet.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from .mechanics import proficiency_bonus_for_cr

if TYPE_CHECKING:  # imported lazily inside make_enemy at runtime (state <-> srd import-cycle guard)
    from ..state import Enemy

_DATA_PATH = Path(__file__).parent / "data" / "bestiary.json"


@lru_cache(maxsize=1)
def load() -> dict:
    """The whole bestiary, slug -> entry dict. Cached after the first read; treat as read-only."""
    with _DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def entry(slug: str) -> dict:
    """One creature's raw entry. Raises a KeyError that lists the known slugs on an unknown one."""
    data = load()
    if slug not in data:
        raise KeyError(f"unknown creature {slug!r}; known slugs: {', '.join(sorted(data))}")
    return data[slug]


def cr(slug: str) -> float:
    """The creature's Challenge Rating as a float (fractional CRs like 1/8 -> 0.125)."""
    return float(entry(slug)["cr"])


def slugs(*, tags: list[str] | None = None, max_cr: float | None = None,
          min_cr: float = 0.0) -> list[str]:
    """Palette query: slugs filtered by tag overlap and CR band, sorted by (cr, slug).

    `tags` matches if the creature shares AT LEAST ONE of the given tags (union, case-insensitive),
    so a wet-dungeon slice can ask for `tags=["dungeon", "water"]` and get the whole palette.
    `min_cr`/`max_cr` are inclusive bounds. No filters -> every slug.
    """
    data = load()
    want = {t.strip().lower() for t in tags} if tags else None
    out: list[str] = []
    for slug, e in data.items():
        c = float(e.get("cr", 0.0))
        if c < min_cr or (max_cr is not None and c > max_cr):
            continue
        if want is not None and want.isdisjoint({str(t).strip().lower() for t in e.get("tags", [])}):
            continue
        out.append(slug)
    return sorted(out, key=lambda s: (float(data[s].get("cr", 0.0)), s))


def make_enemy(slug: str, *, id: str, pos=None, name: str | None = None,
               mind_slug: str | None = None) -> "Enemy":
    """Build a game-owned `Enemy` sheet from a bestiary entry — the replacement for hand-building
    stat blocks in `content.py`.

    `kind` is the bestiary slug (so drops/XP/labels can key off it); `name` lets a slice override
    the display name (e.g. "Cinder-husk" vs a renamed champion); `mind_slug` promotes a generic
    stat block to an engine mind. HP starts full; proficiency bonus derives from CR.
    """
    from ..state import Enemy, Stats  # lazy: state is a sibling of srd/, avoid import cycles

    e = entry(slug)
    atk = e.get("attack", {})
    c = float(e.get("cr", 0.0))
    hp = int(e["hp"])
    return Enemy(
        id=id,
        name=name or e["name"],
        kind=slug,
        max_hp=hp,
        hp=hp,
        ac=int(e["ac"]),
        stats=Stats(**e.get("stats", {})),
        pos=pos,
        mind_slug=mind_slug,
        damage_dice=str(atk.get("damage_dice", "1d4")),
        attack_ability=str(atk.get("ability", "STR")).upper(),
        damage_type=str(atk.get("damage_type", "")),
        saving_throw_profs=list(e.get("saves", [])),
        skill_profs=list(e.get("skills", [])),
        resistances=list(e.get("resistances", [])),
        immunities=list(e.get("immunities", [])),
        vulnerabilities=list(e.get("vulnerabilities", [])),
        condition_immunities=list(e.get("condition_immunities", [])),
        speed=int(e.get("speed", 30)),
        size=str(e.get("size", "medium")),
        creature_type=str(e.get("creature_type", "")),
        cr=c,
        hit_dice=str(e.get("hit_dice", "")),
        prof_bonus=proficiency_bonus_for_cr(c),
    )
