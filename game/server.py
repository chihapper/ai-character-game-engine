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

from .arena.web import router as embodied_router  # noqa: E402
from .bridge.mind_api import router as mind_router  # noqa: E402
from .web import router as game_router  # noqa: E402

WEB = Path(__file__).resolve().parent / "web"
_BUILD = str(int(time.time()))

app = FastAPI(title="The Ferry's Last Crossing")


@app.on_event("startup")
async def _warm_memory_embedder() -> None:
    """Pre-warm the embedder so the ~0.5s fastembed cold-load doesn't land on the player's
    first turn (same guard orchestrator/main.py has had since it bit there)."""
    import asyncio
    import logging
    from orchestrator.memory.long_term import warm_embedder
    try:
        name = await asyncio.to_thread(warm_embedder)
        logging.getLogger(__name__).info("Embedder pre-warmed: %s", name)
    except Exception as exc:  # never block startup on a warm failure
        logging.getLogger(__name__).warning("Embedder pre-warm skipped: %s", exc)
app.include_router(game_router)       # /play — the TEXT control
app.include_router(embodied_router)   # /embodied — the ARENA treatment
app.include_router(mind_router)        # /api/mind — the MIND SERVER for foreign worlds (Unity, #35)


async def _play_page() -> HTMLResponse:
    html = (WEB / "play.html").read_text(encoding="utf-8")
    html = html.replace('src="/play.js"', f'src="/play.js?v={_BUILD}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})


async def _embodied_page() -> HTMLResponse:
    html = (WEB / "embodied.html").read_text(encoding="utf-8")
    html = html.replace('src="/embodied.js"', f'src="/embodied.js?v={_BUILD}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})


app.add_api_route("/", _play_page, methods=["GET"])
app.add_api_route("/play", _play_page, methods=["GET"])
app.add_api_route("/embodied", _embodied_page, methods=["GET"])

# Mounted last so /api/game + the page routes above take precedence over the static catch-all.
app.mount("/", StaticFiles(directory=str(WEB), html=True), name="game-web")


def main() -> None:
    import uvicorn
    uvicorn.run(app, host=os.environ.get("GAME_HOST", "127.0.0.1"),
                port=int(os.environ.get("GAME_PORT", "8001")))


if __name__ == "__main__":
    main()
