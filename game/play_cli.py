"""Terminal pressure-test for the game loop — sit down and play The Ferry's Last Crossing.

    python -m game.play_cli                         # Haiku (fast/cheap iteration)
    python -m game.play_cli --reply-model claude-sonnet-4-6   # Sonnet reply (realness)

Commands:
    <name>: <line>     talk to ONE character      e.g.  corvin: rough night to be stuck here
    say: <line>        say it to the ROOM         (the DM picks who speaks up; they answer in turn)
    do: <action>       attempt a free action      e.g.  do: ease the warrant off the door
    advance            move the story to the next beat
    look               reprint the current scene / who's here
    quit               end + finalize the run in the experiment log
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
from game.runtime import Game  # noqa: E402

C = {"dim": "\033[2m", "b": "\033[1m", "cy": "\033[36m", "mag": "\033[35m",
     "yl": "\033[33m", "gn": "\033[32m", "r": "\033[0m"}


def _fmt(rec: dict) -> str | None:
    k, t = rec["kind"], rec["text"]
    if k in ("player", "player_action"):
        return None  # the user typed it; don't echo
    if k in ("narration", "player_role"):
        return f"{C['dim']}{t}{C['r']}"
    if k == "event":
        return f"{C['yl']}⚡ {t}{C['r']}"
    if k == "reaction":
        return f"{C['mag']}» {rec.get('who','')} {t}{C['r']}"
    if k == "dialogue":
        return f"{C['cy']}{C['b']}{rec.get('who','')}:{C['r']} {t}"
    return t


class Printer:
    def __init__(self, game: Game):
        self.g, self.i = game, 0

    def flush(self):
        for rec in self.g.history[self.i:]:
            line = _fmt(rec)
            if line:
                print(line + "\n")
        self.i = len(self.g.history)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="game/scenarios/ferry_crossing.yaml")
    ap.add_argument("--condition", default="CTRL-TEXT")
    ap.add_argument("--reply-model", default="claude-haiku-4-5")
    ap.add_argument("--dm-model", default="claude-haiku-4-5")
    args = ap.parse_args()

    g = Game(args.scenario, condition=args.condition,
             reply_model=args.reply_model, dm_model=args.dm_model)
    p = Printer(g)
    print(f"{C['b']}{g.scenario['title']}{C['r']}  "
          f"{C['dim']}reply={args.reply_model} · dm={args.dm_model} · {args.condition}{C['r']}\n")
    run_id = await g.begin()
    p.flush()

    def prompt() -> str:
        try:
            return input(f"{C['gn']}» {C['r']}").strip()
        except (EOFError, KeyboardInterrupt):
            return "quit"

    while True:
        raw = prompt()
        if not raw:
            continue
        low = raw.lower()
        if low in ("quit", "exit", "q"):
            break
        try:
            if low == "look":
                print(f"{C['dim']}[{g._beat()['title']} · here: "
                      f"{', '.join(g._name(s) for s in g.present)}]{C['r']}\n{g._perception}\n")
            elif low == "advance":
                more = await g.advance()
                p.flush()
                if not more:
                    print(f"{C['dim']}(the story has reached dawn — 'quit' to finalize){C['r']}\n")
            elif low.startswith("say:"):
                await g.say_to_room(raw[4:].strip())
                p.flush()
            elif low.startswith("do:"):
                await g.act(raw[3:].strip())
                p.flush()
            elif ":" in raw:
                name, line = raw.split(":", 1)
                await g.talk(name.strip(), line.strip())
                p.flush()
            else:
                print(f"{C['dim']}(try  name: your line  |  say: ...  |  do: ...  |  "
                      f"advance | look | quit){C['r']}")
        except Exception as e:  # keep the session alive on a transient error
            print(f"{C['yl']}(error: {e}){C['r']}")

    outcome = ""
    try:
        outcome = input(f"{C['dim']}one-line outcome for the log (optional): {C['r']}").strip()
    except (EOFError, KeyboardInterrupt):
        pass
    await g.finish(outcome)
    print(f"{C['dim']}run logged: {run_id}{C['r']}")


if __name__ == "__main__":
    asyncio.run(main())
