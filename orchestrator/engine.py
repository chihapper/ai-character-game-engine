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
"""
from __future__ import annotations

from .character_store import Character
from .config import get_settings
from .context import (
    RespondRequest, build_arena_query, build_instructions,
)
from .memory.commitments import CommitmentStore, render_commitments
from .memory.long_term import LongTermMemory
from .memory.relationship import RelationshipStore
from .memory.short_term import ShortTermMemory
from .salience import reflect_on_turn, score_salience


class Engine:
    def __init__(self, character: Character, llm, *, readonly: bool = False) -> None:
        s = get_settings()
        self.character = character
        self.llm = llm
        ns = character.memory_namespace
        self.long_term = LongTermMemory(ns, readonly=readonly)
        self.commitments = CommitmentStore(ns, readonly=readonly)
        self.relationship = RelationshipStore(ns, readonly=readonly)
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

    # ---- one turn of the engine (what the GAME asks for) --------------------------------
    async def respond(self, request: RespondRequest, *, debug: bool = False):
        """Produce the character's response to a player line / event, given the live Situation.
        Owns the whole cycle: expire commitments, build the relationship-conditioned arena
        query, retrieve (decay-aware), assemble the prompt, generate, then reflect (salience +
        relationship) and persist — the reflection mirrors the background write in run_full_loop."""
        s = get_settings()
        now_t = request.situation.clock if request.situation else None

        # Overdue commitments expire -> become ordinary (decaying) memories.
        for c in self.commitments.sweep_expired(now_t):
            await self._convert(c, now_t)

        # Recall, conditioned by the live arena AND the character's stance toward the player.
        query = build_arena_query(
            request, self.character, self.short_term.messages(),
            max_recent_turns=s.arena_query_recent_turns,
            relationship_hint=self.relationship.get().query_hint(),
        ) if s.arena_query else request.query()
        scored = await self.long_term.retrieve_scored(query, now_t=now_t) if query else {"selected": [], "scored": []}
        memories = scored.get("selected", [])

        system = build_instructions(
            self.character, memories=memories, situation=request.situation,
            commitments=render_commitments(self.commitments.open_items()),
            relationship=self.relationship.get().render(),
        )
        messages = self.short_term.messages() + [{"role": "user", "content": request.input_text()}]
        reply = await self._generate(system, messages)

        # Reflect: salience + relationship shift (folded), then persist the exchange.
        importance, _commit, rel = await reflect_on_turn(
            self.character, request.input_text(), reply, relationship=self.relationship.get()
        )
        if rel and not self.relationship.readonly:
            self.relationship.update(**rel)
        if request.input_text() and reply:
            self.short_term.add_user(request.input_text())
            self.short_term.add_assistant(reply)
            await self.long_term.add_exchange(
                request.input_text(), reply,
                importance=importance if importance is not None else await score_salience(
                    self.character, request.input_text(), reply),
                t=now_t,
            )

        if debug:
            return reply, {
                "query": query, "scored": scored.get("scored", []),
                "relationship": self.relationship.get().to_dict(),
                "commitments": [{"text": c.text, "due": c.due} for c in self.commitments.open_items()],
            }
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
