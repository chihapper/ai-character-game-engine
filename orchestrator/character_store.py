"""Character profiles: load / list / save the YAML files in `characters/`.

A character is the unit the user talks to. The engine is game-agnostic: a
character is defined by identity, manner, backstory, knowledge, voice, and a set
of *dramatic* mechanics that apply to any character-driven game — goals, secrets
(with reveal conditions), boundaries, relationships, disposition. The engine
COMPILES these structured fields into the system prompt (`build_prompt`).

Game-specific data (e.g. a D&D 5e sheet) lives in `game_data`, an open namespaced
bag the engine stores and round-trips but never interprets — that's the seam a
game layer plugs into, so the engine itself stays game-agnostic.

Legacy characters that only have a freeform `system_prompt` keep working: if no
structured fields are present, `build_prompt` returns that prompt verbatim. The
in-app Create Character flow writes these files; a hand-authored YAML works too.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from .character_extensions import render_game_data
from .config import CHARACTERS_DIR, get_settings


@dataclass
class Character:
    slug: str
    name: str

    # Voice
    voice_id: str = ""
    tts_provider: str = "elevenlabs"
    greeting: str = ""

    # Identity
    concept: str = ""  # one-line logline
    age: str = ""  # free text, e.g. "mid-50s"
    role: str = ""  # occupation / station
    pronouns: str = ""

    # Manner
    temperament: str = ""
    speech_style: list[str] = field(default_factory=list)

    # Backstory & knowledge
    backstory: str = ""
    knows: list[str] = field(default_factory=list)
    doesnt_know: list[str] = field(default_factory=list)

    # Dramatic / dialogue mechanics (game-agnostic)
    goals: list[str] = field(default_factory=list)
    secrets: list[dict] = field(default_factory=list)  # [{text, reveal_when}]
    boundaries: list[str] = field(default_factory=list)
    relationships: dict = field(default_factory=dict)  # {who: how they're regarded}
    disposition: str = ""  # starting stance toward the player
    sample_lines: list[str] = field(default_factory=list)

    # Game-specific extension — stored verbatim, never interpreted by the engine.
    game_data: dict = field(default_factory=dict)

    # Raw override / legacy freeform prompt (used when no structured fields exist).
    system_prompt: str = ""

    # Memory
    memory_namespace: str = ""

    def __post_init__(self) -> None:
        if not self.memory_namespace:
            self.memory_namespace = self.slug

    # ---------------------------------------------------------------- prompt

    def _has_structured_content(self) -> bool:
        return any(
            [
                self.concept, self.age, self.role, self.temperament,
                self.speech_style, self.backstory, self.knows, self.doesnt_know,
                self.goals, self.secrets, self.boundaries, self.relationships,
                self.disposition, self.sample_lines,
            ]
        )

    def build_prompt(self) -> str:
        """Compile the structured fields into a character system prompt. Falls back
        to the raw `system_prompt` for legacy/hand-authored characters that have no
        structured content."""
        if not self._has_structured_content():
            # Legacy/raw character — but a game may still enrich it via game_data.
            extras = render_game_data(self.game_data)
            if not extras:
                return self.system_prompt
            return "\n\n".join([p for p in (self.system_prompt, *extras) if p])

        parts: list[str] = []

        ident = f"You are {self.name}"
        extra = [b for b in (self.age, self.role) if b]
        if extra:
            ident += ", " + ", ".join(extra)
        ident += "."
        if self.pronouns:
            ident += f" ({self.pronouns})"
        if self.concept:
            ident += f" {self.concept}"
        parts.append("# Who you are\n" + ident)

        manner: list[str] = []
        if self.temperament:
            manner.append(self.temperament)
        manner += [f"- {s}" for s in self.speech_style]
        if manner:
            parts.append("# How you speak\n" + "\n".join(manner))

        if self.backstory:
            parts.append("# Your story\n" + self.backstory.strip())

        knowledge: list[str] = []
        if self.knows:
            knowledge.append("You speak with authority on: " + "; ".join(self.knows) + ".")
        if self.doesnt_know:
            knowledge.append(
                "You have no knowledge of, and treat as outside your world: "
                + "; ".join(self.doesnt_know) + "."
            )
        if knowledge:
            parts.append("# What you know\n" + "\n".join(knowledge))

        if self.goals:
            parts.append("# What you want\n" + "\n".join(f"- {g}" for g in self.goals))

        secret_lines = []
        for s in self.secrets:
            text = (s.get("text") or "").strip()
            if not text:
                continue
            reveal = (s.get("reveal_when") or "").strip()
            secret_lines.append(
                f"- {text}" + (f" Reveal this only if: {reveal}." if reveal else " Never reveal this.")
            )
        if secret_lines:
            parts.append(
                "# Secrets you keep\n"
                "You hold these back. Do not volunteer them; stay in character if pressed:\n"
                + "\n".join(secret_lines)
            )

        if self.boundaries:
            parts.append(
                "# Lines you won't cross\n" + "\n".join(f"- {b}" for b in self.boundaries)
            )

        if self.relationships:
            rel = [f"- {who}: {how}" for who, how in self.relationships.items() if how]
            if rel:
                parts.append("# How you regard others\n" + "\n".join(rel))

        if self.disposition:
            parts.append(
                "# Your disposition right now\n"
                + self.disposition.strip()
                + " This can shift over the course of the conversation."
            )

        if self.sample_lines:
            lines = ["For tone only — capture this voice, but never repeat these verbatim:"]
            lines += [f'- "{l}"' for l in self.sample_lines]
            parts.append("# A few lines in your voice\n" + "\n".join(lines))

        # Let any game with a registered renderer add its own depth (game_data).
        parts.extend(render_game_data(self.game_data))

        return "\n\n".join(parts)

    # ----------------------------------------------------------------- yaml

    def to_yaml_dict(self) -> dict:
        """Serialize for storage. Empty fields are omitted to keep files tidy."""
        data: dict = {"name": self.name}
        # Voice
        data["tts_provider"] = self.tts_provider
        data["voice_id"] = self.voice_id
        if self.greeting:
            data["greeting"] = self.greeting
        # Identity
        for key in ("concept", "age", "role", "pronouns", "temperament"):
            if getattr(self, key):
                data[key] = getattr(self, key)
        if self.speech_style:
            data["speech_style"] = self.speech_style
        if self.backstory:
            data["backstory"] = self.backstory
        for key in ("knows", "doesnt_know", "goals", "boundaries", "sample_lines"):
            if getattr(self, key):
                data[key] = getattr(self, key)
        if self.secrets:
            data["secrets"] = self.secrets
        if self.relationships:
            data["relationships"] = self.relationships
        if self.disposition:
            data["disposition"] = self.disposition
        if self.game_data:
            data["game_data"] = self.game_data
        if self.system_prompt:
            data["system_prompt"] = self.system_prompt
        data["memory_namespace"] = self.memory_namespace
        return data

    def public_dict(self) -> dict:
        """Safe-to-send-to-the-browser summary."""
        return {
            "slug": self.slug,
            "name": self.name,
            "concept": self.concept,
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
        voice_id=data.get("voice_id", ""),
        tts_provider=data.get("tts_provider", get_settings().default_tts_provider),
        greeting=data.get("greeting", ""),
        concept=data.get("concept", ""),
        age=data.get("age", ""),
        role=data.get("role", ""),
        pronouns=data.get("pronouns", ""),
        temperament=data.get("temperament", ""),
        speech_style=data.get("speech_style", []) or [],
        backstory=data.get("backstory", ""),
        knows=data.get("knows", []) or [],
        doesnt_know=data.get("doesnt_know", []) or [],
        goals=data.get("goals", []) or [],
        secrets=data.get("secrets", []) or [],
        boundaries=data.get("boundaries", []) or [],
        relationships=data.get("relationships", {}) or {},
        disposition=data.get("disposition", ""),
        sample_lines=data.get("sample_lines", []) or [],
        game_data=data.get("game_data", {}) or {},
        system_prompt=data.get("system_prompt", ""),
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


def delete_character(slug: str) -> bool:
    """Delete a character's file. Returns True if it existed. Conversation memories
    in the long-term store are keyed by namespace and are left untouched."""
    path = _path_for(slug)
    if path.exists():
        path.unlink()
        return True
    return False
