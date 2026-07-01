"""The game's own web server — serves the play view and the /api/game routes. Self-contained: it
IMPORTS the engine (via game.web → game.runtime); the engine NEVER imports it. This is what keeps the
game a clean consumer of the engine (docs/engine-game-contract.md), separate from the engine's own
server (orchestrator/main.py, which hosts the engine API + the director sandbox dev tool).

    python -m game.server            # http://127.0.0.1:8001/play   (GAME_PORT to override)
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")  # engine calls need ANTHROPIC_API_KEY

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from .web import router as game_router  # noqa: E402

WEB = Path(__file__).resolve().parent / "web"
_BUILD = str(int(time.time()))

app = FastAPI(title="The Ferry's Last Crossing")
app.include_router(game_router)


async def _play_page() -> HTMLResponse:
    html = (WEB / "play.html").read_text(encoding="utf-8")
    html = html.replace('src="/play.js"', f'src="/play.js?v={_BUILD}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})


app.add_api_route("/", _play_page, methods=["GET"])
app.add_api_route("/play", _play_page, methods=["GET"])

# Mounted last so /api/game + the page routes above take precedence over the static catch-all.
app.mount("/", StaticFiles(directory=str(WEB), html=True), name="game-web")


def main() -> None:
    import uvicorn
    uvicorn.run(app, host=os.environ.get("GAME_HOST", "127.0.0.1"),
                port=int(os.environ.get("GAME_PORT", "8001")))


if __name__ == "__main__":
    main()
