"""Autonomous agency / deliberation (issue #20): the GENERATOR half of a living NPC. Between
scenes — the player NOT present — the character decides, on its own, what (if anything) it does or
how it changes, grounded in everything that has accumulated (memory, beliefs, relationship, scars,
intent, goals, time). The ENGINE applies the inner half through the seams already built (the #19
self-change path, intent, goals) and hands the outward `world_action` back to the game to enact.

People don't transform on a whim: in the default GATED mode most deliberations return
`changed=false` (the character continues as they are) and a real change needs accumulated CAUSE.
FREE mode lowers that bar for emergence-friendly games. The grounding IS the guardrail — a decision
must be true to this character. One LLM call, only when the game asks. Returns None on error.
"""
from __future__ import annotations

import json
import logging
import re

from .character_store import Character
from .judgment import complete, judgment, parse_json, salvage_json

logger = logging.getLogger(__name__)


def _salvage_decision(text: str) -> dict | None:
    """Best-effort recovery when the JSON is truncated (e.g. a long reflection blew max_tokens and the
    object never closed) — delegates to the shared generic salvage (judgment.salvage_json)."""
    return salvage_json(text)


def _parse_decision(text: str) -> dict | None:
    text = text or ""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    d = None
    if m:
        try:
            d = json.loads(m.group())
        except (ValueError, TypeError):
            d = None
    if not isinstance(d, dict):
        d = _salvage_decision(text)  # truncated/malformed — recover complete fields rather than lose all
    if not isinstance(d, dict):
        return None
    goals = d.get("new_goals")
    return {
        "reflection": str(d.get("reflection") or "").strip(),
        "changed": bool(d.get("changed")),
        "internal": str(d.get("internal") or "").strip(),
        "new_intent": str(d.get("new_intent") or "").strip(),
        "new_goals": [str(g).strip() for g in goals if str(g).strip()] if isinstance(goals, list) else [],
        "world_action": str(d.get("world_action") or "").strip(),
    }


async def deliberate(
    character: Character, *, grounding: str, mode: str = "gated", model: str | None = None,
) -> dict | None:
    """Decide what this character does/becomes on its own. `grounding` is the assembled state the
    engine passes; `mode` is 'gated' (default) or 'free'. Returns a Decision dict or None."""
    bar = (
        "Most of the time return changed=false — people don't transform on a whim; a real change "
        "needs accumulated CAUSE (weariness, beliefs that have drifted, an unresolved wound, time)."
        if mode != "free" else
        "FREE mode: the character may change more readily and follow emergent impulses — but it must "
        "still be plausible for who they are."
    )
    system = (
        "You are the autonomous inner life of a fictional character BETWEEN scenes — the player is "
        "NOT present. From who they are and everything that has accumulated, decide what, if "
        f"anything, they choose to do or how they change ON THEIR OWN. {bar} Any change must be TRUE "
        "to this character and grounded in what's given — never arbitrary.\n"
        "GROUND YOURSELF IN THE RECORD: base anything you say about the player ONLY on what the "
        "record below shows they actually did. You may interpret real events naturally — a person "
        "misremembers and conflates, that's human — but do NOT invent contact, words, or actions "
        "from the player that never happened. Before you decide, REGISTER in your reflection every "
        "significant thing that has happened since you last took stock — name and weigh EACH, even "
        "those you decide change nothing, and ESPECIALLY when several have piled up at once (after a "
        "long stretch away, a whole season may need reckoning with in one sitting). Do NOT tunnel on "
        "one thread and let a real loss, betrayal, or opportunity pass unremarked — a beloved death or "
        "an open door must never go unmentioned just because a louder wound is also present.\n"
        "Return JSON ONLY:\n"
        "{\"reflection\": \"<their first-person reasoning — CONCISE. Speak to each significant "
        "development since you last took stock in a brief line (name it + your read), even any you "
        "judge change nothing; 1-2 sentences total if little has happened. Cover them so none is "
        "ignored, but do NOT write an essay.>\", "
        "\"changed\": <true|false>, "
        "\"internal\": \"<a shift in how they regard the PLAYER that they genuinely arrive at. It must "
        "be COHERENT and grounded — a real reckoning, never random noise that swings up one week and "
        "down the next. WEIGH ANY PLAYER ABSENCE through THIS character and what was actually "
        "established: passing contact with no real promise -> absence is just drifting to neutral over "
        "time, leave empty (decay handles it); but promises this character took to heart — or warmth "
        "they reasonably read AS a promise (people do this, especially when they fear being left) — "
        "mean the player's silence can genuinely sting, cool, or wound. Conversely, a player who keeps "
        "SHOWING UP — loyalty demonstrated over time, not merely promised — can let even a guarded "
        "character finally warm and trust them; that trust is earned, not given. People aren't always "
        "rational; judge it as THEY would, not as a fair arbiter would. Often empty.>\", "
        "\"new_intent\": \"<their updated near-term aim, or empty>\", "
        "\"new_goals\": [<their standing life-goals, RECONCILED with who they've ACTUALLY become — but a "
        "life-goal moves only on ACCUMULATED cause that genuinely reorients THIS character, never on "
        "one good night or a single scene (old habits die hard; a lifelong pattern rarely bends in a "
        "sitting). Whether a goal yields is CHARACTER-DEPENDENT: a goal core to who they are — an "
        "identity, a wound, a pleasure they own — can PERSIST even when the player or the situation "
        "pulls against it, and that unresolved tension is true to life, NOT to be tidied away (it can "
        "drive future conflict, even betrayal). When they HAVE genuinely transformed over accumulated "
        "time/cause, revise or drop the goals that no longer fit and add what the change implies. "
        "Return the FULL updated list (it REPLACES the old goals — include the ones that still hold). "
        "Leave empty unless the direction has really moved (most deliberations); don't churn for "
        "change's sake, and don't bend a goal just because the situation wants it to.>], "
        "\"world_action\": \"<an outward action for the GAME to enact, e.g. 'leaves the harbor for the "
        "cliff abbey' — or empty>\"}\n"
        "`internal` is a rare, decisive change of heart toward the player (the engine applies it — it "
        "can heal or deepen a scar); `world_action` is something the GAME makes happen in its world. "
        "When changed=false, leave the change fields empty."
    )
    prompt = (f"WHO YOU ARE + WHAT HAS ACCUMULATED:\n{grounding}\n\n"
              "What, if anything, do you do or become now? JSON only.")
    try:
        # [system] (list) opts the stable deliberation instructions into prompt caching; the grounding
        # lives in the user message and stays uncached (it's unique each deliberation).
        text = await complete([system], prompt, role="deliberation", model=model, max_tokens=1000)
        return _parse_decision(text)
    except Exception:
        logger.exception("Deliberation failed; no decision this cycle")
        return None


async def reconcile_goals(
    character: Character, current_goals: list[str], *, grounding: str, reflection: str = "",
    proposed: list[str] | None = None, model: str | None = None,
) -> list[str] | None:
    """A FOCUSED second pass: reconcile the character's STANDING life-goals with who they've become.
    Decoupled from deliberate() on purpose (#29) — folded into the big decision JSON, goal-revision
    competes with reflection/internal/intent and the model defaults it to empty even at full
    transformation. Given nothing else to produce, a single-purpose call actually examines each goal.
    Returns the reconciled list (may equal the input if nothing should move) or None on error."""
    if not current_goals:
        return None
    system = (
        "You reconcile a fictional character's STANDING LIFE-GOALS with who they have ACTUALLY become. "
        "You're given who they are, the state they've accumulated (feelings, beliefs, what's happened), "
        "their latest reckoning, and their current goals. Go through the goals ONE BY ONE and, for each, "
        "decide: KEEP it as-is; SOFTEN/reword it to fit who they now are; REPLACE it; or DROP it — and "
        "ADD any new goal the change now implies.\n"
        "RR-faithful, NOT deterministic: a life-goal moves only on ACCUMULATED, genuine transformation, "
        "never on a whim or to please the situation. A goal CORE to who they are — an identity, a wound, "
        "a pleasure they own — can PERSIST even when a relationship or situation pulls against it; that "
        "tension is true to life, not to be tidied away (it can drive real conflict, even betrayal — "
        "leave it). But a goal the transformation has genuinely HOLLOWED OUT — a transactional aim when "
        "they now want something real, a mask they've shed — should soften or fall away. Be DECISIVE "
        "about one class in particular: a goal aimed at getting something (a drink, attention, a thrill, "
        "validation, a good time) from ANYONE / whoever's around / strangers. Once the character has "
        "found something REAL with a SPECIFIC person and wants it, a 'get-it-from-anyone' goal is hollow "
        "and should reliably soften — usually toward what they now actually want (it needn't vanish: 'a "
        "good time with anyone' can become 'this, with them'). Do NOT over-extend this — a trait that is "
        "genuinely still THEM (a social nature, a love of fun, being charming) persists; only the "
        "getting-it-from-just-anyone framing is what the bond has hollowed out. Don't churn for change's "
        "sake: if nothing has truly shifted, return the goals UNCHANGED. Most of who they are persists; "
        "revise only what the change has actually reached.\n"
        "ANCHOR ON THE EXISTING WORDING: if a goal already fits who they are, return it VERBATIM — do "
        "NOT re-articulate, restyle, or 'improve' the phrasing of a goal that's already right. Change a "
        "goal's wording ONLY when its MEANING has genuinely gone stale or wrong. A goal that keeps "
        "getting reworded each time you reconcile is a FAILURE — once it fits, it should hold steady "
        "across deliberations until a real new shift earns a change.\n"
        "Return JSON ONLY: {\"goals\": [<the FULL reconciled standing-goals list, priority order>], "
        "\"note\": \"<=20 words: what moved and why, or 'no change'>\"}"
    )
    proposed_block = ""
    if proposed and list(proposed) != list(current_goals):
        proposed_block = ("Their OWN deliberation just proposed this goal change — it's the character's "
                          "own reasoning about who they're becoming, so weigh it SERIOUSLY and honor it "
                          "unless it truly doesn't fit, then make the final call:\n"
                          + "\n".join(f"- {g}" for g in proposed) + "\n\n")
    prompt = (f"WHO THEY ARE + WHAT HAS ACCUMULATED:\n{grounding}\n\n"
              + (f"Their latest reckoning: {reflection}\n\n" if reflection else "")
              + proposed_block
              + "CURRENT STANDING GOALS:\n" + "\n".join(f"- {g}" for g in current_goals)
              + "\n\nReconcile each goal with who they've become. JSON only.")
    try:
        d = parse_json(await complete([system], prompt, role="deliberation", model=model,
                                      max_tokens=500))
        goals = d.get("goals") if isinstance(d, dict) else None
        if isinstance(goals, list):
            cleaned = [str(g).strip() for g in goals if str(g).strip()]
            return cleaned or None
        return None
    except Exception:
        logger.exception("Goal reconciliation failed; goals left as-is")
        return None


# --- The AGNOSTIC action seam (embodied demo, #30) ------------------------------------------------

async def choose_action(character: Character, situation: str, options: list[str], *,
                        grounding: str = "", model: str | None = None) -> dict:
    """Pick the ONE action a character takes right now — CHOSEN ONLY FROM the concrete options the GAME
    supplies (the things the world currently affords). The engine never knows what an action MEANS; it
    only selects from the offered list, so a character can never do something the world doesn't afford
    (no "slip down the alley to Mother Sael's" when stuck in an inn). Game-agnostic: the vocabulary is
    the caller's; this is the single embodied-action seam.

    `grounding` is who they've BECOME — evolved goals, near-term aim, feelings/scars, beliefs — so the
    choice is made by the lived character, not the static sheet. Prefer `Engine.choose_action`, which
    assembles it; calling this bare is for stateless demos. Returns {"action": <exact option or None>,
    "reason": <short, in-character>, "expression": <how it reads on their face, free text>,
    "face": <neutral|happy|sad|angry|fear|surprise>}.

    The face is part of the manifestation, not decoration: WHICH expression surfaces is the
    character's psychology meeting the moment's relevance — an unsettling character may smile at
    the wrong thing; most people's faces stay neutral unless the moment genuinely reaches them.
    The game maps `face` to whatever its body layer can show (or ignores it)."""
    from .salience import _character_summary
    if not options:
        return {"action": None, "reason": ""}
    system = ("You decide what a fictional character DOES at this moment, choosing ONLY from the options "
              "given — those are the only things the world affords right now. Stay true to who they are "
              "AND to who they have become; pick nothing if they'd simply hold as they are. Reply with "
              "JSON ONLY.")
    opts = "\n".join(f"- {o}" for o in options)
    became = f"WHO THEY'VE BECOME (their lived state — weigh it as much as the sheet):\n{grounding}\n\n" \
        if grounding else ""
    prompt = (f"CHARACTER:\n{_character_summary(character)}\n\n{became}"
              f"WHAT THEY PERCEIVE RIGHT NOW:\n{situation}\n\n"
              f"They may do exactly ONE of these, or nothing:\n{opts}\n\n"
              "Choose the single action THIS character would take now — copy its text EXACTLY, or use "
              "null for nothing. Invent nothing outside the list. Also say what shows on their FACE as "
              "they do it: most faces stay neutral unless the moment genuinely reaches this character; "
              "what surfaces (and whether it fits the moment) is who they are — some people smile at "
              'the wrong things. JSON: {"action": <exact option text or null>, "reason": "<short, in '
              'their voice>", "expression": "<what their face does, one short phrase>", '
              '"face": "<neutral|happy|sad|angry|fear|surprise>"}')
    data = await judgment(system, prompt, role="salience", model=model, max_tokens=200,
                          what="choose_action")
    if not isinstance(data, dict):
        return {"action": None, "reason": "", "expression": "", "face": "neutral"}
    chosen = data.get("action")
    # Bind HARD to the offered set — the world's affordances are the guardrail, not the prompt.
    if chosen not in options:
        chosen = next((o for o in options if chosen and str(chosen).strip().lower() in o.lower()), None)
    face = str(data.get("face") or "neutral").strip().lower()
    if face not in ("neutral", "happy", "sad", "angry", "fear", "surprise"):
        face = "neutral"
    return {"action": chosen, "reason": str(data.get("reason") or "")[:200],
            "expression": str(data.get("expression") or "")[:120], "face": face}
