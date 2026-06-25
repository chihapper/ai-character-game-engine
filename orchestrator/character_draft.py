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


# Inworld wants ONE concise line, <=250 chars, ending with its quality cue.
_VOICE_DESC_SYSTEM_INWORLD = """You are a voice-casting director writing a prompt for \
Inworld's TTS voice design, which generates a voice from a text description. Given a \
character, write ONE vivid voice description Inworld can use to design a fitting voice.

Hard rules:
- English. Keep the whole description UNDER 240 characters (aim ~150-200). Be concise.
- Cover, in this spirit: age range, gender, accent (name a region only if it truly \
fits), pitch, pace, tone, and ONE texture word (raspy, breathy, smooth, warm, \
gravelly, bright...). Put the texture word in the MIDDLE, never at the very end.
- Be concrete ("early 20s", "low and unhurried"), never vague ("a nice voice").
- Infer gender from the pronouns. Match the character's temperament and speech style.
- End with exactly: Perfect broadcast quality audio.
Return ONLY the description text — no quotes, no labels, no preamble."""

# ElevenLabs wants a richer, structured description (no char cap). Follows the
# format from ElevenLabs' Voice Design prompting guide.
_VOICE_DESC_SYSTEM_EL = """You are a voice-casting director writing a prompt for \
ElevenLabs Voice Design (text-to-voice). Given a character, write a vivid, granular \
voice description that yields a fitting voice. More descriptive prompts give better \
voices, so be specific.

Use this structure, each on its own line:
Line 1: "Native English. <gender>, <age range>. Studio quality."
Line 2: "Persona: <2-5 words>. Emotion: <2-3 adjectives>."
Line 3: One or two sentences on timbre, pitch, pace, and delivery, matched to the character.

Rules:
- Name a real regional accent ONLY if it truly fits (e.g. "thick Louisiana drawl"); \
never "foreign"/"exotic".
- Use vocal-quality words (deep, gravelly, smooth, breathy, bright, warm), NOT \
audio-effect words (reverb, echo, phone).
- Infer gender from the pronouns; match the character's temperament and speech style.
- Be concrete, never vague.
Return ONLY the description text — no preamble, no quotes, no markdown."""

_VOICE_DESC_FIELDS = ("name", "concept", "age", "role", "pronouns", "temperament")


async def draft_voice_description(
    card: dict, model: str | None = None, provider: str = "inworld"
) -> str:
    """Write a voice description from a character card, shaped for the target provider:
    a concise <=250-char line for Inworld, or a richer structured description for
    ElevenLabs. Raises ValueError if the card is empty."""
    bits = [f"{k}: {card[k].strip()}" for k in _VOICE_DESC_FIELDS if (card.get(k) or "").strip()]
    style = card.get("speech_style") or []
    if style:
        bits.append("speech style: " + "; ".join(str(s) for s in style))
    if not bits:
        raise ValueError("Fill in the character (name, concept, age...) first.")

    elevenlabs = provider == "elevenlabs"
    system = _VOICE_DESC_SYSTEM_EL if elevenlabs else _VOICE_DESC_SYSTEM_INWORLD
    user = "Character:\n" + "\n".join(bits) + "\n\nWrite the voice description."
    llm = AnthropicLLM(model=model, max_tokens=400)
    parts: list[str] = []
    async for delta in llm.stream_reply([{"role": "user", "content": user}], system=system):
        parts.append(delta)
    raw = "".join(parts).strip().strip('"')

    if elevenlabs:
        # Keep the multi-line structure; ElevenLabs has no character cap.
        desc = "\n".join(line.rstrip() for line in raw.splitlines() if line.strip())
        cap = 800
    else:
        desc = " ".join(raw.split())  # collapse to one line
        cap = 250
    if len(desc) > cap:  # trim back to a clean sentence end
        clipped = desc[:cap]
        cut = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))
        desc = clipped[: cut + 1] if cut > 30 else clipped.rsplit(" ", 1)[0]
    return desc
