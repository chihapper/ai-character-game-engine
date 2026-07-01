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
- Know only what you'd know. Your knowledge is what this description gives you plus \
what you've actually lived with this player (your memories below). You are NOT \
omniscient. If asked about something outside your world, your expertise, or your \
memory, don't invent it — be honestly uncertain or ignorant in character ("Never heard \
of it." / "How would I know that?"). Never fabricate facts, people, places, or a shared \
past you were never given.
- Hold your ground on what's true. If the player asserts something that contradicts \
what you know or remember, don't just accept it — notice the discrepancy and react as \
your character would: correct them, get suspicious, or press them on it.
"""


@dataclass
class Situation:
    """Transient 'what's true right now' the GAME owns and pushes per request. Injected
    as a 'Current situation' section, never persisted to memory (the game decides what's
    durable via the memory-write API). All fields optional; an empty Situation renders
    to nothing. `extra` is an open, game-namespaced bag the engine renders generically."""

    location: str = ""
    game_time: str = ""  # game-defined clock STRING for display; the engine never parses it
    present: list[str] = field(default_factory=list)  # who else is in the scene
    recent_events: list[str] = field(default_factory=list)  # what just happened
    extra: dict = field(default_factory=dict)
    # Numeric game clock for temporal decay (issue #5): a single monotonic number whose units
    # the GAME owns (days/ticks/turns/seconds). The engine only takes differences — never
    # rendered, never interpreted. Optional; absent -> memory falls back to index recency.
    clock: float | None = None

    def is_empty(self) -> bool:
        # `clock` counts: a clock-only Situation must survive from_dict so decay still gets it
        # (render_situation separately renders nothing when there are no DISPLAY fields).
        return not (self.location or self.game_time or self.present or self.recent_events
                    or self.extra or self.clock is not None)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Situation | None":
        """Build from a game-supplied JSON object (e.g. over the WS). Returns None for
        an absent/empty payload so callers can pass it straight through."""
        if not isinstance(data, dict) or not data:
            return None
        raw_clock = data.get("clock")
        if raw_clock is None:
            raw_clock = data.get("t")
        sit = cls(
            location=str(data.get("location") or "").strip(),
            game_time=str(data.get("game_time") or data.get("time") or "").strip(),
            present=[str(p).strip() for p in (data.get("present") or []) if str(p).strip()],
            recent_events=[str(e).strip() for e in (data.get("recent_events") or []) if str(e).strip()],
            extra={k: v for k, v in (data.get("extra") or {}).items()} if isinstance(data.get("extra"), dict) else {},
            clock=float(raw_clock) if isinstance(raw_clock, (int, float)) else None,
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


def build_arena_query(
    request: RespondRequest,
    character: Character,
    recent_messages: list[dict] | None = None,
    *,
    max_recent_turns: int = 2,
    include_goals: bool = True,
    relationship_hint: str = "",
    goals: list[str] | None = None,
) -> str:
    """Compose the long-term retrieval query — the *arena* the agent is in, not just the
    last line. Relevance realization: what's relevant is relative to the situation + the
    agent's goals, and referents ("her", "it", "my drink") live in the surrounding context.
    So we fold the trigger together with recent conversation, the live `Situation`, and the
    character's goals, then embed *that*. An explicit `request.retrieval_query` overrides it.

    Kept compact (recent turns truncated, few goals) so the embedding stays focused rather
    than diluting into a blob."""
    if request.retrieval_query:
        return request.retrieval_query.strip()

    parts: list[str] = []
    trigger = (request.player_input or request.event or "").strip()
    if trigger:
        parts.append(trigger)

    # Recent conversation (oldest→newest of the last few turns) — resolves referents.
    for m in (recent_messages or [])[-max_recent_turns * 2:]:
        content = (m.get("content") or "").strip()
        if content:
            parts.append(content[:200])

    # The live arena (what's true right now).
    sit = request.situation
    if sit is not None:
        for bit in (sit.location, sit.game_time, ", ".join(sit.present), *sit.recent_events):
            if bit:
                parts.append(bit)

    # The agent's standing concerns — relevance is relative to what THEY want. Deliberation (#20)
    # can evolve goals away from the profile; the override takes precedence when given.
    effective_goals = goals if goals is not None else character.goals
    if include_goals and effective_goals:
        parts.extend(effective_goals[:3])

    # The agent's current stance toward the player — relevance is relative to their caring, so
    # a wary character recalls a different past than a fond one (issue #6 RR-deepening).
    if relationship_hint:
        parts.append(relationship_hint)

    return "  ".join(parts).strip() or trigger


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
    if not lines:  # clock-only situation carries decay metadata but nothing to display
        return ""
    return (
        "# Current situation\n"
        "What is true in the scene right now. React to it naturally as your character; "
        "do not narrate it back verbatim.\n" + "\n".join(lines)
    )


def render_memories(memories: list[str] | None) -> str:
    """Render retrieved long-term memories into a prompt section, or "" if none."""
    if not memories:
        return ""
    recalled = "\n".join(f"- {m}" for m in memories)
    return (
        "# Memories from past conversations with this user\n"
        "Draw on these naturally if relevant; do not recite them verbatim.\n" + recalled
    )


def render_beliefs(beliefs: list[str] | None) -> str:
    """Render consolidated BELIEFS (issue #9) into their own section — convictions are a different
    thing from a recalled exchange, so they get a distinct header (issue #14), or "" if none."""
    if not beliefs:
        return ""
    body = "\n".join(f"- {b}" for b in beliefs)
    return (
        "# What you've come to believe about this person\n"
        "Convictions you've formed over time — let them colour how you read and treat them; "
        "don't recite them.\n" + body
    )


def render_recent_happenings(events: list[str] | None, own_acts: list[str] | None) -> str:
    """Working memory (#30): the few FRESH, high-salience things that just happened AROUND the
    character, and what they THEMSELVES just did/decided — surfaced top-of-mind for the current
    beat so they react in the moment and never have to be reminded of their own recent acts. "" when
    nothing fresh. Transient by construction (the caller only passes items within the recency
    window), so it fades back into ordinary retrieval as the scene moves on."""
    if not events and not own_acts:
        return ""
    lines: list[str] = []
    if events:
        lines.append("Just happened — right now, or moments ago:")
        lines += [f"- {e}" for e in events]
    if own_acts:
        lines.append("What you yourself just did or decided (you KNOW you did this — no one need remind you):")
        lines += [f"- {a}" for a in own_acts]
    return (
        "# What's happening right now\n"
        "Fresh in your mind this very moment — react to it as your character naturally would, "
        "in the moment. You are fully aware of it; don't narrate it back verbatim.\n" + "\n".join(lines)
    )


def render_goals(goals: list[str] | None) -> str:
    """Render goals the character has EVOLVED through deliberation (#20), so its shifted life
    direction overrides the static profile goals in-prompt. "" when goals haven't changed."""
    if not goals:
        return ""
    body = "\n".join(f"- {g}" for g in goals)
    return (
        "# What you want now\n"
        "Your aims have shifted from where they began — this is the direction you've come to want.\n"
        + body
    )


def render_turn_context(
    *, memories: list[str] | None = None, situation: Situation | None = None,
    commitments: str = "", relationship: str = "", intent: str = "", beliefs: list[str] | None = None,
    goals: list[str] | None = None, recent_happenings: str = "",
) -> str:
    """The per-turn DYNAMIC half of a character's context: what's happening RIGHT NOW (fresh
    events + the character's own just-taken acts, #30), recalled memories, the character's formed
    beliefs, the evolving relationship/feelings, their current short-term intent, OPEN commitments
    (always surfaced), and the live Situation. The full loop injects this as a small context *item*
    each turn (keeping the big static prompt stable + cacheable); the modular pipeline folds it into
    the full prompt. Returns "" when there's nothing dynamic."""
    parts = [s for s in (recent_happenings, render_memories(memories), render_beliefs(beliefs),
                         render_goals(goals), relationship, intent, commitments,
                         render_situation(situation)) if s]
    return "\n\n".join(parts)


def build_instructions(
    character: Character,
    *,
    memories: list[str] | None = None,
    situation: Situation | None = None,
    commitments: str = "",
    relationship: str = "",
    intent: str = "",
    performance_provider: str | None = None,
) -> str:
    """Assemble a character's full system prompt from the sources. With no dynamic context
    (memories/commitments/relationship/intent/situation), this equals the legacy prompt, so
    existing behavior is unchanged."""
    parts: list[str] = [ENGINE_DIRECTION + "\n" + character.build_prompt()]

    if performance_provider:
        directive = performance_directive(performance_provider)
        if directive:
            parts.append(directive)

    turn_context = render_turn_context(
        memories=memories, situation=situation, commitments=commitments,
        relationship=relationship, intent=intent,
    )
    if turn_context:
        parts.append(turn_context)

    return "\n\n".join(parts)
