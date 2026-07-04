"""Casting: situate a reusable character sheet INTO a scenario's world at engine construction.

A cast is reused across scenarios (the same Bri played a modern voice app before this riverlands
night), and a sheet's authored facts — role, named relationships — carry SYSTEM-PROMPT authority
that no per-turn context note can out-argue (playtest: Bri kept mentioning "Marco the bartender"
right through a world-frame injected into her situation). So the adaptation happens where the
authority is: the scenario's `world_frame` is baked into the sheet's backstory, and each cast
entry may carry an `adapt:` block (role override, relationship drops/adds) that swaps the
anachronisms for period equivalents — preserving the PSYCHOLOGY (a protective-older-coworker
figure) while replacing the furniture. Game-side by design: profiles on disk are never forked,
and the engine stays untouched (it just receives a Character)."""
from __future__ import annotations

from dataclasses import replace


def situate(character, scenario: dict, cast_entry: dict | None):
    adapt = (cast_entry or {}).get("adapt") or {}
    frame = (scenario.get("world_frame") or "").strip()
    changes = {}
    if adapt.get("role"):
        changes["role"] = str(adapt["role"]).strip()
    rel = dict(getattr(character, "relationships", None) or {})
    for k in adapt.get("drop_relationships") or []:
        rel.pop(k, None)
    for k, v in (adapt.get("add_relationships") or {}).items():
        rel[k] = v
    if rel != (getattr(character, "relationships", None) or {}):
        changes["relationships"] = rel
    swaps = adapt.get("knows_swap") or {}
    if swaps:
        knows = [swaps.get(k, k) for k in (getattr(character, "knows", None) or [])]
        if knows != (getattr(character, "knows", None) or []):
            changes["knows"] = knows
    backstory = getattr(character, "backstory", "") or ""
    for old, new in (adapt.get("backstory_swap") or {}).items():
        backstory = backstory.replace(old, new)  # literal swaps: this world's venues for the old one's
    if adapt.get("backstory_note"):
        backstory = f"{backstory}\n\n{str(adapt['backstory_note']).strip()}".strip()
    if frame:
        backstory = f"{backstory}\n\n(The world you live in: {frame})".strip()
    if backstory != (getattr(character, "backstory", "") or ""):
        changes["backstory"] = backstory
    return replace(character, **changes) if changes else character


# ---- voice casting (Track V) --------------------------------------------------------------------
# Hume Octave voices per cast member � library NAMES (platform.hume.ai). Per-slug env override
# HUME_VOICE_<SLUG_WITH_UNDERSCORES> wins, then this map, then the global BAKEOFF_HUME_VOICE.
HUME_VOICES = {
    "della-fenwick": "Medieval Peasant Woman",
    "brielle-bri-castellano": "Expressive Girl",
    "edwin-hale": "Yorkshire Chap",
    "corvin-ashgrave-inworld": "Brooding Intellectual Man",
}


def hume_voice(slug: str) -> str:
    import os
    return (os.environ.get("HUME_VOICE_" + (slug or "").upper().replace("-", "_"))
            or HUME_VOICES.get(slug)
            or os.environ.get("BAKEOFF_HUME_VOICE")
            or "Ava Song")
