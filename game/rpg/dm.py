"""The DM orchestrator — a GAME-layer LLM narrator + referee (NOT an engine Character).

It is the player's eyes and ears: it narrates scenes, and it ADJUDICATES free-form player actions
("I search the rubble", "I pry the door", "I climb the ledge") by calling the rules core as TOOLS.
The rules core is the sole authority on outcomes — the DM only narrates what the dice return. It has
no mind, no namespace, no feelings, and it NEVER speaks an NPC's dialogue (those come from each
NPC's Engine.respond). Grounding comes from the scene + the campaign log.
"""
from __future__ import annotations

from orchestrator.adapters.llm_anthropic import _shared_client
from orchestrator.config import get_settings

from .rules import RulesEngine
from .state import Combatant

_SYSTEM = (
    "You are the Dungeon Master of a grim, torch-lit high-fantasy dungeon crawl — the player's eyes, "
    "ears, and referee. Narrate what happens when the player attempts something: 1-3 vivid, grounded "
    "sentences, second person, present tense. Convey only what the player could perceive.\n"
    "You have NO access to any character's inner thoughts, and you NEVER put words in an NPC's mouth "
    "or speak their dialogue — they speak for themselves. You never mention rules, dice, or DCs.\n"
    "When an attempt has a real chance of failure — searching, forcing, climbing, sneaking, sensing, "
    "disarming, persuading against resistance — CALL the ability_check tool: you choose the ability "
    "and a DC from 5 (trivial) to 20 (near-impossible). The check's result is AUTHORITATIVE: narrate "
    "the SUCCESS or FAILURE it returns, never a different outcome. For a trivial or purely descriptive "
    "action, just narrate — no check.\n"
    "Stay physically consistent: keep the player where they are unless the action clearly moves them, "
    "and never invent an exit from the Vault that isn't there.")


class DM:
    def __init__(self, rules: RulesEngine, *, model: str | None = None) -> None:
        self.rules = rules
        self.model = model or "claude-haiku-4-5"
        self.client = _shared_client(get_settings().anthropic_api_key)   # shared connection pool

    async def narrate_scene(self, scene: str) -> str:
        """Atmospheric narration of the current surroundings (no check) — used on arrival / look."""
        resp = await self.client.messages.create(
            model=self.model, max_tokens=220, system=_SYSTEM,
            messages=[{"role": "user", "content": f"{scene}\n\nDescribe this moment to the player in "
                                                   f"2-3 sentences. No check — just set the scene."}])
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    async def adjudicate(self, action_text: str, *, scene: str, player: Combatant) -> str:
        """Resolve a free-form player action. The DM may call ability_check (rules core decides), then
        narrates the authoritative outcome. `player` is the Combatant the check rolls against."""
        tools = [t for t in self.rules.tools() if t["name"] == "ability_check"]
        messages: list[dict] = [{"role": "user", "content":
            f"SCENE:\n{scene}\n\nThe player attempts: \"{action_text}\"\n\nNarrate what happens."}]
        for _ in range(3):                       # bounded tool loop
            resp = await self.client.messages.create(
                model=self.model, max_tokens=380, system=_SYSTEM, tools=tools, messages=messages)
            if resp.stop_reason != "tool_use":
                return "".join(b.text for b in resp.content if b.type == "text").strip() or "..."
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                inp = block.input or {}
                r = self.rules.ability_check(player, str(inp.get("ability", "WIS")),
                                             int(inp.get("dc", 12)), advantage=int(inp.get("advantage", 0) or 0))
                verdict = "SUCCESS" if r.success else "FAILURE"
                crit = f" (natural {'20' if r.critical == 'hit' else '1'})" if r.critical else ""
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": f"{inp.get('ability','WIS')} check: {verdict}{crit} "
                                           f"(rolled {r.total} vs DC {r.dc})."})
            messages.append({"role": "user", "content": results})
        return "..."
