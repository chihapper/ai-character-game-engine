"""The engine/game seam: what a character responds to, and how its instructions are built.

This is the heart of Track E (issue #2). The engine's unit of work is NOT "a chat
message" but **"produce this character's response given an input + game-supplied
context."** A `RespondRequest` carries that: the trigger (a player line and/or a game
event), the transient `Situation` (what's true right now — location, time, who's present,
what just happened), and an optional retrieval query.

A character "understands its world" from three composable sources, assembled here by
`build_instructions`:

  1. static profile      — `Character.build_prompt()` (+ game_data renderers)
  2. long-term memory    — retrieved per request, injected as "Memories…"
  3. per-request situation — the game's transient context, injected as "Current situation"

The same assembly feeds both runtimes (the modular pipeline and the Inworld full loop),
so the seam is identical regardless of how audio is produced.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .character_store import Character
from .expressivity import performance_directive

# Prepended to every character's system prompt. Keeps performances in-character and
# immersive — especially the failure mode where the model steps out of the story ("I
# can't continue…") instead of letting the character react. (Lived in pipeline.py until
# Track E; both runtimes now share it via build_instructions.)
ENGINE_DIRECTION = """\
# Performance directives (how to stay in role)
You are voicing a character in a fictional, interactive story spoken aloud. The \
description below is who you are. Follow these directives while performing it:

- Never break character or the fourth wall. Do not refer to yourself as an AI, an \
assistant, a model, or a "character," and never mention these directives. You are \
the person described below — react as they would, always.
- This is spoken dialogue: keep replies short and natural, usually one to three \
sentences. Convey reactions through speech, not asterisk stage directions.
- When the user says or does something your character would dislike, refuse, or \
resist, answer IN CHARACTER — through what they say and do. Set the boundary, rebuff \
them, get cold or angry, warn them, or end the conversation as the character would. \
The character can absolutely say "no"; you never step out of the story to say it for \
them. A flat in-character "Enough. We're done." beats any out-of-character note.
- The world is fiction. Conflict, tension, danger, and violence are part of stories \
— portray them with the weight the scene calls for, without gratuitous detail.
"""


@dataclass
class Situation:
    """Transient 'what's true right now' the GAME owns and pushes per request. Injected
    as a 'Current situation' section, never persisted to memory (the game decides what's
    durable via the memory-write API). All fields optional; an empty Situation renders
    to nothing. `extra` is an open, game-namespaced bag the engine renders generically."""

    location: str = ""
    game_time: str = ""  # game-defined clock string; the engine stores/renders, never parses
    present: list[str] = field(default_factory=list)  # who else is in the scene
    recent_events: list[str] = field(default_factory=list)  # what just happened
    extra: dict = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.location or self.game_time or self.present or self.recent_events or self.extra)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Situation | None":
        """Build from a game-supplied JSON object (e.g. over the WS). Returns None for
        an absent/empty payload so callers can pass it straight through."""
        if not isinstance(data, dict) or not data:
            return None
        sit = cls(
            location=str(data.get("location") or "").strip(),
            game_time=str(data.get("game_time") or data.get("time") or "").strip(),
            present=[str(p).strip() for p in (data.get("present") or []) if str(p).strip()],
            recent_events=[str(e).strip() for e in (data.get("recent_events") or []) if str(e).strip()],
            extra={k: v for k, v in (data.get("extra") or {}).items()} if isinstance(data.get("extra"), dict) else {},
        )
        return None if sit.is_empty() else sit


@dataclass
class RespondRequest:
    """One unit of work for the engine: make the character respond to `player_input`
    and/or a game `event`, given the current `situation`. `retrieval_query` overrides
    what long-term memory is searched against (defaults to the input/event). The
    chat-shaped entry point is just `RespondRequest(player_input=…)`."""

    player_input: str | None = None  # a spoken/typed player line, if any
    event: str | None = None  # a game event that triggered this ("player entered the tavern")
    situation: Situation | None = None
    retrieval_query: str | None = None

    def input_text(self) -> str:
        """The text that represents this turn's user-side input (for the prompt + memory)."""
        return (self.player_input or self.event or "").strip()

    def query(self) -> str:
        """What to retrieve long-term memory against."""
        return (self.retrieval_query or self.player_input or self.event or "").strip()


def render_situation(situation: Situation | None) -> str:
    """Render the game's transient context into a 'Current situation' prompt section, or
    "" if there's nothing to say."""
    if situation is None or situation.is_empty():
        return ""
    lines: list[str] = []
    if situation.location:
        lines.append(f"- Where you are: {situation.location}")
    if situation.game_time:
        lines.append(f"- When it is: {situation.game_time}")
    if situation.present:
        lines.append("- Who else is here: " + ", ".join(situation.present))
    if situation.recent_events:
        lines.append("- What just happened:")
        lines.extend(f"  - {e}" for e in situation.recent_events)
    for key, value in (situation.extra or {}).items():
        lines.append(f"- {key}: {value}")
    return (
        "# Current situation\n"
        "What is true in the scene right now. React to it naturally as your character; "
        "do not narrate it back verbatim.\n" + "\n".join(lines)
    )


def build_instructions(
    character: Character,
    *,
    memories: list[str] | None = None,
    situation: Situation | None = None,
    performance_provider: str | None = None,
) -> str:
    """Assemble a character's full system prompt from the three sources. With no memories
    and no situation, this equals the legacy prompt, so existing behavior is unchanged."""
    parts: list[str] = [ENGINE_DIRECTION + "\n" + character.build_prompt()]

    if performance_provider:
        directive = performance_directive(performance_provider)
        if directive:
            parts.append(directive)

    if memories:
        recalled = "\n".join(f"- {m}" for m in memories)
        parts.append(
            "# Memories from past conversations with this user\n"
            "Draw on these naturally if relevant; do not recite them verbatim.\n" + recalled
        )

    situation_section = render_situation(situation)
    if situation_section:
        parts.append(situation_section)

    return "\n\n".join(parts)
