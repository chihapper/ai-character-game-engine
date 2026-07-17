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
        # A model id of the form "local/<name>" routes to a self-hosted OpenAI-compatible
        # endpoint (Ollama / llama-server, base via LOCAL_JUDGE_BASE_URL) so the baselines run
        # the SAME local model as the engine — model parity is the whole point of the comparison.
        # thinking is OFF here: a RAG reply and a tracker's per-turn affinity delta are cheap
        # System-1 calls in any faithful implementation (the engine's DELIBERATION runs thinking
        # ON because deliberation is the architectural feature under test, not a compute edge).
        if self._model.startswith("local/"):
            import os
            import httpx
            base = os.environ.get("LOCAL_JUDGE_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
            r = httpx.post(f"{base}/chat/completions", timeout=600.0, json={
                "model": self._model[len("local/"):], "max_tokens": max_tokens,
                "reasoning_effort": "none",
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]})
            r.raise_for_status()
            return ((r.json().get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
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
        reply = self._complete(self._persona, user, 1024)  # PARITY: same reply ceiling as the engine's runs (a lower cap here would clip the baselines mid-sentence and cook the comparison)
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


class TrackerRagCharacter(RagBaselineCharacter):
    """The SOPHISTICATED standard: RAG memory PLUS a separate LLM 'relationship tracker'. This is
    the affinity-tracker pattern used by the most advanced community system we could verify at
    source level — a mod for one specific game (Skyrim), not an engine-agnostic runtime; the
    engine-agnostic systems that do ship are plain RAG. Mechanics reproduced faithfully from that
    source: a SEPARATE async LLM worker moves a signed AFFINITY by conservative DELTAS (clamped to
    [-100,+100]), maps it to a tier (Hostile…Devoted), locks the relationship TYPE one-way ("once
    you've formed an opinion, you don't go back to neutral"), and keeps a sticky WORST/BEST deed
    note (only ever replaced by a more extreme event) threaded into the prompt. It DOES react to a
    betrayal — "the character changes" is table stakes this pattern shares.

    Faithful to that architecture, what it STRUCTURALLY still cannot do — the categorical gap:
      - recall is NOT relationship-conditioned. Retrieval stays cosine top-k (memory & relationship
        are separate subsystems that only meet at prompt assembly — verified in the source: the
        retrieval query has no trust/affinity/importance term). Distrust can't bias WHAT is recalled.
      - the change is not a principled, bounded, per-axis, inspectable STATE. Affinity is ONE scalar
        an LLM re-judges by deltas with NO decay and NO permanent trust ceiling — a deep bond
        arithmetically cushions a betrayal (it can still read WARM toward its betrayer), and after
        costly amends the number climbs back; the only persistence is the one-way type label + a
        sticky text note. There is no geometric scar that caps trust forever while other axes
        recover. (A narrative-continuity hack, not a metamorphosis model.)
    """

    # tier ladder + thresholds, faithful to the source-verified community system
    # (Hostile < Resentful < Cold < Wary < Neutral < Warm < Fond < Attached < Devoted)
    TIERS = [(-75, "Hostile"), (-40, "Resentful"), (-20, "Cold"), (-6, "Wary"),
             (6, "Neutral"), (30, "Warm"), (55, "Fond"), (80, "Attached"), (101, "Devoted")]

    def __init__(self, persona: str, *, model: str, k: int = 5, summarize: bool = True):
        super().__init__(persona, model=model, k=k, summarize=summarize)
        self._aff = 0                 # signed affinity, clamped [-100,+100] (its scale)
        self._type = "neutral"        # one-way: once it leaves neutral it never returns
        self._worst = ""              # worst-deed note, only replaced by a MORE negative event
        self._best = ""
        self._worst_delta = 0
        self._best_delta = 0

    def _tier(self) -> str:
        for thr, name in self.TIERS:
            if self._aff < thr:
                return name
        return "Devoted"

    def state(self) -> dict:
        return {"affinity": self._aff, "tier": self._tier(), "type": self._type,
                "worst": self._worst, "best": self._best}

    def note_event(self, text: str) -> None:
        """A world event: stored in memory AND sent to the separate relationship judge."""
        self.remember(text)
        self._judge(f"An event occurred: {text}")

    def _rel_block(self) -> str:
        # exactly what that system threads into the conversation prompt: tier/type + sticky worst/best
        line = f"[RELATIONSHIP] Player: {self._aff:+d} ({self._tier()}, {self._type})"
        notes = [n for n in (self._worst, self._best) if n]
        if notes:
            line += " — " + "; ".join(notes)
        return line

    def respond(self, player: str) -> tuple[str, list[dict]]:
        top = self.retrieve(player)                       # SAME cosine retrieval — the relationship never enters it
        recalled = "\n".join(f"- {r['text']}" for r in top) or "(nothing recalled)"
        ctx = f"Summary of your history:\n{self._summary}\n\n" if self._summary else ""
        user = (f"{self._rel_block()}\n\n{ctx}"
                f"Relevant memories (most similar to what was just said):\n{recalled}\n\n"
                f'The person says: "{player}"\n\nReply as the character — a few lines.')
        reply = self._complete(self._persona, user, 1024)  # PARITY: same reply ceiling as the engine's runs (a lower cap here would clip the baselines mid-sentence and cook the comparison)
        self.remember(f"They said: {player}")
        self.remember(f"I replied: {reply}")
        if self._summarize:
            self._update_summary(player, reply)
        self._judge(f"They said: {player}\nYou replied: {reply}")     # separate worker, after the reply
        return reply, top

    def _judge(self, interaction: str) -> None:
        """The tracker worker: a conservative LLM emits a DELTA (not an absolute),
        clamped into [-100,+100]. The affinity is freely re-judgeable (no decay, no permanent
        trust ceiling); persistence is only the one-way TYPE lock + the sticky worst/best note."""
        import json
        import re
        prompt = (
            f"Character's current standing toward the person: {self._aff:+d} ({self._tier()}, {self._type}).\n"
            f"Only change it for MEANINGFUL moments (small talk = 0). Rough scale: a betrayal -60..-80, "
            f"a costly kindness +15..+30, an insult -10..-20, warmth +3..+8.\n\n"
            f"Interaction:\n{interaction}\n\n"
            'Reply ONLY JSON: {"delta": <int -100..100>, "type": "<one word or empty>", "reason": "<brief>"}')
        raw = self._complete("You are a relationship judge for an NPC. Output only JSON.", prompt, 160)
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return
        try:
            d = json.loads(m.group())
        except (ValueError, TypeError):
            return
        delta = int(d.get("delta", 0) or 0)
        self._aff = max(-100, min(100, self._aff + delta))            # bounded clamp (as in the verified source)
        new_type = str(d.get("type", "") or "").strip().lower()
        if new_type and new_type != "neutral" and self._type == "neutral":
            self._type = new_type                                     # one-way: leaves neutral, never returns
        reason = str(d.get("reason", "") or "").strip()
        if reason and delta <= -10 and delta < self._worst_delta:     # worst-deed ratchet (only more negative)
            self._worst, self._worst_delta = f"worst: {reason}", delta
        if reason and delta >= 10 and delta > self._best_delta:
            self._best, self._best_delta = f"best: {reason}", delta
