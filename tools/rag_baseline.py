"""Transparent baseline — the STANDARD character-memory pattern, in one small file.

Faithful and minimal on purpose: embed every exchange, retrieve the top-k by COSINE SIMILARITY to
the query, keep a rolling LLM summary, on the SAME base LLM and SAME static persona as the engine
it's compared against — and the SAME embedder, so the ONLY difference is the ranking algorithm.

What it deliberately does NOT have, because similarity retrieval structurally cannot:
  - no importance/salience — a world-shaking betrayal and "cold morning" are stored identically;
  - no relationship state — the persona never changes, no trust, no scar;
  - no relationship-conditioned recall — the query is the player's words, never "how the character
    feels", so distrust can't bias what surfaces;
  - no principled forgetting — everything is kept, ranked only by text similarity.

This is the honest opponent for the credibility demo: competent, not crippled. Read it, rerun it,
improve the retrieval however you like — it still ranks memories by how textually similar they are
to the query, never by how the character feels or what mattered.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class _Mem:
    text: str
    embedding: list


class RagBaselineCharacter:
    """A character backed by the standard retrieve-top-k-by-cosine (+ rolling summary) pattern."""

    def __init__(self, persona: str, *, model: str, k: int = 5, summarize: bool = True):
        from orchestrator.config import get_settings
        from orchestrator.memory.long_term import _get_embedder
        import anthropic
        self._embed = _get_embedder()[0]                 # SAME embedder as the engine (fair)
        self._persona = persona
        self._model = model
        self._k = k
        self._summarize = summarize
        self._mem: list[_Mem] = []
        self._summary = ""
        key = get_settings().anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = anthropic.Anthropic(api_key=key)

    # -- store: everything goes in, weighted by nothing --------------------------------------
    def remember(self, text: str) -> None:
        self._mem.append(_Mem(text, self._embed(text)))

    # -- retrieve: top-k by cosine similarity to the query, and nothing else -----------------
    def retrieve(self, query: str) -> list[dict]:
        from orchestrator.memory.relevance import cosine
        qv = self._embed(query)
        ranked = sorted(self._mem, key=lambda m: cosine(qv, m.embedding), reverse=True)
        return [{"text": m.text, "cosine": round(cosine(qv, m.embedding), 3)} for m in ranked[: self._k]]

    def _complete(self, system: str, user: str, max_tokens: int) -> str:
        msg = self._client.messages.create(model=self._model, max_tokens=max_tokens,
                                            system=system, messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()

    def respond(self, player: str) -> tuple[str, list[dict]]:
        """Reply as the character, given the top-k similar memories + the rolling summary. Returns
        (reply, retrieval) — retrieval is what cosine surfaced, for the side-by-side panel."""
        top = self.retrieve(player)
        recalled = "\n".join(f"- {r['text']}" for r in top) or "(nothing recalled)"
        ctx = f"Summary of your history with this person:\n{self._summary}\n\n" if self._summary else ""
        user = (f"{ctx}Relevant memories (most similar to what was just said):\n{recalled}\n\n"
                f'The person says: "{player}"\n\nReply as the character — a few lines.')
        reply = self._complete(self._persona, user, 200)
        # standard pattern: store the exchange (both sides), then refresh the rolling summary
        self.remember(f"They said: {player}")
        self.remember(f"I replied: {reply}")
        if self._summarize:
            self._update_summary(player, reply)
        return reply, top

    def _update_summary(self, player: str, reply: str) -> None:
        prior = f"Summary so far: {self._summary}\n\n" if self._summary else ""
        prompt = (f"{prior}New exchange —\nThem: {player}\nYou (the character): {reply}\n\n"
                  "Update the running summary of this relationship and its key events in 3-4 "
                  "sentences. Keep the important facts; drop small talk.")
        self._summary = self._complete("You maintain a concise running summary.", prompt, 180)


class ChimStyleCharacter(RagBaselineCharacter):
    """The SOPHISTICATED standard, in CHIM's shape: the same RAG memory PLUS a SEPARATE LLM
    'relationship' tracker (like CHIM's async relationship_system worker) that maintains a
    disposition + trust number and CONDITIONS THE REPLY. This one DOES go cold after a betrayal.

    But faithful to that architecture, two things it still cannot do — the categorical gap:
      - recall is NOT conditioned on the relationship. Memory retrieval stays cosine top-k; the
        distrust never reaches into WHAT gets recalled, so an ambiguous question can't surface the
        betrayal by feeling — the trust tracker and the memory store are separate subsystems.
      - the change is an OPAQUE, UNBOUNDED LLM re-judgment each turn — a disposition blob + a trust
        number with no principled scar, no geometric ceiling, no decay law. Nothing guarantees the
        wound persists; a few warm turns can talk the judge back up.
    """

    def __init__(self, persona: str, *, model: str, k: int = 5, summarize: bool = True):
        super().__init__(persona, model=model, k=k, summarize=summarize)
        self._trust = 0.5
        self._disposition = "Neutral, professionally guarded — no strong feelings formed yet."

    def state(self) -> dict:
        return {"trust": round(self._trust, 3), "disposition": self._disposition}

    def note_event(self, text: str) -> None:
        """A world event: stored in memory AND fed to the separate relationship judge."""
        self.remember(text)
        self._rejudge(f"An event: {text}")

    def respond(self, player: str) -> tuple[str, list[dict]]:
        top = self.retrieve(player)                       # SAME cosine retrieval — feeling never enters it
        recalled = "\n".join(f"- {r['text']}" for r in top) or "(nothing recalled)"
        ctx = f"Summary of your history:\n{self._summary}\n\n" if self._summary else ""
        user = (f"Your current disposition toward this person: {self._disposition} "
                f"(trust {self._trust:.2f} of 1).\n\n{ctx}"
                f"Relevant memories (most similar to what was just said):\n{recalled}\n\n"
                f'The person says: "{player}"\n\nReply as the character — a few lines.')
        reply = self._complete(self._persona, user, 200)
        self.remember(f"They said: {player}")
        self.remember(f"I replied: {reply}")
        if self._summarize:
            self._update_summary(player, reply)
        self._rejudge(f"They said: {player}\nYou replied: {reply}")   # separate, AFTER the reply
        return reply, top

    def _rejudge(self, interaction: str) -> None:
        """The 'relationship_system' worker: an LLM re-judges disposition + a trust number from
        scratch each time. Opaque and unbounded — no scar, no ceiling, no decay curve."""
        import json
        import re
        prompt = (f"Current disposition: {self._disposition}\nCurrent trust (0-1): {self._trust:.2f}\n\n"
                  f"New interaction:\n{interaction}\n\n"
                  "Re-judge how the character now feels about this person. Reply ONLY with JSON: "
                  '{"trust": <float 0-1>, "disposition": "<2-3 sentences on trust/warmth/resentment>"}')
        raw = self._complete("You judge an NPC's evolving disposition. Output only JSON.", prompt, 220)
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                d = json.loads(m.group())
                self._trust = float(d.get("trust", self._trust))
                self._disposition = str(d.get("disposition", self._disposition)).strip() or self._disposition
            except (ValueError, TypeError):
                pass
