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
    "You are the game-master (DM) of an intimate, character-driven interactive story — a tense, "
    "rain-soaked bottle episode. You narrate the world and adjudicate what the PLAYER does. You do "
    "NOT speak for the characters (they have their own minds), you NEVER reveal a character's private "
    "feelings, and you NEVER mention rules or 'stats'. Prose is sensory, grounded, and economical. "
    "You are given authoritative world-state (who is present, how to refer to them, and where the "
    "player is) — narrate FROM it; never contradict it or invent facts it doesn't give you. Never "
    "break the fiction."
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
            f"SCENARIO: {self.s['title']} — {self.s.get('logline', '')}\n"
            f"TONE: {self.s.get('dm', {}).get('tone', '')}\n\n{self._people(refs)}\n\n"
            f"THE PLAYER IS CURRENTLY: {player_location}. Narrate from where they are; do not relocate them.\n\n"
            f"{so_far}\n\nBEAT: {beat['title']}\nWHAT FRAMES THIS MOMENT: {beat.get('setting', '')}\n\n"
            f"Write 2-4 sentences of scene narration to the PLAYER (second person, present tense). {task} "
            "Do NOT put words in anyone's mouth, and do NOT describe the player's own actions or feelings."
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
            "detail — the space; each person present and their OBSERVABLE state (posture, expression, "
            "what they're doing — never inner feelings); and what has CHANGED since before. No inner "
            "states, no stats, no addressing the player."
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
                         player_location: str) -> str:
        """Narrate the world's response to a free-form player action. RESPECTS the player's current
        position — only moves them if the action explicitly does; a movement is reported back to the
        runtime via a trailing `LOCATION: ...` line, which the runtime parses and strips."""
        prompt = (
            f"SCENARIO: {self.s['title']}\n\n{self._people(refs)}\n\n"
            f"THE SCENE RIGHT NOW: {perception}\n\nTHE PLAYER IS CURRENTLY: {player_location}.\n\n"
            f"The player attempts: \"{action}\"\n\n"
            "Narrate what happens in 1-3 grounded sentences (second person, present tense). Stay "
            "physically plausible and CONSISTENT with where the player is — do NOT move them unless the "
            "action explicitly moves them; looking around, surveying, noticing, or speaking does NOT "
            "move them. Do NOT resolve any character's feelings or decisions — only the world's "
            "response. No proper names for anyone unnamed.\n"
            "If — and ONLY if — the action moves the player to a new spot, add a final line, exactly: "
            "LOCATION: <short phrase of where they now are>. Otherwise do not add that line."
        )
        return await self._say(prompt)
