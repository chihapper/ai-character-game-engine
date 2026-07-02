"""LAN launcher for the game server: binds 0.0.0.0 so a phone on the same Wi-Fi can play,
without flipping game.server's safe loopback DEFAULT. Honors a launcher-assigned PORT
(e.g. from a dev-server harness); otherwise the usual 8001.

    python -m game.server_lan     # http://<lan-ip>:8001/embodied
"""
import os

os.environ.setdefault("GAME_HOST", "0.0.0.0")
os.environ.setdefault("GAME_PORT", os.environ.get("PORT", "8001"))

from game.server import main  # noqa: E402  (env must be set before config resolution)

if __name__ == "__main__":
    main()
