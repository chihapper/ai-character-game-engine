"""Character profiles: load / list / save the YAML files in `characters/`.

A character is the unit the user talks to: a name, a personality (system prompt),
a TTS provider + cloned/preset voice, a greeting, and a memory namespace. The
in-app Create Character flow writes these files; a hand-authored YAML works too.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from .config import CHARACTERS_DIR, get_settings


@dataclass
class Character:
    slug: str
    name: str
    system_prompt: str
    voice_id: str
    tts_provider: str = "inworld"
    greeting: str = ""
    memory_namespace: str = ""

    def __post_init__(self) -> None:
        if not self.memory_namespace:
            self.memory_namespace = self.slug

    def to_yaml_dict(self) -> dict:
        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "tts_provider": self.tts_provider,
            "voice_id": self.voice_id,
            "greeting": self.greeting,
            "memory_namespace": self.memory_namespace,
        }

    def public_dict(self) -> dict:
        """Safe-to-send-to-the-browser summary."""
        return {
            "slug": self.slug,
            "name": self.name,
            "tts_provider": self.tts_provider,
            "greeting": self.greeting,
        }


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "character"


def _path_for(slug: str):
    return CHARACTERS_DIR / f"{slug}.yaml"


def load_character(slug: str) -> Character:
    path = _path_for(slug)
    if not path.exists():
        raise FileNotFoundError(f"No character named '{slug}' in {CHARACTERS_DIR}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Character(
        slug=slug,
        name=data.get("name", slug),
        system_prompt=data.get("system_prompt", ""),
        voice_id=data.get("voice_id", ""),
        tts_provider=data.get("tts_provider", get_settings().default_tts_provider),
        greeting=data.get("greeting", ""),
        memory_namespace=data.get("memory_namespace", slug),
    )


def list_characters() -> list[Character]:
    CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
    out: list[Character] = []
    for path in sorted(CHARACTERS_DIR.glob("*.yaml")):
        try:
            out.append(load_character(path.stem))
        except Exception:  # skip malformed files rather than failing the whole list
            continue
    return out


def save_character(character: Character) -> None:
    CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
    path = _path_for(character.slug)
    path.write_text(
        yaml.safe_dump(character.to_yaml_dict(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
