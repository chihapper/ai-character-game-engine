"""Game extension seam — how a game adds more 'character' to a character.

The engine is game-agnostic: it compiles only the universal character fields into
the system prompt. But every game emphasizes different aspects, so each character
carries an open `game_data` bag the engine stores but never interprets.

This module is the one place that turns that bag into behavior. A game layer
registers a *renderer* for its namespace; the renderer takes `game_data[namespace]`
and returns an extra system-prompt section. The engine then appends those sections
when it compiles a character — without knowing anything about what the game means.

    # in a game layer, at startup:
    from orchestrator.character_extensions import register_game_extension
    def render_srd5(sheet: dict) -> str:
        return f"# Your nature\nLevel {sheet['level']} {sheet['class']}. ..."
    register_game_extension("srd5", render_srd5)

With no game registered, `game_data` stays inert (current engine default). Register
a renderer and that game's characters gain extra, game-shaped depth.
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

# namespace -> function(game_data[namespace]) -> prompt section text
Renderer = Callable[[dict], str]
_RENDERERS: dict[str, Renderer] = {}


def register_game_extension(namespace: str, renderer: Renderer) -> None:
    """Register a game's renderer for its `game_data` namespace. Idempotent;
    re-registering replaces the previous renderer."""
    _RENDERERS[namespace] = renderer


def clear_game_extensions() -> None:
    """Drop all registered renderers (mainly for tests)."""
    _RENDERERS.clear()


def render_game_data(game_data: dict) -> list[str]:
    """Render every namespace in `game_data` that has a registered renderer into a
    list of prompt sections. Unregistered namespaces are left untouched (stored,
    not spoken). A renderer that errors is skipped, never fatal."""
    sections: list[str] = []
    for namespace, blob in (game_data or {}).items():
        renderer = _RENDERERS.get(namespace)
        if not renderer or not blob:
            continue
        try:
            text = renderer(blob)
        except Exception:
            logger.exception("Game extension '%s' renderer failed", namespace)
            continue
        if text and text.strip():
            sections.append(text.strip())
    return sections
