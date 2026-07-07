# Godot game build — Step-0 inspection / gap report

> Status: inspection done 2026-07-06 (night). Verifies the assumptions in
> [`godot-game-build-plan.md`](godot-game-build-plan.md) against the actual code
> **before** building. Verdict: **the spec is highly coherent with the codebase — clear to
> start Phase A**, with three decisions for the owner (below) and one big reuse opportunity.

## Verdict: ✅ ready for Phase A (pending 3 owner decisions)

The engine seam the spec relies on exists in full, a reusable game layer already exists, and
the character-clone approach is feasible. Nothing in the spec is blocked.

## Spec assumption → reality

| Spec assumption | Status | Notes |
|---|---|---|
| Seam: `respond`, `remember`, `deliberate`, `commit`, `resolve_commitment` | ✅ all exist | `orchestrator/engine.py` (87, 154, 158, 166, 507) |
| Seam: `choose_action(percept, afforded_options)` | ✅ exists, ⚠ naming | Real signature is `choose_action(situation, options: list[str])` (engine.py:227). Build a `Situation` (the "percept") + pass a list of option strings (the "afforded_options"). Functionally identical. |
| `Situation(clock, location, present)` numeric clock | ✅ | `context.py`: `location`, `game_time` (display string), `present`, `recent_events`, `extra`, and numeric `clock`. Pass `clock`; `game_time` is display-only. |
| Applied-vs-returned semantics; reaction = recipe (no `engine.react`) | ✅ | Contract holds; `remember`→salience→`deliberate`→enact is composed game-side. |
| `register_game_extension` + `game_data` | ✅ exists | `orchestrator/character_extensions.py` — and its own docstring example is literally `register_game_extension("srd5", render_srd5)`. The SRD game-data hook is already anticipated. |
| Character clone → reskin → fresh `memory_namespace` | ✅ feasible | `load_character(slug)` + `Character.memory_namespace` (defaults to slug, overridable) + `game/casting.py: situate(character, scenario, cast_entry)`. Load, override identity + namespace, situate into the world. |
| All depth flags default ON | ⚠ decision | 6 of the 10 default **OFF** today (see below). |

## 🔑 Big reuse opportunity — a game layer already exists

`game/arena/` is a working game layer that already does the spec's perceive→choose→enact loop:
- `world.py`, `maps/` — a **world/map system**
- `perception.py`, `demo_perception.py` — **percept** building
- `actions.py`, `demo_action.py` — **afforded actions**
- `game.py` — a loop that already calls `self.engines[slug].choose_action(sit, [a.label for a in acts])` (game.py:251, 327)

And `game/` also has `dm.py` (a DM narrator for the text game), `runtime.py` (text-game scenario runner that already enables the depth flags per-Engine), `casting.py`, `policy.py`, `scenarios/`. **Per the spec's own "extend and reuse — do not duplicate" rule, the RPG game-core should build on `game/arena/` (map/perceive/choose/combat) + reuse `dm.py`/`runtime.py` patterns (narration/dialogue/`remember`/depth-flags), not start from zero.**

## Capability flags — current defaults (spec wants all ON)

`orchestrator/config.py`: **ON** = `salience_scoring`, `relationship_time_decay`, `recent_happenings`, `arena_query`. **OFF** = `relationship_state`, `intent_state`, `reflection_enabled`, `commitment_detection`, `contradiction_detection`, `reinforce_on_recall`. Note: `game/runtime.py:45` already flips most ON via a **per-Engine caps override** (`EngineCaps.from_settings(get_settings(), relationship_state=True, reflection_enabled=True, intent_state=True, …)`) — so the "full depth" pattern already exists without changing global defaults.

## Three decisions for the owner (morning)

1. **Depth flags: flip global `config.py` defaults ON, or keep the per-Engine caps override** (as `runtime.py` does)? The per-Engine override preserves the #30 control-arm ability to turn faculties off explicitly; a global default-ON is simpler but is an engine-core change. *Recommendation: per-Engine caps override in the game-core (keeps the engine neutral, matches the existing pattern, still gives every NPC full depth).*
2. **Reuse base: is the RPG a NEW subpackage (e.g. `game/rpg/`) that reuses `game/arena/` + `game/dm.py`, or a direct extension of `game/arena/`?** `arena` is closest to the RPG (map + perceive + `choose_action` + combatants); `runtime.py`/`dm.py` own narration + dialogue + `remember`. Likely a new `game/rpg/` package that composes both. *Confirm the intended relationship so we extend rather than fork.*
3. **`choose_action` mismatch is cosmetic** — confirm you're fine mapping the spec's `(percept, afforded_options)` onto the real `(situation, options)` (no engine change needed).

## Suggested first build move (Phase A, step 1–2)
Start `game/rpg/` with the Pydantic **state model** + the **rules-core interface** (d20 behind a clean seam) + the **`GameSession`** interface — all renderer-agnostic — while reading `game/arena/world.py` + `game/arena/game.py` to reuse the map/percept/choose_action machinery rather than rebuild it. Defer the DM orchestrator + tcod view to steps 5–6.
