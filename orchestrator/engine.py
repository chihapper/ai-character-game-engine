"""The game-director engine core — runtime-agnostic (issues #2 / #7).

A GAME drives a character by calling `respond(RespondRequest)` and the world-state hooks
(`remember` / `commit` / `resolve_commitment`), advancing its OWN clock. The engine owns
everything an NPC needs to feel alive across that: relevance-realization recall with
game-time decay, always-injected commitments that convert to memory on close, and an evolving
relationship that conditions both tone and recall.

This is the seam the Inworld full loop wraps for voice (run_full_loop) — the same retrieve →
inject → generate → reflect cycle, minus the audio/Inworld plumbing. A headless game (no
voice) can drive it directly; see tools/game_demo.py. The only thing the host supplies is an
LLM with `stream_reply(messages, system)`.

The game's CLOCK is a single float in whatever unit the game chooses (days, hours, minutes —
just be consistent). The engine only ever takes differences, so any granularity works:
"due by midday" vs "due by end of day" are just different float values (e.g. 1.5 vs 2.0).
The one thing tied to the unit is the decay half-life (RR_DECAY_HALF_LIFE) — set it in the
same unit (a game running on hours tunes it in hours).
"""
from __future__ import annotations

from .character_store import Character
from .config import get_settings
from .context import (
    RespondRequest, build_arena_query, build_instructions, render_turn_context,
)
from .memory.commitments import CommitmentStore, render_commitments
from .memory.intent import IntentStore
from .memory.long_term import LongTermMemory
from .memory.relationship import RelationshipStore
from .memory.short_term import ShortTermMemory
from .salience import reflect_on_turn, score_salience


class Engine:
    def __init__(self, character: Character, llm=None, *, readonly: bool = False) -> None:
        s = get_settings()
        self.character = character
        self.llm = llm
        ns = character.memory_namespace
        self.long_term = LongTermMemory(ns, readonly=readonly)
        self.commitments = CommitmentStore(ns, readonly=readonly)
        self.relationship = RelationshipStore(ns, readonly=readonly)
        self.intent = IntentStore(ns, readonly=readonly)
        self.short_term = ShortTermMemory(max_turns=s.short_term_turns)

    # ---- the game's world-state seam (what the GAME pushes) ------------------------------
    async def remember(self, fact: str, **kw) -> None:
        """Push a durable world event into the character's memory (direct or indirect)."""
        await self.long_term.remember(fact, **kw)

    def commit(self, text: str, **kw):
        """Declare an obligation the character has taken on."""
        return self.commitments.add(text, **kw)

    async def resolve_commitment(self, commitment_id: str, status: str, *, t: float | None = None):
        """Close a commitment (fulfilled/broken); it converts into an ordinary memory."""
        c = self.commitments.resolve(commitment_id, status)
        if c:
            await self._convert(c, t)
        return c

    # ---- one turn, in two halves (so any driver plugs its generation in between) ---------
    async def prepare(self, request: RespondRequest) -> tuple[str, dict]:
        """First half: expire overdue commitments, build the relationship-conditioned arena
        query, retrieve (decay-aware), and render the per-turn dynamic context (memories +
        commitments + relationship + situation) to inject. Returns (injected_context, debug)."""
        s = get_settings()
        now_t = request.situation.clock if request.situation else None
        for c in self.commitments.sweep_expired(now_t):
            await self._convert(c, now_t)
        # The agent's stance toward the player: feelings (#6) AND current aim (#8) both condition
        # what's relevant — a wary, "find out who sent them" character recalls a different past.
        stance = "; ".join(h for h in (self.relationship.get().query_hint(),
                                       self.intent.get().query_hint()) if h)
        if s.arena_query:
            query = build_arena_query(
                request, self.character, self.short_term.messages(),
                max_recent_turns=s.arena_query_recent_turns, relationship_hint=stance,
            )
        else:
            query = request.query()
        scored = await self.long_term.retrieve_scored(query, now_t=now_t) if query else {"selected": [], "scored": []}
        injected = render_turn_context(
            memories=scored.get("selected", []), situation=request.situation,
            commitments=render_commitments(self.commitments.open_items()),
            relationship=self.relationship.get().render(), intent=self.intent.get().render(),
        )
        return injected, {"query": query, "memories": scored.get("selected", []),
                          "scored": scored.get("scored", []), "embedder": scored.get("embedder", ""),
                          "intent": self.intent.get().intent}

    async def reflect(self, user_text: str, reply: str, situation) -> None:
        """Second half (background-safe): salience + any detected commitment + the relationship
        shift, then persist the exchange. Does NOT touch short-term — the caller owns that, so
        it can be updated synchronously before the next turn's query reads it."""
        if not user_text or not reply or self.long_term.readonly:
            return
        s = get_settings()
        now_t = situation.clock if situation else None
        if s.commitment_detection or s.relationship_state or s.intent_state:
            importance, detected, rel, intent = await reflect_on_turn(
                self.character, user_text, reply,
                relationship=self.relationship.get(), intent=self.intent.get())
            if detected and not self.commitments.readonly:
                self.commitments.add(detected["text"], made_t=now_t,
                                     importance=detected["significance"], due=detected["due"])
            if rel and not self.relationship.readonly:
                self.relationship.update(**rel)
            if intent is not None and not self.intent.readonly:
                self.intent.update(intent)
        else:
            importance = await score_salience(self.character, user_text, reply)
        await self.long_term.add_exchange(user_text, reply, importance=importance, t=now_t)

    async def respond(self, request: RespondRequest, *, debug: bool = False):
        """Headless convenience: prepare -> generate (direct LLM) -> record short-term ->
        reflect. The voice runtime instead calls prepare()/reflect() around Inworld's own
        generation (audio in, audio out)."""
        if self.llm is None:
            raise RuntimeError("Engine.respond needs an llm; voice drivers use prepare()/reflect().")
        injected, dbg = await self.prepare(request)
        system = build_instructions(self.character)
        if injected:
            system += "\n\n" + injected
        messages = self.short_term.messages() + [{"role": "user", "content": request.input_text()}]
        reply = await self._generate(system, messages)
        if request.input_text() and reply:
            self.short_term.add_user(request.input_text())
            self.short_term.add_assistant(reply)
        await self.reflect(request.input_text(), reply, request.situation)
        if debug:
            return reply, {**dbg, "relationship": self.relationship.get().to_dict(),
                           "commitments": [{"text": c.text, "due": c.due} for c in self.commitments.open_items()]}
        return reply

    # ---- internals ----------------------------------------------------------------------
    async def _generate(self, system: str, messages: list[dict]) -> str:
        parts: list[str] = []
        async for delta in self.llm.stream_reply(messages, system):
            parts.append(delta)
        return "".join(parts).strip()

    async def _convert(self, commitment, now_t: float | None) -> None:
        await self.long_term.remember(
            commitment.memory_text(), importance=commitment.memory_importance(),
            t=now_t, kind="commitment",
        )
