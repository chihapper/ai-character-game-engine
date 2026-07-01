"""The Arena — the embodied demo's authoritative world model + perception (#30 treatment arm).

Ground truth for space: a grid under the hood (positions, distance), presented as NAMED regions,
never coordinates. Perception is DERIVED from here, so a character can't be re-invented into
contradiction (no "alley to Mother Sael's" while stuck in the inn). The engine (the mind) stays
untouched; this is all game-side. See docs/embodied-demo-architecture.md.
"""
