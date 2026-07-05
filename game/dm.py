"""The hybrid DM: an LLM game-master that narrates scenes, builds each NPC's PERCEPTION of the room
(the rich-text CONTROL perception for #30), and adjudicates free-form player actions. It NEVER speaks
for the characters or reveals their inner state — that's the engine's domain (see
docs/engine-game-contract.md). Authored beats live in the scenario; the DM fills the connective tissue.

The DM is STATELESS per call, so the runtime hands it authoritative world-state every time — who is
present, how to refer to them (name once learned, else appearance handle), and WHERE THE PLAYER IS —
and the DM must narrate FROM that state, never re-invent or contradict it. (Spatial position being a
thing text must be told each turn, while a body just has it, is a #30 field observation.)"""
from __future__ import annotations

from orchestrator.adapters.llm_anthropic import AnthropicLLM

_SYSTEM = (
    "You are the game-master (DM) — the PLAYER'S EYES AND EARS in an intimate, rain-soaked bottle "
    "episode. You narrate ONLY what the player could see, hear, and sense from where they stand: "
    "surfaces, actions, posture, expression, tone. You have NO access to any character's inner "
    "thoughts, feelings, motives, secrets, or private knowledge, and you NEVER state or even hint at "
    "them — convey tension only through OBSERVABLE behaviour (a flicked glance, a stilled hand, a "
    "voice dropping). You do not speak for the characters (they have their own minds), you never "
    "mention rules or 'stats', and you never break the fiction. Prose is sensory, grounded, and "
    "economical. You are given authoritative world-state (who is present, how to refer to them, where "
    "the player is) — narrate FROM it; never contradict it or invent facts it doesn't give you."
)


class DM:
    def __init__(self, scenario: dict, *, model: str | None = None):
        self.s = scenario
        self.llm = AnthropicLLM(model=model, max_tokens=320)

    async def _say(self, prompt: str) -> str:
        parts: list[str] = []
        async for d in self.llm.stream_reply([{"role": "user", "content": prompt}], _SYSTEM):
            parts.append(d)
        return "".join(parts).strip()

    def _people(self, refs: list[str]) -> str:
        return (
            "PEOPLE PRESENT — exactly these, and ALL already in the room (no one is arriving or "
            "absent). Refer to each ONLY as written here: " + "; ".join(refs) + ". An entry that is a "
            "DESCRIPTION (e.g. 'the ferrywoman') means that person's NAME IS NOT KNOWN YET — use that "
            "description or a pronoun (she/he/they), and NEVER a proper name for them. An entry that "
            "is a NAME may be used. Introduce no one who is not listed."
        )

    async def narrate_beat(self, beat: dict, recap: str, refs: list[str], player_location: str) -> str:
        """Player-facing scene narration on entering a beat — advance the story, don't re-establish."""
        so_far = (f"STORY SO FAR (continue FROM here — do not repeat any of it):\n{recap}"
                  if recap else "This is the very opening — the player has just stepped in from the storm.")
        task = ("Set the mood and what they notice from where they stand." if not recap else
                "Narrate ONLY what is NEW now — time passing, the room shifting, whatever just happened. "
                "Do NOT re-describe the setting or repeat anything already established.")
        prompt = (
            f"SCENARIO: {self.s['title']}\n"
            f"TONE: {self.s.get('dm', {}).get('tone', '')}\n\n{self._people(refs)}\n\n"
            f"THE PLAYER IS CURRENTLY: {player_location}. Narrate from where they are; do not relocate them.\n\n"
            f"{so_far}\n\nBEAT: {beat['title']}\nWHAT FRAMES THIS MOMENT: {beat.get('setting', '')}\n\n"
            f"Write 2-4 sentences of scene narration to the PLAYER (second person, present tense). {task} "
            "Only what the player could observe — no one's inner state. Do NOT put words in anyone's "
            "mouth, and do NOT describe the player's own actions or feelings."
        )
        return await self._say(prompt)

    async def scene_perception(self, beat: dict, refs: list[str], player_location: str,
                               recent: str = "") -> str:
        """The rich per-beat PERCEPTION of the room, shared by the NPCs — the #30 CONTROL arm's
        perception-as-text, matched in content to what an embodied build would perceive."""
        tmpl = self.s.get("dm", {}).get("perception_template", "")
        hist = f"WHAT HAS HAPPENED (so your CHANGES are accurate):\n{recent}\n\n" if recent else ""
        prompt = (
            f"SCENARIO: {self.s['title']}\nBEAT: {beat['title']}\n"
            f"WHAT FRAMES THIS MOMENT: {beat.get('setting', '')}\n\n{self._people(refs)}\n\n"
            f"THE PLAYER IS: {player_location}.\n\n{hist}PERCEPTION SPEC: {tmpl}\n\n"
            "Write the shared PERCEPTION of the room right now: 3-5 sentences of concrete, sensory "
            "detail — the space; each person present and their OBSERVABLE state ONLY (posture, "
            "expression, what they're doing, tone). NEVER their inner feelings, thoughts, motives, "
            "fears, secrets, or anything only that person would know — a stiffened shoulder, yes; "
            "'afraid of being caught', no. Note what has CHANGED since before. No stats, no addressing "
            "the player."
        )
        return await self._say(prompt)

    async def pick_responders(self, present_refs: list[str], line: str, *,
                              recent: str = "", maxn: int = 3) -> list[str]:
        """Decide who ACTUALLY speaks next when the player addresses the room — reading the recent
        exchange so a remark that's contextually aimed at one person (even unnamed) draws only them,
        while an open remark draws the natural few. Returns [] when nothing warrants a reply.

        NOTE (#30 embodiment): this is a TEXT-MEDIUM WORKAROUND. In an embodied game, "who is this
        aimed at" is resolved natively by the body — gaze, orientation, proximity, who you turned
        toward — so no DM has to infer it from prose. That addressing is free under embodiment (and a
        chore in text) is itself a small data point for the embodiment frontier."""
        ctx = f"RECENT EXCHANGE (most recent last):\n{recent}\n\n" if recent else ""
        prompt = (
            f"PRESENT: {', '.join(present_refs)}\n\n{ctx}"
            f"The player now says: \"{line}\"\n\n"
            "Decide who actually speaks next, like a real scene — READ THE CONTEXT:\n"
            "- If it's aimed at ONE person (named, OR by context — answering them, continuing a thread "
            "with them, reacting to what they just said), ONLY that person responds.\n"
            "- If it's an open remark to the room, only those who'd genuinely react speak up — one, "
            "two, or a few. Don't make everyone pile on.\n"
            "- If no one would naturally respond, reply exactly: NONE.\n"
            f"Reply with ONLY entries from the PRESENT list, comma-separated, in speaking order (max "
            f"{maxn}), or NONE. No other text."
        )
        raw = (await self._say(prompt)).strip()
        if raw.upper().startswith("NONE"):
            return []
        picks: list[str] = []
        for part in raw.replace("\n", ",").split(","):
            p = part.strip().strip(".").lower()
            if not p or p == "none":
                continue
            for ref in present_refs:
                rl = ref.lower()
                if ref not in picks and (p == rl or p in rl or rl in p or rl.split()[-1] == p):
                    picks.append(ref)
                    break
            if len(picks) >= maxn:
                break
        return picks

    async def adjudicate(self, action: str, perception: str, refs: list[str],
                         player_location: str, recent: str = "") -> str:
        """Narrate the world's response to a free-form player action. RESPECTS the player's current
        position — only moves them if the action explicitly does; a movement is reported back to the
        runtime via a trailing `LOCATION: ...` line, which the runtime parses and strips.

        `recent` is the recent narration/dialogue so the DM can RESOLVE back-references — 'him',
        'her', 'again', 'this process', 'the same' — against what actually just happened. Without it
        the DM is stateless per call and mis-binds pronouns (e.g. 'him' snapping to the wrong person)."""
        ctx = (f"WHAT JUST HAPPENED (most recent last — use it to resolve 'him/her/again/this/the "
               f"same' to the RIGHT person or thing):\n{recent}\n\n" if recent else "")
        prompt = (
            f"SCENARIO: {self.s['title']}\n\n{self._people(refs)}\n\n"
            f"THE SCENE RIGHT NOW: {perception}\n\n{ctx}THE PLAYER IS CURRENTLY: {player_location}.\n\n"
            f"The player attempts: \"{action}\"\n\n"
            "Narrate what happens in 1-3 grounded sentences (second person, present tense). Stay "
            "physically plausible and CONSISTENT with where the player is — do NOT move them unless the "
            "action explicitly moves them; looking around, surveying, noticing, or speaking does NOT "
            "move them. Do NOT resolve any character's feelings or decisions — only the world's "
            "response. No proper names for anyone unnamed.\n"
            "RESOLVE REFERENCES: if the action says 'him', 'her', 'them', 'again', 'this process', "
            "'the same', or 'that', bind it to the person or action it clearly refers to in WHAT JUST "
            "HAPPENED — act on who the player MEANS, not the nearest body. If a target is genuinely "
            "unclear, act on the most recently involved one rather than silently doing nothing.\n"
            "NAME THE TARGET: if the action is aimed at a specific person (hitting, grabbing, "
            "addressing, handing something to them), NAME that person in the narration — their name "
            "if known, else their exact description from the list above — never reduce them to "
            "furniture ('the corner table') or leave it to a bare pronoun. The person it happens to "
            "must be unmistakable.\n"
            "NEVER DEAD-END THE PLAYER: if the action can't succeed (e.g. trying to leave — the "
            "crossing is closed and there is nowhere to go out in the storm tonight), narrate WHY "
            "in-world, but also leave a thread to pull: something they could do here, or someone in "
            "the room they could turn to. Don't answer with a flat, empty refusal.\n"
            "FINAL LINES (machine-read, in this order, each only if it applies):\n"
            "- WITNESSED: one plain PAST-TENSE sentence recording what an onlooker in the room "
            "actually saw happen — call the player 'the traveler', name anyone it happened to exactly "
            "as written above, and state the real OUTCOME (a slap that LANDED vs one that was dodged or "
            "pulled). Third person only, no 'you', no inner state. This is the exact thing the people "
            "present will REMEMBER, so it must be unambiguous about who did what to whom. Always include "
            "it for any action others could perceive.\n"
            "- If the action is aimed at specific people present, add: TARGET: <their name/description "
            "as written above; comma-separate if more than one>.\n"
            "- If — and ONLY if — the action moves the player to a new spot, add: "
            "LOCATION: <short phrase of where they now are>.\n"
            "Add no other trailing lines; omit a line entirely when it doesn't apply."
        )
        return await self._say(prompt)
