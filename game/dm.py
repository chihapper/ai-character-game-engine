"""The hybrid DM: an LLM game-master that narrates scenes, builds each NPC's PERCEPTION of the room
(the rich-text CONTROL perception for #30), and adjudicates free-form player actions. It NEVER speaks
for the characters or reveals their inner state — that's the engine's domain (see
docs/engine-game-contract.md). Authored beats live in the scenario; the DM fills the connective tissue.

Strangers rule: everyone met tonight, so the DM refers to each person ONLY by appearance-handle, never
by a proper name — names surface only when a character speaks their own in dialogue."""
from __future__ import annotations

from orchestrator.adapters.llm_anthropic import AnthropicLLM

_SYSTEM = (
    "You are the game-master (DM) of an intimate, character-driven interactive story — a tense, "
    "rain-soaked bottle episode. You narrate the world and adjudicate what the PLAYER does. You do "
    "NOT speak for the characters (they have their own minds), you NEVER reveal a character's private "
    "feelings, and you NEVER mention rules or 'stats'. Prose is sensory, grounded, and economical. "
    "Never break the fiction."
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

    def _people(self, handles: list[str]) -> str:
        return (
            "STRANGERS: everyone here washed in tonight — NO ONE knows anyone's name yet. Refer to "
            "each person ONLY by appearance, using exactly these handles and nothing else — "
            + "; ".join(handles) + ". NEVER use a proper name; a name appears only after a character "
            "has spoken it themselves in dialogue."
        )

    async def narrate_beat(self, beat: dict, recap: str, present_handles: list[str]) -> str:
        """Player-facing scene narration on entering a beat — advance the story, don't re-establish."""
        so_far = (f"STORY SO FAR (continue FROM here — do not repeat any of it):\n{recap}"
                  if recap else "This is the very opening — the player has just stepped in from the storm.")
        task = ("Set the mood and what they notice as they step in." if not recap else
                "Narrate ONLY what is NEW now — time passing, the room shifting, whatever just happened. "
                "Do NOT re-describe the setting or repeat anything already established.")
        prompt = (
            f"SCENARIO: {self.s['title']} — {self.s.get('logline', '')}\n"
            f"TONE: {self.s.get('dm', {}).get('tone', '')}\n\n{self._people(present_handles)}\n\n"
            f"{so_far}\n\nBEAT: {beat['title']}\nWHAT FRAMES THIS MOMENT: {beat.get('setting', '')}\n\n"
            f"Write 2-4 sentences of scene narration to the PLAYER (second person, present tense). {task} "
            "Do NOT put words in anyone's mouth."
        )
        return await self._say(prompt)

    async def scene_perception(self, beat: dict, present_handles: list[str], recent: str = "") -> str:
        """The rich per-beat PERCEPTION of the room, shared by the NPCs — the #30 CONTROL arm's
        perception-as-text, matched in content to what an embodied build would perceive."""
        tmpl = self.s.get("dm", {}).get("perception_template", "")
        hist = f"WHAT HAS HAPPENED (so your CHANGES are accurate):\n{recent}\n\n" if recent else ""
        prompt = (
            f"SCENARIO: {self.s['title']}\nBEAT: {beat['title']}\n"
            f"WHAT FRAMES THIS MOMENT: {beat.get('setting', '')}\n\n{self._people(present_handles)}\n\n"
            f"{hist}PERCEPTION SPEC: {tmpl}\n\n"
            "Write the shared PERCEPTION of the room right now: 3-5 sentences of concrete, sensory "
            "detail — the space; each person present and their OBSERVABLE state (posture, expression, "
            "what they're doing — never inner feelings); and what has CHANGED since before. No names, "
            "no inner states, no stats, no addressing the player."
        )
        return await self._say(prompt)

    async def pick_responders(self, present_names: list[str], line: str, *,
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
            f"PRESENT: {', '.join(present_names)}\n\n{ctx}"
            f"The player now says: \"{line}\"\n\n"
            "Decide who actually speaks next, like a real scene — READ THE CONTEXT:\n"
            "- If it's aimed at ONE person (named, OR by context — answering them, continuing a thread "
            "with them, reacting to what they just said), ONLY that person responds.\n"
            "- If it's an open remark to the room, only those who'd genuinely react speak up — one, "
            "two, or a few. Don't make everyone pile on.\n"
            "- If no one would naturally respond, reply exactly: NONE.\n"
            f"Reply with ONLY names from the list, comma-separated, in speaking order (max {maxn}), or "
            "NONE. No other text."
        )
        raw = (await self._say(prompt)).strip()
        if raw.upper().startswith("NONE"):
            return []
        picks: list[str] = []
        for part in raw.replace("\n", ",").split(","):
            p = part.strip().strip(".").lower()
            if not p or p == "none":
                continue
            for name in present_names:
                nl = name.lower()
                if name not in picks and (p == nl or p in nl or nl.split()[0] == p):
                    picks.append(name)
                    break
            if len(picks) >= maxn:
                break
        return picks

    async def adjudicate(self, action: str, perception: str, present_handles: list[str]) -> str:
        """Narrate the world's response to a free-form, non-dialogue player action."""
        prompt = (
            f"SCENARIO: {self.s['title']}\n\n{self._people(present_handles)}\n\n"
            f"THE SCENE RIGHT NOW: {perception}\n\nThe player attempts: \"{action}\"\n\n"
            "Narrate what happens in 1-3 grounded sentences (second person). Stay physically "
            "plausible; do NOT resolve any character's feelings or decisions — only the world's "
            "response to the attempt. No proper names."
        )
        return await self._say(prompt)
