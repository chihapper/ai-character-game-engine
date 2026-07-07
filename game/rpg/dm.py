"""The DM orchestrator — a GAME-layer LLM narrator + referee (NOT an engine Character).

It is the player's eyes and ears: it narrates scenes, and it ADJUDICATES free-form player actions
("I search the rubble", "I pry the door", "I climb the ledge") by calling the rules core as TOOLS.
The rules core is the sole authority on outcomes — the DM only narrates what the dice return. It has
no mind, no namespace, no feelings, and it NEVER speaks an NPC's dialogue (those come from each
NPC's Engine.respond). Grounding comes from the scene + the campaign log.
"""
from __future__ import annotations

import anthropic

from orchestrator.config import get_settings

from .rules import RulesEngine
from .state import ABILITIES, Combatant

def _system(setting: str) -> str:
    """The DM system prompt, keyed off the SLICE's setting (data) so the same narrator serves a
    flooded vault, a volcanic cavern, or a sunlit ruin without any hard-coded biome."""
    # "Game Master" deliberately — the alternative title is a WotC trademark NOT covered by the
    # SRD's CC-BY-4.0 license (the SRD itself says Game Master/GM). Never use the other mark.
    return (
        f"You are the Game Master of {setting} — the player's eyes, ears, and referee. Narrate "
        "what happens when the player attempts something: 1-3 vivid, grounded sentences, second "
        "person, present tense. Convey only what the player could perceive.\n"
        "You have NO access to any character's inner thoughts, and you NEVER put words in an NPC's "
        "mouth or speak their dialogue — they speak for themselves. You never mention rules, dice, or DCs.\n"
        "When an attempt has a real chance of failure — searching, forcing, climbing, sneaking, "
        "sensing, disarming, persuading against resistance — CALL the ability_check tool: you choose "
        "the ability and a DC from 5 (trivial) to 20 (near-impossible). The check's result is "
        "AUTHORITATIVE: narrate the SUCCESS or FAILURE it returns, never a different outcome. For a "
        "trivial or purely descriptive action, just narrate — no check.\n"
        "Stay physically consistent: keep the player where they are unless the action clearly moves "
        "them, and never invent an exit from this place that isn't there.")


class DM:
    def __init__(self, rules: RulesEngine, *, model: str | None = None, setting: str | None = None) -> None:
        self.rules = rules
        self.model = model or "claude-haiku-4-5"
        self.system = _system(setting or "a grim, torch-lit dungeon crawl")
        # The DM is a GAME-layer narrator, not an engine Character — it owns its own Anthropic client
        # rather than reaching into the engine's LLM adapter internals (keeps the game/engine seam clean).
        self.client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)

    def _system_blocks(self) -> list[dict]:
        """The system prompt as a CACHED block: it is identical for every call this session, so
        cache_control lets the API reuse the processed prefix — cuts DM time-to-first-token on
        every narration/adjudication after the first (the engine's own adapter already does this
        for NPC minds; the DM's separate client needs it too)."""
        return [{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}]

    async def narrate_scene(self, scene: str) -> str:
        """Atmospheric narration of the current surroundings (no check) — used on arrival / look."""
        resp = await self.client.messages.create(
            model=self.model, max_tokens=220, system=self._system_blocks(),
            messages=[{"role": "user", "content": f"{scene}\n\nDescribe this moment to the player in "
                                                   f"2-3 sentences. No check — just set the scene."}])
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    async def narrate_gesture(self, npc_name: str, gesture: str, *, scene: str) -> str:
        """An NPC's visible stage business, offered to the narrator (owner design 2026-07-06):
        speak it aloud ONLY if a watchful storyteller would bother — a hand drifting to a knife
        matters; shifting weight doesn't. Returns '' to stay silent. NARRATIVE relevance only:
        the GM describes visible behavior and never interprets inner states (the system prompt
        already forbids reading minds — this must stay an ordinary narrator function, not a
        psychology readout)."""
        resp = await self.client.messages.create(
            model=self.model, max_tokens=80, system=self._system_blocks(),
            messages=[{"role": "user", "content":
                f"SCENE:\n{scene}\n\nWhile speaking, {npc_name} visibly does this: \"{gesture}\"\n\n"
                "If — and only if — that visible behavior is worth the player's attention (a threat, "
                "a tell, a reach for something, a meaningful retreat or approach), narrate it in ONE "
                "short sentence, third person, present tense, describing only what can be SEEN. "
                "If it is ordinary business (shifting weight, a shrug, glancing about), reply with "
                "exactly: SKIP"}])
        out = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not out or out.upper().startswith("SKIP"):
            return ""
        return out

    async def adjudicate(self, action_text: str, *, scene: str, player: Combatant, grant_item=None) -> str:
        """Resolve a free-form player action. The DM may call ability_check (rules core decides pass/
        fail) and, if provided, grant_item (loot becomes REAL), then narrates the authoritative
        outcome. `player` is the Combatant a check rolls against."""
        tools = [t for t in self.rules.tools() if t["name"] == "ability_check"]
        if grant_item is not None:
            tools.append({
                "name": "grant_item",
                "description": "Give the player a SMALL, fitting item they plausibly found or took from "
                               "this action (a coin-purse, a tool, a note, a trinket, a common weapon). "
                               "NEVER a key to a sealed door, nor anything that trivializes an objective. "
                               "Call only on a genuine find, then narrate it.",
                "input_schema": {"type": "object", "properties": {
                    "name": {"type": "string", "description": "e.g. 'a pouch of silver'"},
                    "kind": {"type": "string", "enum": ["misc", "weapon", "consumable", "note"]}},
                    "required": ["name"]}})
        messages: list[dict] = [{"role": "user", "content":
            f"SCENE:\n{scene}\n\nThe player attempts: \"{action_text}\"\n\nNarrate what happens."}]
        # Cache the stable prefix: tools + system are identical across calls, so mark the LAST
        # tool with cache_control (tools precede system in the prompt; one marker covers both
        # tool schemas and everything cached before it) plus the system block itself.
        if tools:
            tools = [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}]
        for _ in range(3):                       # bounded tool loop
            resp = await self.client.messages.create(
                model=self.model, max_tokens=380, system=self._system_blocks(), tools=tools, messages=messages)
            if resp.stop_reason != "tool_use":
                return "".join(b.text for b in resp.content if b.type == "text").strip() or "..."
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                inp = block.input or {}
                if block.name == "grant_item" and grant_item is not None:
                    got = grant_item(str(inp.get("name", "something")), str(inp.get("kind", "misc")))
                    # A falsy return = the game REFUSED the grant (objective-key guard). Tell the
                    # model plainly — never wrap a refusal in "Given to the player: ..." (that
                    # self-contradicting result once led the model to narrate a grant that never happened).
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": (f"Given to the player: {got}." if got else
                                                "REFUSED — that item would trivialize the objective. "
                                                "Nothing was given; narrate the attempt yielding no such find.")})
                else:
                    # The tool schema restricts `ability` to ABILITIES, but tool-use inputs aren't
                    # hard-validated by the API — a model that emits 'Perception'/'LUCK' would crash
                    # Stats.mod's getattr. Coerce any off-enum value to a safe default (WIS).
                    ability = str(inp.get("ability", "WIS")).upper()
                    if ability not in ABILITIES:
                        ability = "WIS"
                    # dc/advantage get the same defensive coercion as ability — tool-use inputs
                    # aren't hard-validated, and a model emitting "moderate" or 12.0 must not crash.
                    try:
                        dc = int(float(inp.get("dc", 12)))
                    except (TypeError, ValueError):
                        dc = 12
                    try:
                        adv = int(float(inp.get("advantage", 0) or 0))
                    except (TypeError, ValueError):
                        adv = 0
                    r = self.rules.ability_check(player, ability, dc, advantage=max(-1, min(1, adv)))
                    verdict = "SUCCESS" if r.success else "FAILURE"
                    crit = f" (natural {'20' if r.critical == 'hit' else '1'})" if r.critical else ""
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": f"{ability} check: {verdict}{crit} "
                                               f"(rolled {r.total} vs DC {r.dc})."})
            messages.append({"role": "user", "content": results})
        return "..."
