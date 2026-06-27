"""Headless game-loop demo (issue #7): a tiny scripted game drives the engine end-to-end.

"The Harbor Job" — a game advances its own clock and pushes Situations, world events
(remember, direct AND indirect), and a commitment lifecycle (commit -> fulfilled) at Corvin,
while the engine handles recall (decay-aware, relationship-conditioned), the always-injected
commitment, and the evolving relationship. Each beat prints what the engine recalled (★), the
relationship state, open commitments, and Corvin's reply — so you can watch it all move
together. Proves the engine/game seam; surfaces gaps. Bills the LLM. Run:

    python -m tools.game_demo
"""
import asyncio
import os
import pathlib
import sys

os.environ.setdefault("RELATIONSHIP_STATE", "true")
os.environ.setdefault("INTENT_STATE", "true")  # show the evolving short-term agenda (#8)
os.environ.setdefault("COMMITMENT_DETECTION", "false")  # this game declares commitments explicitly
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.context import RespondRequest, Situation  # noqa: E402
from orchestrator.engine import Engine  # noqa: E402

SLUG = "corvin-ashgrave-inworld"


def wipe():
    for p in pathlib.Path(".memory").glob(f"{SLUG}.*"):
        p.unlink()


def show(reply, dbg, name):
    stars = [s["text"] for s in dbg["scored"] if s.get("selected")]
    if stars:
        print("   recalled:")
        for t in stars:
            print("     ★ " + t[:78].replace("\n", " / "))
    if dbg["commitments"]:
        print("   open commitments: " + "; ".join(c["text"] for c in dbg["commitments"]))
    r = dbg["relationship"]
    print(f"   relationship: affection {r['affection']:.2f} · trust {r['trust']:.2f} · "
          f"respect {r['respect']:.2f}  ({r['mood']})")
    if dbg.get("intent"):
        print(f"   intent: {dbg['intent']}")
    print(f"\n   {name}: {reply}\n")


async def beat(eng, name, *, label, player, situation):
    rec = f"  recent: {', '.join(situation.recent_events)}" if situation.recent_events else ""
    print(f"\n{'=' * 80}\n▶ {label}\n   [{situation.game_time} · {situation.location}]{rec}")
    print(f'   player: "{player}"')
    reply, dbg = await eng.respond(RespondRequest(player_input=player, situation=situation), debug=True)
    show(reply, dbg, name)


async def main():
    wipe()
    char = load_character(SLUG)
    name = char.name.split()[0]
    eng = Engine(char, AnthropicLLM(model="claude-sonnet-4-6", max_tokens=180))

    await beat(eng, name, label="Day 1 — the player offers to work for Corvin",
        player="I hear you move things quietly around here. I want in — I can be useful.",
        situation=Situation(location="the fish-dock", game_time="midnight, day 1", clock=1, present=[name]))

    print("\n   ⚑ WORLD EVENT: the watch doubles its night patrols")
    await eng.remember("The harbor watch doubled its night patrols after an informant's tip.",
                       importance=0.6, when="day 1", t=1, kind="world_event")

    c = eng.commit("watch the east pier tomorrow night and warn Corvin if the watch approaches",
                   importance=0.6, made_t=1, due_t=2, due="tomorrow night")
    print(f"   ⚑ GAME committed: {c.text}")
    await beat(eng, name, label="Day 1 — the player takes the watch job",
        player="Put me to work. I'll watch the east pier tomorrow night and signal if the watch comes near.",
        situation=Situation(location="the fish-dock", game_time="midnight, day 1", clock=1,
                            recent_events=["the watch doubled patrols tonight"]))

    await beat(eng, name, label="Day 2 — the player reports back from the pier",
        player="Done. Watched all night. A man in a grey coat was watching your crew the whole time — never moved.",
        situation=Situation(location="the east pier", game_time="night, day 2", clock=2,
                            recent_events=["the drop happened tonight"]))
    await eng.resolve_commitment(c.id, "fulfilled", t=2)
    print("   ⚑ GAME resolved the commitment: FULFILLED")

    print("\n   ⚑ WORLD EVENT (indirect): Corvin's fence is arrested")
    await eng.remember("Corvin's fence, Hale, was taken by the watch at dawn — word is a grey-coated "
                       "informant gave him up.", importance=0.85, when="day 3", t=3, kind="world_event")

    await beat(eng, name, label="Day 3 — the player brings news of Hale",
        player="You hear about Hale? The watch took him this morning. Word is someone tipped them off.",
        situation=Situation(location="Corvin's cellar", game_time="dusk, day 3", clock=3,
                            recent_events=["Hale was arrested at dawn"]))

    await beat(eng, name, label="Day 8 — days later, the player drops by (decay + recall test)",
        player="Remember that night at the pier? Feels like a lifetime ago now.",
        situation=Situation(location="the back of the tavern", game_time="night, day 8", clock=8, present=[name]))


if __name__ == "__main__":
    asyncio.run(main())
