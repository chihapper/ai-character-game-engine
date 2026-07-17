"""Character-aware salience scoring — how memorable a moment is TO THIS character.

Relevance is relative to the agent (relevance realization): the same event is pivotal for
one character and forgettable for another. So when a memory is stored, we score its
`importance` from the character's own profile — a caring Bri holds onto the player's
brother's death; a cold, self-absorbed Corvin barely registers it. This is what lets
old-but-pivotal memories survive recency decay (GitHub issue #3).

A small LLM call rates the moment 0–1 against a compact character summary. It runs in the
background (off the critical path; see pipeline / main), so its latency never reaches the
user. Falls back to a neutral score on any error, so memory writes never fail because of it.
"""
from __future__ import annotations

import logging
import re

from .character_store import Character
from .config import get_settings
from .judgment import complete, judgment

logger = logging.getLogger(__name__)

NEUTRAL = 0.5  # fallback when scoring is off or fails

_SYSTEM = (
    "You output a single number, 0.00–1.00: how reliably a specific fictional character "
    "would RECALL this moment later. This is about retrievable memory, not drama.\n"
    "Two things make a moment recallable — take the HIGHER:\n"
    "1) EMOTIONAL/PERSONAL weight — it touches their goals, values, relationships, or "
    "fears. A warm character: more; a cold or guarded one: less.\n"
    "2) ROLE RELEVANCE — assume the character is COMPETENT at their job and expertise "
    "unless the profile clearly says otherwise. A competent professional reliably recalls "
    "facts in their domain EVEN WHEN ROUTINE — routine-ness does NOT make something "
    "forgettable for them. A bartender recalls a patron's drink order; a guard a face; a "
    "merchant a deal; a detective a detail.\n"
    "Calibration: pure filler / greetings → 0.0–0.1. Pleasant but inconsequential chatter "
    "→ 0.1–0.25. A fact a competent character would track in their role (a customer's "
    "order, a client's request, a detail in their expertise) → 0.6–0.8. A personally "
    "pivotal moment → 0.8–1.0. Do NOT rate a role-relevant fact low just because it is "
    "ordinary. Reply with ONLY the number."
)


def _character_summary(character: Character) -> str:
    """A compact 'who they are, their role, and what they care about' for the rater — must
    include role + expertise so it can judge role/competence salience (not the full prompt)."""
    bits: list[str] = [f"Name: {character.name}"]
    if character.concept:
        bits.append(character.concept)
    if character.role:
        bits.append(f"Role / job: {character.role}")
    if character.temperament:
        bits.append(f"Temperament: {character.temperament}")
    if character.knows:
        bits.append("Competent in / knows: " + "; ".join(character.knows))
    if character.goals:
        bits.append("Cares about / wants: " + "; ".join(character.goals))
    if character.disposition:
        bits.append(f"Current stance toward the player: {character.disposition}")
    if character.relationships:
        rel = "; ".join(f"{who}: {how}" for who, how in character.relationships.items() if how)
        if rel:
            bits.append("Relationships: " + rel)
    return "\n".join(bits)


def _parse_score(text: str) -> float:
    m = re.search(r"\d*\.?\d+", text or "")
    if not m:
        return NEUTRAL
    try:
        return max(0.0, min(1.0, float(m.group())))
    except ValueError:
        return NEUTRAL


async def score_salience_text(
    character: Character, moment: str, *, magnitude: float | None = None, model: str | None = None
) -> float:
    """Rate, 0–1, how memorable `moment` (any stored memory text) is to `character`.
    `magnitude` is an OPTIONAL coarse objective-scale hint the world/DM may supply (0 = trivial,
    1 = world-shaking) — the character WEIGHS it but realizes their OWN personal salience, which
    can diverge from objective scale (a distant war they shrug off; a small kindness that marks
    them for life). Returns NEUTRAL when scoring is disabled or on error."""
    settings = get_settings()
    if not settings.salience_scoring:
        return NEUTRAL
    mag_line = ""
    if magnitude is not None:
        mag_line = (
            f"\n\nThe world rates this event's OBJECTIVE scale at {magnitude:.2f} "
            f"(0 = trivial, 1 = world-shaking). Weigh it, but judge what it means to "
            f"{character.name} PERSONALLY — objective scale and personal salience can diverge."
        )
    prompt = (
        f"CHARACTER:\n{_character_summary(character)}\n\n"
        f"MOMENT:\n{moment}{mag_line}\n\n"
        f"How reliably would {character.name} RECALL this later? Weigh both personal/"
        f"emotional weight and role relevance — a competent professional recalls facts in "
        f"their domain even when routine. Reply with only a number from 0.00 to 1.00."
    )
    try:
        return _parse_score(await complete(_SYSTEM, prompt, role="salience", model=model,
                                           max_tokens=16))
    except Exception:
        logger.exception("Salience scoring failed; using neutral importance")
        return NEUTRAL


async def score_salience(
    character: Character, user_text: str, assistant_text: str, *, model: str | None = None
) -> float:
    """Rate, 0–1, how memorable this exchange is to `character`."""
    moment = f"Player: {user_text}\n{character.name}: {assistant_text}"
    return await score_salience_text(character, moment, model=model)


# --- Post-turn reflection: one folded call (salience + #4-B detection + #6 relationship) ----

_IMPORTANCE_BLOCK = (
    "importance — how reliably THIS character would RECALL this moment later (memory, not "
    "drama). Take the higher of emotional/personal weight or role relevance; a competent "
    "professional recalls facts in their domain even when routine. Filler/greeting 0.0-0.1; a "
    "role-relevant fact 0.6-0.8; a personally pivotal moment 0.8-1.0."
)

_COMMITMENT_BLOCK = (
    "commitment — set ONLY if the CHARACTER (not the player) STATED a concrete, durable "
    "promise, obligation, deal, or constraint they could be held to (\"I'll meet you at dawn\", "
    "\"I won't tell anyone\"). Write `text` as the obligation from the character's POV (\"meet "
    "the player at dawn\"); extract it even if they may be lying — they still SAID it. "
    "`significance` (0.00-1.00) is how BINDING this character truly considers it — driven by "
    "whether they MEAN it and intend to keep it, judged from their nature. Use these anchors:\n"
    "- an honest, loyal, or earnest character giving a real promise: 0.70-0.90 (their word is a bond);\n"
    "- a routine, low-stakes, or hedged promise: 0.40-0.60;\n"
    "- a deceptive, evasive, or self-serving character making a promise they likely WON'T keep, or "
    "one said only to placate or manipulate: 0.10-0.30 (cheap words).\n"
    "Be CONSERVATIVE about detection itself: hedges, pleasantries, hypotheticals, and anything the "
    "PLAYER said are NOT commitments → null."
)


def _relationship_block() -> str:
    return (
        "relationship — how THIS exchange moved the character's feelings toward the player, as "
        "signed deltas (range -0.30..0.30). MOST EXCHANGES ARE 0.00 — feelings move rarely. "
        "Magnitude is judged by THIS CHARACTER'S NATURE, not the surface niceness:\n"
        "- A guarded, cynical, jaded, or proud character: routine pleasantries, flattery, and "
        "nice talk roll off like WATER OFF A DUCK'S BACK — they've seen it all; move them 0.00. "
        "ONLY rare, proven, costly things shift them — genuine sacrifice, loyalty proven over "
        "real time, being truly SEEN, or a real betrayal — and even then slowly (±0.05-0.15). "
        "Very few people ever get close to such a character.\n"
        "- A warm, open, lonely, or impulsive character moves more readily to ordinary warmth.\n"
        "- ASYMMETRY — trust/affection are LOST fast but REGAINED slowly. A betrayal or cruelty can "
        "drop them sharply in ONE exchange; nothing raises them sharply. When standing is already "
        "LOW because the player did real damage, recovery is GRINDING: apologies, a name, a few good "
        "turns barely register — only sustained, costly proof over a long time earns it back, and a "
        "guarded or grudge-holding character forgives almost not at all. Even a WARM character does "
        "not bounce back quickly from a DEEP betrayal (the worse the wound, the slower). So when "
        "trust is low, keep positive deltas TINY (0.00–0.03) unless the proof is extraordinary.\n"
        "affection_delta (colder/fonder), trust_delta (warier/more trusting), respect_delta "
        "(contempt/admiration). `mood` = their acute feeling right now, 1-2 words.\n"
        "- SCAR (permanent) — set `scar` ONLY for a real betrayal or deep wound that would mark "
        "this character FOREVER, per axis (0.0 = no permanent mark; 0.3 = that axis can never "
        "rebuild past 0.7; 0.5 = never past 0.5). MOST exchanges have NO scar (all 0). WHICH axes "
        "and HOW deep is entirely about THIS character and THIS betrayal — do not apply a formula: "
        "a businessman double-crossed on a deal scars TRUST but maybe not RESPECT (he respects the "
        "game) unless it was a cheap lowball; a lover cheated on after years of vulnerability scars "
        "TRUST, RESPECT (\"how could I respect someone that low\"), AND AFFECTION. A forgiving or "
        "naive character scars shallower; a proud or guarded one deeper. Scar only what they'd "
        "truly carry for life.\n"
        "- SCAR_HEAL (the hardest thing) — set `scar_heal` per axis (0-1 = fraction of the REMAINING "
        "scar this act lifts) ONLY for EXTRAORDINARY, scar-lifting proof — monumental, costly, often "
        "sustained. This does NOT erase the memory of the betrayal (that's forever); it only lets "
        "them feel/trust again DESPITE remembering. Normally the axis must already have rebuilt as "
        "far as the scar allows (straining at its cap) before proof can lift the cap — BUT a single "
        "DRAMATIC act (saving their child's life, ruin taken on for them) can lift it even mid-"
        "recovery. CHARACTER-AWARE: a forgiving soul's scar can lift toward gone; a guarded grudge-"
        "holder's barely budges (small heal even for huge acts). MOST exchanges: 0 — words, time, "
        "apologies, and ordinary favors lift NOTHING.\n"
        "(The character's CURRENT standing and scars are given with the exchange below.)"
    )


def _standing_line(rel) -> str:
    """The LIVE standing — rides with the prompt so the big rubric above stays byte-identical
    across turns and characters (prompt-cacheable; the review found the floats embedded in the
    system string defeated that for every judgment call)."""
    return (f"Current standing, 0.5=baseline — affection {rel.affection:.2f}, trust {rel.trust:.2f}, "
            f"respect {rel.respect:.2f}; existing scars — affection {rel.scar_affection:.2f}, trust "
            f"{rel.scar_trust:.2f}, respect {rel.scar_respect:.2f}.")


def _intent_block() -> str:
    return (
        "intent — the character's IMMEDIATE short-term aim with the player right now, beyond "
        "their standing profile goals. A concrete agenda from their POV (\"find out who sent "
        "them\", \"keep them close tonight\", \"test if they can be trusted with the ledger\", "
        "\"get rid of them\"). It EVOLVES — it may continue, sharpen, or change with the scene "
        "and their feelings. CHARACTER-AWARE: a schemer probes and uses; a lonely flirt wants to "
        "be chosen; a guarded one wants distance until trust is earned. Empty string if they have "
        "no particular agenda. (Their current aim, if any, is given with the exchange below.)"
    )


def _parse_relationship(r) -> dict | None:
    """Build a relationship update {d_affection, d_trust, d_respect, mood, scar?} from the model's
    JSON `relationship` object — shared by the per-turn reflection and the world-event assessor."""
    if not isinstance(r, dict):
        return None
    clamp = lambda x: max(-0.3, min(0.3, float(x))) if isinstance(x, (int, float)) else 0.0
    rel = {
        "d_affection": clamp(r.get("affection_delta")), "d_trust": clamp(r.get("trust_delta")),
        "d_respect": clamp(r.get("respect_delta")), "mood": str(r.get("mood") or "").strip() or None,
    }
    c01 = lambda x: max(0.0, min(1.0, float(x))) if isinstance(x, (int, float)) else 0.0
    for key in ("scar", "scar_heal"):
        v = r.get(key)
        if isinstance(v, dict):
            axes = {"affection": c01(v.get("affection")), "trust": c01(v.get("trust")),
                    "respect": c01(v.get("respect"))}
            if any(axes.values()):
                rel[key] = axes
    return rel


def _parse_reflection(text: str, want_commit: bool, want_rel: bool, want_intent: bool):
    import json

    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return _parse_score(text), None, None, None
    try:
        d = json.loads(m.group())
    except (ValueError, TypeError):
        return _parse_score(text), None, None, None
    imp = d.get("importance")
    importance = max(0.0, min(1.0, float(imp))) if isinstance(imp, (int, float)) else NEUTRAL
    commitment = None
    if want_commit and isinstance(d.get("commitment"), dict):
        c = d["commitment"]
        if str(c.get("text") or "").strip():
            sig = c.get("significance")
            commitment = {
                "text": str(c["text"]).strip(),
                "significance": max(0.0, min(1.0, float(sig))) if isinstance(sig, (int, float)) else 0.5,
                "due": str(c.get("due") or "").strip(),
            }
    relationship = _parse_relationship(d.get("relationship")) if want_rel else None
    intent = None
    if want_intent and isinstance(d.get("intent"), str):
        # An explicit empty string IS a signal — the prompt says "empty if no agenda" — so it must
        # reach the store as a CLEAR, not be conflated with "field absent" (None = no update).
        intent = d["intent"].strip()
    return importance, commitment, relationship, intent


async def reflect_on_turn(
    character: Character, user_text: str, assistant_text: str, *,
    relationship=None, intent=None, model: str | None = None,
    recalled: list[str] | None = None, open_commitments: list[str] | None = None,
    want_commit: bool | None = None, want_rel: bool | None = None,
    want_intent: bool | None = None, want_salience: bool | None = None,
) -> tuple[float, dict | None, dict | None, str | None]:
    """ONE background LLM call: salience importance, plus — when enabled — any commitment the
    character made (#4-B), how the exchange moved their feelings (#6), and their updated
    short-term intent (#8). Folded into a single call (~0 player latency). Returns (importance,
    commitment|None, relationship_update|None, intent|None); fallbacks are all-None.

    `recalled` / `open_commitments`: the SAME RR-selected memories the actor's reply was
    conditioned on, plus the character's open promises — the judge is a relevance realizer
    too (the material history is what makes a betrayal a betrayal rather than mere news;
    without it, the actor's improvised TONE becomes the judge's only evidence of the inner
    state, and a fear-toned take on a real betrayal reads as danger instead of a wound —
    found 2026-07-17 on the fully-local lich rerun). Context rides in the per-turn prompt;
    the cacheable rubric stays byte-identical.

    The want_* flags come from the CALLER (Engine passes its per-engine caps); the process-global
    settings are only the default when a flag isn't passed. Deriving them here from the globals
    silently ignored every EngineCaps override — per-turn affect was dead on all caps-enabled
    surfaces (found by the pre-Unity review)."""
    settings = get_settings()
    if want_commit is None:
        want_commit = settings.commitment_detection
    if want_rel is None:
        want_rel = settings.relationship_state
    if want_intent is None:
        want_intent = settings.intent_state
    if want_salience is None:
        want_salience = settings.salience_scoring
    want_rel = want_rel and relationship is not None
    want_intent = want_intent and intent is not None
    if not want_salience and not want_commit and not want_rel and not want_intent:
        return NEUTRAL, None, None, None
    fields = ['"importance": <0.00-1.00>']
    blocks = [_IMPORTANCE_BLOCK]
    if want_commit:
        fields.append('"commitment": null | {"text": "...", "significance": <0.00-1.00>, "due": "..."}')
        blocks.append(_COMMITMENT_BLOCK)
    if want_rel:
        fields.append('"relationship": {"affection_delta": <-0.3..0.3>, "trust_delta": '
                      '<-0.3..0.3>, "respect_delta": <-0.3..0.3>, "mood": "<1-2 words>", '
                      '"scar": {"affection": <0-1>, "trust": <0-1>, "respect": <0-1>}, '
                      '"scar_heal": {"affection": <0-1>, "trust": <0-1>, "respect": <0-1>}}')
        blocks.append(_relationship_block())
    if want_intent:
        fields.append('"intent": "<short aim from their POV, or empty>"')
        blocks.append(_intent_block())
    system = ("You analyze one exchange with a fictional character and return JSON ONLY — no "
              "prose.\nReturn: {" + ", ".join(fields) + "}\n\n" + "\n\n".join(blocks))
    live = ""
    if want_rel:
        live += "\n" + _standing_line(relationship)
    if want_intent and intent and intent.intent:
        live += "\nTheir current aim: " + intent.intent
    if recalled:
        live += ("\nWhat this relationship is built on — the character's own memories, "
                 "recalled for this exchange:\n" + "\n".join(f"- {m}" for m in recalled[:8]))
    if open_commitments:
        live += ("\nTheir open promises to the player: " + "; ".join(open_commitments[:6]))
    prompt = (f"CHARACTER:\n{_character_summary(character)}{live}\n\n"
              f"EXCHANGE:\nPlayer: {user_text}\n{character.name}: {assistant_text}\n\n"
              "Return the JSON described.")
    try:
        # system rides as a LIST: the rubric is byte-identical across turns AND characters for a
        # given capability set, so it prompt-caches (the live floats travel with the prompt).
        text = await complete([system], prompt, role="salience", model=model, max_tokens=380)
        return _parse_reflection(text, want_commit, want_rel, want_intent)
    except Exception:
        logger.exception("Reflection (salience/detect/relationship/intent) failed; neutral fallback")
        return NEUTRAL, None, None, None


async def score_and_detect(
    character: Character, user_text: str, assistant_text: str, *, model: str | None = None
) -> tuple[float, dict | None]:
    """Back-compat: salience + commitment only (no relationship/intent)."""
    importance, commitment, _, _ = await reflect_on_turn(character, user_text, assistant_text, model=model)
    return importance, commitment


# --- Issue #12: world events shift disposition; per-character emotional persistence -----------

async def assess_event_impact(
    character: Character, event: str, *, attribution: str, relationship, model: str | None = None,
) -> dict | None:
    """How does an EVENT — a world event OR the character's own internal change — move THIS
    character's feelings toward the player? `attribution` describes how the event relates to the
    player ("the player caused this", "the player benefited from this", or "the character THEMSELVES
    underwent this — a change of heart; the player did nothing"). Same character-aware rubric as the
    per-turn update: deltas + a possible permanent scar, or a scar_heal (e.g. forgiveness the
    character reaches on their own — issue #19). Returns the relationship update or None."""
    settings = get_settings()
    system = (
        "You judge how an EVENT moves a fictional character's feelings TOWARD THE PLAYER. The event "
        "may be something in the world, or the character's OWN internal change (a change of heart, a "
        "transformation, a decision they reached on their own, the player having done nothing). "
        "Return JSON ONLY: {\"relationship\": null} if it doesn't bear on how they feel about the "
        "player, else {\"relationship\": {\"affection_delta\": <-0.3..0.3>, \"trust_delta\": "
        "<-0.3..0.3>, \"respect_delta\": <-0.3..0.3>, \"mood\": \"<1-2 words>\", \"scar\": "
        "{\"affection\": <0-1>, \"trust\": <0-1>, \"respect\": <0-1>}, \"scar_heal\": {\"affection\": "
        "<0-1>, \"trust\": <0-1>, \"respect\": <0-1>}}}.\n\n" + _relationship_block() +
        "\nINDIRECTNESS: weigh how directly the player is to blame/credit — a fair-minded character "
        "separates the player from their faction or allies; a vengeful or absolutist one does not. A "
        "severe harm can permanently SCAR like a personal betrayal.\n"
        "SELF-CHANGE: if the character THEMSELVES underwent a GENUINE, hard-won transformation (a "
        "change of life or faith, years of reflection, finally letting go of a grudge), that can "
        "warm them toward the player AND heal a scar (scar_heal) EVEN THOUGH THE PLAYER DID NOTHING — "
        "forgiveness they arrived at on their own. A passing mood or a whim heals nothing.")
    prompt = (f"CHARACTER:\n{_character_summary(character)}\n{_standing_line(relationship)}\n\n"
              f"EVENT ({attribution}):\n{event}\n\n"
              "How does it move how they feel about the player? JSON only.")
    d = await judgment([system], prompt, role="salience", model=model, max_tokens=240,
                       what="World-event impact assessment")
    return _parse_relationship(d.get("relationship")) if isinstance(d, dict) else None


async def assess_persistence(character: Character, *, model: str | None = None) -> float:
    """AI-derived 'emotional persistence' -> a decay half-life (game-clock units) for how long this
    character's player-specific feelings linger before drifting back to baseline with no contact.
    Warm/loyal/devoted/obsessive/grudge-holding -> long; mercurial/fickle/cold/transactional ->
    short. Returns 0.0 (= "unassessed") on error or an unparseable reply, so callers retry later
    instead of permanently pinning the global default as if it were this character's nature."""
    system = (
        "From a character's nature, judge how LONG their feelings toward someone linger before "
        "fading back to baseline when they have NO contact. Warm, loyal, devoted, obsessive, or "
        "grudge-holding natures persist a LONG time; mercurial, fickle, cold, transactional, or "
        "easily-distracted ones fade FAST. Return JSON ONLY: {\"persistence_days\": <number, ~30 "
        "for fast-fading to ~1000 for barely-fading>}.")
    prompt = f"CHARACTER:\n{_character_summary(character)}\n\nHow long do their feelings linger? JSON only."
    try:
        text = await complete(system, prompt, role="salience", model=model, max_tokens=40)
        m = re.search(r"\d+\.?\d*", text)
        return max(5.0, min(5000.0, float(m.group()))) if m else 0.0
    except Exception:
        logger.exception("Persistence assessment failed; left unassessed (will retry)")
        return 0.0
