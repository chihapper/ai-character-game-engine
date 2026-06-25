"""AI-assisted character drafting: one line of concept -> a full structured card.

This is the only place the engine uses an LLM to *author* a character (the runtime
prompt compiler in character_store is plain, deterministic code). It asks the
configured model to fill the same fields the builder form exposes, and returns them
for the user to review and edit. Nothing is saved here.

Game-agnostic on purpose: the draft prompt must not assume a genre or ruleset.
"""
from __future__ import annotations

import json
import logging

from .adapters.llm_anthropic import AnthropicLLM

logger = logging.getLogger(__name__)

_SYSTEM = """You are a master character designer for a voice-driven, game-agnostic AI \
character engine. Given a one-line concept, design a vivid, internally consistent \
character an actor could play and stay in character as.

Return ONLY a single JSON object (no prose, no markdown fences) with EXACTLY these keys:
- name: string — a fitting name
- concept: string — one polished sentence capturing them
- age: string — e.g. "mid-50s" (free text; may be empty)
- role: string — their station or occupation
- pronouns: string — e.g. "she/her"
- greeting: string — their spoken opening line to the player, in their own voice
- temperament: string — one or two sentences on their inner disposition
- speech_style: array of short strings — concrete delivery traits, e.g. "Terse. Short sentences."
- backstory: string — 2-4 sentences of history that explain who they are now
- knows: array of strings — what they can speak about with authority
- doesnt_know: array of strings — what is outside their world (prevents anachronism)
- goals: array of strings — what they want in a scene
- secrets: array of objects {text, reveal_when} — things they hide; reveal_when is the \
condition under which they'd let it slip (leave empty to mean "never")
- boundaries: array of strings — topics they refuse or shut down
- relationships: array of objects {who, how} — include at least {"who":"the player","how":"..."}
- disposition: string — their starting stance toward the player
- sample_lines: array of strings — 2-4 signature lines in their exact voice

Guidance:
- Be specific and grounded; avoid generic filler. Give them a real flaw and at least one secret.
- Do NOT assume any particular game, genre, or ruleset — keep the character portable.
- These lines are spoken aloud: keep greeting and sample_lines short and natural.
Output JSON only."""


def _coerce_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _parse_json(raw: str) -> dict:
    """Pull the JSON object out of the model's reply, tolerant of stray prose/fences."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("The model did not return a character (no JSON found).")
    return json.loads(raw[start : end + 1])


def _normalize(d: dict) -> dict:
    """Shape the model output into the same card the /full endpoint returns, so the
    builder form can populate it exactly like an edit."""
    rels: dict = {}
    raw_rels = d.get("relationships")
    if isinstance(raw_rels, dict):
        rels = {str(k).strip(): str(v).strip() for k, v in raw_rels.items() if str(k).strip() and str(v).strip()}
    elif isinstance(raw_rels, list):
        for r in raw_rels:
            if isinstance(r, dict):
                who = (r.get("who") or "").strip()
                how = (r.get("how") or r.get("description") or "").strip()
                if who and how:
                    rels[who] = how

    secrets: list[dict] = []
    for s in d.get("secrets") or []:
        if isinstance(s, dict):
            text = (s.get("text") or "").strip()
            if text:
                secrets.append({"text": text, "reveal_when": (s.get("reveal_when") or "").strip()})
        elif isinstance(s, str) and s.strip():
            secrets.append({"text": s.strip(), "reveal_when": ""})

    return {
        "name": str(d.get("name") or "").strip(),
        "concept": str(d.get("concept") or "").strip(),
        "age": str(d.get("age") or "").strip(),
        "role": str(d.get("role") or "").strip(),
        "pronouns": str(d.get("pronouns") or "").strip(),
        "greeting": str(d.get("greeting") or "").strip(),
        "temperament": str(d.get("temperament") or "").strip(),
        "speech_style": _coerce_list(d.get("speech_style")),
        "backstory": str(d.get("backstory") or "").strip(),
        "knows": _coerce_list(d.get("knows")),
        "doesnt_know": _coerce_list(d.get("doesnt_know")),
        "goals": _coerce_list(d.get("goals")),
        "secrets": secrets,
        "boundaries": _coerce_list(d.get("boundaries")),
        "relationships": rels,
        "disposition": str(d.get("disposition") or "").strip(),
        "sample_lines": _coerce_list(d.get("sample_lines")),
    }


async def draft_card_from_concept(concept: str, model: str | None = None) -> dict:
    """Draft a full character card from a one-line concept. `model` selects which LLM
    drafts it (defaults to the configured model). Raises on LLM/parse error."""
    llm = AnthropicLLM(model=model, max_tokens=2048)  # a card is bigger than a realtime reply
    user = f'Concept: "{concept}"\n\nDesign the character. Return only the JSON object.'
    parts: list[str] = []
    async for delta in llm.stream_reply([{"role": "user", "content": user}], system=_SYSTEM):
        parts.append(delta)
    return _normalize(_parse_json("".join(parts).strip()))
