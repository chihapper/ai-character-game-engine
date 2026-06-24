"""Speaker cadence profiles: load / list / save / delete the YAML files in
`profiles/`. Each profile holds the end-of-turn timings learned from a person's
calibration recording, so the engine adapts to how they actually speak.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from .config import PROFILES_DIR


@dataclass
class Profile:
    slug: str
    name: str
    min_turn_silence: int
    max_turn_silence: int
    stats: dict = field(default_factory=dict)

    def to_yaml_dict(self) -> dict:
        return {
            "name": self.name,
            "min_turn_silence": self.min_turn_silence,
            "max_turn_silence": self.max_turn_silence,
            "stats": self.stats,
        }

    def public_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "min_turn_silence": self.min_turn_silence,
            "max_turn_silence": self.max_turn_silence,
            "stats": self.stats,
        }


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "speaker"


def _path_for(slug: str):
    return PROFILES_DIR / f"{slug}.yaml"


def load_profile(slug: str) -> Profile:
    path = _path_for(slug)
    if not path.exists():
        raise FileNotFoundError(f"No profile '{slug}' in {PROFILES_DIR}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Profile(
        slug=slug,
        name=data.get("name", slug),
        min_turn_silence=int(data.get("min_turn_silence", 300)),
        max_turn_silence=int(data.get("max_turn_silence", 1800)),
        stats=data.get("stats", {}) or {},
    )


def list_profiles() -> list[Profile]:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    out: list[Profile] = []
    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        try:
            out.append(load_profile(path.stem))
        except Exception:
            continue
    return out


def save_profile(profile: Profile) -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    _path_for(profile.slug).write_text(
        yaml.safe_dump(profile.to_yaml_dict(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def delete_profile(slug: str) -> bool:
    path = _path_for(slug)
    if path.exists():
        path.unlink()
        return True
    return False
