<!-- AUTHORITATIVE BUILD PLAN for the game layer (owner-authored, 2026-07-06).
     This is the reference spec for the SRD-style AI-DM game (Python game-core → tcod dev
     view → Godot 4.x native desktop). A Step-0 inspection/gap report lives alongside at
     docs/godot-build-step0-inspection.md. Docs + code win where they disagree with this. -->

# Claude Code Build Prompt — Living-World AI Game Master (game layer)

## What you're building
The **game layer** — the *world* — that drives an existing character engine (the *mind*). A 2D, **SRD-style RPG** with an AI Game Master, procedurally generated dungeons, and NPCs whose personalities **evolve over a campaign**. The engine already delivers the evolving-NPC behavior; the game's job is to feed it a campaign's worth of consequential, attributable events and to render the result. The end target is a **downloadable, Steam-shippable native desktop game** (see Phase B) — not a web app.

**Read these first (they are the contract, in the repo):** `docs/engine-game-contract.md`, `docs/architecture-seams.md`, `docs/engine-overview.md`, `docs/relevance-scoring.md`. When they and this prompt disagree, the docs + code win. *(Note: the engine's chosen voice is now **Hume Octave**, served through the modular `TTSAdapter` seam; EVI was ruled out — its CLM strips authored delivery. If docs still name a previous provider, treat Hume Octave as current.)*

**The one rule (from the contract): the engine owns the MIND, the game owns the WORLD.** Everything below honors it.

**Architecture in one line:** a **renderer-agnostic Python game-core** (durable logic) with a **swappable renderer** — a disposable tcod/ASCII dev view first (Phase A), then a **Godot 4.x native desktop client** over local IPC (Phase B). The logic is built and proven once; only the thin rendering layer changes.

**Pacing — two modes (this is a SRD campaign, not a turn-based game):**
- **Exploration & social — free-flow (real-time):** the default. The player moves freely, talks to NPCs conversationally (each player line → `respond`), and explores. *Not* turn-based. Dialogue runs at conversational cadence; NPC on-map behavior (`choose_action`) fires on events/cadence, not every frame — so cost stays bounded even in free-flow.
- **Combat — turn-based:** begins when combat commences (encounter/aggression). Initiative, rounds, and actions resolved by the rules core; returns to free-flow when combat ends.
- The **clock** advances in the game's own opaque unit across both modes (narrative time in exploration, rounds in combat); the engine only differences it.

---

## Step 0 — inspect before you build
Before writing anything, inspect the repo and build *coherently* with what's there:
- The engine's public seam: `orchestrator/engine.py` (`Engine`), `orchestrator/context.py` (`RespondRequest`, `Situation`), `orchestrator/character_store.py` (`load_character`, `Character.build_prompt`), and the capability flags in `orchestrator/config.py`.
- **Any existing game layer** (e.g. `game/arena/world.py`, `game/perception.py`, `game/scenarios/`, `game/game_data`/`register_game_extension`). If a world/map or scenario system already exists, **extend and reuse it — do not duplicate it.**
- Confirm the seam methods and their applied-vs-returned semantics against the contract before relying on them.

If the existing game-layer state is ambiguous, **ask before building** rather than assuming.

---

## Hard guardrails (do NOT violate — these are why the engine works)
1. **Drive the engine only through its documented seam** — `respond`, `remember`, `deliberate`, `choose_action`, `commit`/`resolve_commitment`, with a `Situation` carrying a numeric `clock`. Never reach into the character's psychology any other way.
2. **Do NOT build memory, relationship, personality, salience, belief, or evolution logic.** All engine-owned. The game *feeds* the engine; it never models minds.
3. **Do NOT name any game concept in engine code** (quests, factions, classes, dice, maps, clocks). Game meaning lives game-side via `register_game_extension` + `game_data`.
4. **Keep the engine→game dependency at zero.** The game imports the engine's public surface; the engine never imports the game.
5. **No *psychological* readout — but mechanical stats are fine.** A character's feelings/relationship/mood are *felt through behavior, dialogue, and voice* — never surfaced as an affinity panel (the engine's sandbox bars are dev-only). **Mechanical stats are a different, game-owned layer:** show **follower/party HP** normally, and add a **player option to toggle enemy health visibility in combat**. The rule is about the *mind*, not the character sheet.
6. **Reactions are a recipe, not a method.** Compose game-side: `remember` → *your* salience threshold → `deliberate` → enact. No `engine.react()`.
7. **The game owns the clock and cadence.** Pass a numeric `Situation.clock` every turn; tune `recent_happenings_window` to that unit. Never make the engine run a loop.
8. **Voice is Hume Octave through the engine's modular `TTSAdapter` seam** — this IS the shipped RPG voice path. (EVI was ruled out 2026-07-06: its CLM strips authored delivery.) Consume the seam; don't build a parallel voice stack. Expressive/extreme delivery is a prompt/expressivity concern, not game logic.
9. **Memory is engine-owned** (per-character JSONL + fastembed/lexical + RR scoring — *not* ChromaDB). The game persists **world** state separately; never touch the mind store.
10. **Target native desktop, not the web.** The renderer is a downloadable app; never assume a browser/hosted deployment.

---

## The renderer-agnostic game-core (Python) — the durable heart (~80% of the work)

Build these as a package alongside the engine (e.g. `game/`), all renderer-agnostic (they emit/accept **data**, never pixels):

- **Game state model (Pydantic):** `PlayerCharacter` (stats, HP, skills, inventory), `WorldMap` (tiles, locations, seed), `NpcPlacement` (which engine-character is where + world role via `game_data`), `Follower` (a companion NPC carrying **mechanical** stats — HP, conditions — for the party UI; its *mind* still lives in its Engine), `Enemy`/`Encounter`, `QuestThread`, `CampaignLog`, `GameClock`, and a `Mode` flag (exploration | combat).
- **Rules core (deterministic) — lightweight now, extensible by design.** The MVP ships a **lightweight custom d20** system (resolution `roll + modifier vs DC`, turn-based combat with initiative/actions/damage/statuses, inventory). But put it **behind a clean interface** so it can grow toward a **rigorous, BG3-depth 5e-style ruleset** (full actions, conditions, spells, reactions) later **without disturbing** the map, DM, or engine-integration layers. Do not hard-wire lightweight assumptions elsewhere. Surface rules to the engine as **tools/function-calls** so a check fires *through* the voiced conversation; the rules core is the sole authority on outcomes.
- **Maps — two sources behind one model:** a `WorldMap` is produced either by a **procedural generator** (dungeons: BSP + cellular-automata, Phase A: one dungeon) *or* loaded from an **authored map** (towns, cities, story hubs designed by hand — e.g. in a tile editor like Tiled and loaded from data). Build a small **map-source abstraction** so both feed the same `WorldMap`, and the renderer + rest of the core don't care which. Phase A ships one procedural dungeon, but **leave the authored path open from the start**. Either source includes a tile grid, FOV + pathfinding.
- **Encounter/enemy generation:** placed by the generator (and optionally scripted into authored maps). Generic enemies are **deterministic stat-blocks** (rules-core combatants) — *no Engine mind*, for cost and scale (a goblin doesn't need a persistent psychology). A **named/recurring** adversary can be **promoted to an `Engine` instance** so it remembers and evolves like any character. *The exact generation method (authored encounter tables vs. procedural budgets vs. LLM-assisted population) is an open design detail to prototype in Phase A.*
- **DM orchestrator (the narrator — a game-layer LLM, NOT an engine Character):** a Baldur's-Gate-style narrator + referee, and almost your "internal thoughts" voice. It (a) narrates scenes and the outcomes of actions after the rules core resolves them, (b) adjudicates via the rules-core tools, (c) sequences a scene / decides who speaks, and (d) **feeds consequential events into the relevant NPC engines** via `remember(..., player_role=…, actor=…)` and calls `deliberate`/`choose_action` on cadence. It has **no engine mind, no namespace, no feelings** — it is the world's voice. Give it a **lightweight campaign-log retrieval** (simple keyword/recency lookup over `CampaignLog`) feeding its prompt, so it can call back ("the crossroads where you spared the bandit") — memory without being a character. **The DM never speaks NPC lines** — those come from each NPC's `Engine.respond`. Narration is text in the MVP; NPC dialogue is voiced by the engine's **Hume** runtime.
- **Engine integration layer:** construct **one `Engine` per named NPC** (`load_character(<slug>)`, LLM attached); build a `Situation(clock, location, present)` each turn/beat; call `respond` for dialogue, `choose_action(percept, afforded_options)` for on-map/combat behavior, `deliberate(situation)` between scenes; **enact the returned `world_action` / `choose_action` result** against the world. Enable the depth flags (below) and always pass the clock.
- **World persistence:** save/load `WorldMap` (+ seed), quests, `CampaignLog`, player sheet, clock, and mode to SQLite or JSON. (The engine auto-persists each mind at `.memory/<slug>.jsonl`.)
- **The `GameSession` interface (the linchpin — makes the renderer swappable):** one clean boundary both renderers consume — in-process for tcod, over local IPC for Godot. The core never knows which is attached.
  ```
  GameSession:
    get_state() -> StateSnapshot            # map, entities, player sheet, clock, mode (renderable data)
    submit_action(action) -> None           # player intent from the view (move, talk, attack, use…)
    events() -> async stream of:
        NarrationEvent(text)                # DM narration
        DialogueEvent(npc, text, audio?)    # an NPC line (+ Hume-voiced audio / ARKit-52 frames)
        MapUpdateEvent | CombatEvent | ModeChanged | StateChanged
  ```

### Capability flags — everything defaults ON
Set **every** engine capability to default ON in `config.py`/`Settings`: `relationship_state`, `relationship_time_decay`, `reflection_enabled`, `intent_state`, `salience_scoring`, `commitment_detection`, `contradiction_detection`, `recent_happenings`, `arena_query`, and `reinforce_on_recall`. Always pass `Situation.clock`. A fresh character then runs at full depth out of the box — nothing to toggle, nothing that reads as broken. (Still experiment-safe: the per-`Engine` caps let the #30 control arm switch specific faculties off explicitly when needed.)
*(Settled in implementation: the global `config.py`/`Settings` defaults were left unchanged; full depth is applied via a per-`Engine` caps override — see `full_depth_caps` in `game/rpg/minds.py`.)*

### The core loop (mode-aware)
**Exploration/social (free-flow):**
1. View sends an action (move / talk / interact).
2. Movement/interaction updates world state directly; a **talk** action → build `Situation` → `respond` for NPC dialogue (`DialogueEvent`, Hume-voiced).
3. The DM narrates as needed (`NarrationEvent`), pulling world + campaign-log context.
4. Consequences: update world state; **feed attributable events to NPC engines** via `remember(fact, t=clock, player_role=…)`; append to `CampaignLog`.
5. On cadence / between scenes → `deliberate` NPCs → enact `world_action`.

**Combat (turn-based), entered on encounter/aggression:**
1. Roll initiative; the rules core runs the round structure.
2. On each combatant's turn: player actions via the view; generic enemies via simple rules AI; a named NPC via `choose_action(percept, [afforded combat options])`, grounded in its state.
3. The rules core resolves outcomes; the DM narrates them.
4. Notable combat moments worth remembering (a betrayal, a rescue) are pushed to the relevant minds via `remember`.
5. On combat end → `ModeChanged` back to free-flow.

Emit updated `StateSnapshot` + events to the view throughout.

---

## Characters — reskinned from the tuned cast
A `Character` is a data profile. For each MVP **named** NPC: **clone the psychological fields** (disposition, personality, speaking style, and the tuning that produced the validated behavior) from an existing character, and **reskin the identity** — new name, background, world role, voice id, and a **fresh `memory_namespace`** so the mind starts empty and they meet the player in-world.

Provide **two** for the MVP, chosen to showcase the differentiator: a **guarded/schemer** analog (Corvin-derived) and a **warm** analog (Bri-derived). Identical events should evolve them differently — the thesis on screen. Assign each a world role via `game_data`. (Generic enemies are *not* characters — stat-blocks only.)

---

## Phase A — Python game-core + disposable tcod/ASCII dev view (proves the game AND the differentiator)
Build here first, entirely in Python, where you can run and self-correct in the terminal.

1. Step 0 inspection; scaffold `game/`, reusing existing game-layer utilities where present.
2. Game state model + rules core (d20 checks + turn-based combat) behind the extensible interface, as tools.
3. Create the two reskinned named characters (fresh namespaces).
4. Engine integration: one `Engine` per named NPC; `Situation` with clock; `respond` for dialogue; depth flags on.
5. DM narrator (game-layer LLM) + campaign-log retrieval; adjudication via tools.
6. Procedural single-dungeon gen **with generated enemies/encounters** + a **tcod/ASCII dev view** rendering the map, narration, dialogue, and combat, with player input and mode switching (free-flow ↔ combat). This view is **disposable** — keep it thin.
7. `choose_action` for NPC on-map/combat behavior; feed attributable events via `remember(player_role=…)`; `deliberate` between scenes; enact `world_action`.
8. World save/load.
9. **Differentiator proof scenario:** a short playable dungeon where the player's attributable actions toward a named NPC visibly shift its dialogue *and* behavior within a session, and persist across a restart. Verify against the engine's `MEMORY_DEBUG` 🧠 panel (relationship axes moving, salient memories injected).

**Phase A acceptance:** a playable-in-terminal slice — free-flow exploration of a procedurally generated dungeon with generated enemies, turn-based combat that resolves deterministically, a DM that narrates and adjudicates, and at least one named NPC that demonstrably evolves from attributed events (visible in behavior/dialogue, confirmed in the debug panel), with world + minds persisting across a restart. *This is the go/no-go for the whole game — do not start Phase B until it's real.*

## Phase B — Godot 4.x native desktop game (downloadable / Steam), NOT a web app
The game-core is **unchanged** from Phase A. Only a local-IPC wrapper and a Godot client are added.

Godot 4.x exports a **native desktop executable** (Windows/Mac/Linux) — the downloadable, Steam-shippable game. The Python game-core + engine ships **bundled as a local companion process** the Godot client talks to over **local IPC (localhost WebSocket or pipes)** — inter-process communication on the player's own machine, **not a hosted server or browser**; the player never sees it.

> **Packaging reality:** bundle the Python side (PyInstaller or equivalent) and have the Godot executable **launch/supervise it as a local subprocess**. This is heavier than a pure-Godot game (two runtimes bundled) and is the price of reusing the Python engine rather than porting it — a Phase-B packaging task, not a Phase-A concern. Because the core runs locally, the **local-model/offline path stays open** (the key to a true buy-once Steam title; cloud LLM/voice calls otherwise require internet + per-player cost — your deferred monetization decision).

Steps:
1. Wrap the `GameSession` interface as a **local IPC service** (same seam pattern the engine already uses; localhost WS or pipes). `get_state` / `submit_action` / `events` map onto messages.
2. Build a **Godot 4.x native project as a client**: connect over local IPC; render the map with a `TileMap`, player/NPCs/enemies as sprites/portraits, a dialogue/narration + combat UI, and play the engine's Hume-voiced NPC audio (raw PCM) — optionally drive a 2D portrait rig with ARKit-52 face frames.
3. Wire input → `submit_action`; render `StateSnapshot` + `NarrationEvent`/`DialogueEvent`/`CombatEvent`/`ModeChanged`.
4. **Wire up a Godot MCP so Claude Code can build scenes, attach scripts, run, and screenshot** — recommend `godot-ai` (GDAI) or Godot MCP Pro. Expect GDScript's loose typing to make agent calls fail more often than Python and more manual runtime debugging than Phase A. Build scenes via MCP; **keep all game logic in the Python core — never re-implement it in GDScript.**
5. Configure **native export presets** for the target platforms; bundle + launch the Python companion process; smoke-test the packaged build.

**Phase B acceptance:** the same proven core, now a native desktop build with tiles/sprites, dialogue/narration/combat UI, and Hume-voiced NPCs — **logic 100% reused, only the renderer new**, packaged as a downloadable executable.

---

## What NOT to build (recap)
- No mind logic (memory / relationship / personality / salience / belief / evolution) — drive the engine.
- No game concepts in engine code — use `register_game_extension` + `game_data`.
- No NPC *psychological* readout (feelings/relationship/mood) — felt through behavior. (Mechanical stats *are* fine: follower HP, and a player-toggled enemy-HP readout in combat.)
- No `engine.react()` — compose the recipe.
- Don't run the engine's clock — the game owns cadence + clock.
- Don't build a parallel voice stack; voice = Hume Octave via the modular `TTSAdapter` seam (EVI ruled out).
- Don't assume web deployment — target native desktop.
- Don't re-implement game logic in GDScript — Godot is a renderer over the Python core.

---

## Tech stack (locked)
| Concern | Choice |
| --- | --- |
| Game-core language | **Python** (drive the engine in-process or over local IPC) |
| Data models | **Pydantic** |
| Rules | **extensible d20** — lightweight now, behind a clean interface, designed to grow to **BG3-depth 5e** later; surfaced as engine tools |
| Maps | **procedural dungeons** (BSP + cellular automata) **or authored towns/cities** (e.g. Tiled), behind one `WorldMap`; FOV/pathfinding; **encounter/enemy generation** (stat-blocks; named ones promotable to Engine minds) |
| Party UI | **mechanical** stats shown: follower HP; **player-toggle** for enemy HP in combat (no *psychological* readout) |
| Pacing | **free-flow exploration/social; turn-based combat** |
| DM | **game-layer LLM narrator** (not a Character) + campaign-log retrieval |
| NPC minds | **engine `Engine` instances** via the seam — never reimplemented |
| Voice / face | **Hume Octave** via the engine's modular `TTSAdapter` seam + ARKit-52 bridge — consumed, not rebuilt |
| Memory store | **engine-owned** (JSONL + fastembed/lexical, RR-scored) — untouched |
| Game concepts | `register_game_extension` + `game_data` + renderer |
| Depth flags | **all engine capabilities default ON** (relationship, time-decay, reflection, intent, salience, commitment + contradiction detection, recent-happenings, arena-query, reinforce-on-recall) + always pass `clock` |
| Renderer | **tcod/ASCII dev view (Phase A, disposable)** → **Godot 4.x native desktop export, Steam-shippable (Phase B)** |

## Working method
- Inspect first; build coherently with the existing engine and any game layer; ask if the seam or existing game state is ambiguous.
- Work incrementally; **validate each Phase A step**, and prove the differentiator, before touching Phase B.
- Keep the game-core strictly renderer-agnostic behind the `GameSession` interface — the tcod view and the Godot client consume the same one.
- Write a README so a stranger could run Phase A in the terminal and, later, build + launch the native Godot client against the same core.

---

## Roadmap — deferred until AFTER the Godot proof-of-concept (do NOT build before PoC)

**Order of operations (owner decision, 2026-07-06):** finish the **full proof-of-concept in Godot (Phase B)** on the *current* content model before fleshing out a real game. Today we do **constructive PCG**: the **map layout is procedural** (seeded rooms-and-corridors + cellular-automata caverns, connectivity enforced by `dungeon._assert_connected`), while enemies / loot / NPCs / objective are **authored per slice** and *placed* on procedural anchors (`Dungeon.spawns`). That is a standard, respected pattern and is enough to prove the PoC.

**Deferred (post-PoC) — procedural CONTENT generation.** The below is a large build (enemy classes, difficulty math, balancing) and is premature before the PoC lands. It all lives in the **content layer on top of the existing map + anchor-population seam — NO game-core change** (the seam was audited + adversarially verified slice-agnostic; the headless harness proves both slices — vault's rooms-and-corridors and emberdeep's cellular-automata caverns — run the full scripted playthrough with zero core edits, and a worktree exercise validated authoring a new slice without touching the core):
- **Enemy system:** enemy *classes / archetypes* (e.g. melee brute, skirmisher, archer, caster, support) with distinct **attack profiles** (the `Combatant.damage_dice` / `attack_ability` seam already exists) and behaviors; **stat-block generation** rather than hand-authored rosters.
- **Difficulty / depth scaling:** a CR-like budget so encounters scale to player level / dungeon depth (Pawson's "loot scaled to rank" idea, generalized to foes).
- **Loot tables:** depth/level-scaled loot with **rarity tiers**, rolled per run (today loot is DM-narrated + authored keys only).
- **Encounter composition:** a budget-based encounter builder that picks a *mix* of enemy classes to a target difficulty for a room / depth, then places them on anchors.
- **Tactical combat (owner feedback 2026-07-06):** hard fights should reward *positioning and setup*, not just HP trades. Deepen the turn-based layer toward a BG3 / tactics-RPG feel: grid tactics (flanking, attacks of opportunity, chokepoints), **cover + terrain use** (leans on the obstacle/terrain tiles above), formations and the **party acting as a coordinated unit**, action economy, ability/spell options, and enemy AI that actually *plays the map* (focus-fires, takes high ground, avoids bad ground). The combat mode + per-combatant attack profiles already exist as the frame; this is the depth pass so encounters become puzzles you set up for.
- **Secret walls / hidden passages:** a hidden door/wall (a `Door` or wall tile with `hidden=True` + `reveal_dc`) that renders as solid until a **search / perception check passes** — the DM already calls `ability_check`, so this slots in with no new machinery; adds exploration reward and optional shortcuts/loot rooms.
- **Obstacles & terrain types:** expand the tile vocabulary beyond wall/floor/door/stairs — pillars, rubble, water, chasms, hazard/cover tiles, destructibles — plus the **rules effects** they carry (block/slow movement, break line-of-sight, deal damage). Data-model + rules work; the generator seeds them, content authors them.
- (Optional, further out) noise-driven **biome / hazard tile variation** (Perlin), and additional map generators (BSP, drunkard's-walk) behind the same `generate_*` contract.

**Deferred further — presentation / dimensionality:**
- **2.5D & elevation gameplay:** height layers, high-ground advantage, line-of-sight by elevation, falling. Two parts kept distinct: *2.5D as a rendering choice* (isometric / layered sprites) lives in the **Godot client** over the same flat tile grid; *elevation that affects gameplay* is a deeper **core** change (data model + rules). Both deferred until well after the PoC.

**Guard already in place for this:** `game/rpg/gencheck.py` fuzzes every generator's invariants across N seeds (connected floor, reachable stairs, valid anchors) — extend it to cover generated encounters/loot when that work begins.

**Deferred — social / dialogue systems (owner feedback 2026-07-06, during the Godot buildout):**
- **Dialogue- and mission-driven recruitment:** recruiting a companion must be *earned through conversation* (and, for some characters, a condition/quest — e.g. Vael only comes if you've convinced him you're on his side, or completed something for him), NOT a single "press R" keypress. The current R-recruit is a placeholder that only proves companions can follow + fight; replace it with a conversational/quest gate per character. The engine already decides join/refuse via `choose_action` grounded in disposition — the missing piece is a game-layer *social flow* (talk → build trust / satisfy a condition → the join offer becomes available) instead of an instant command.
- **Player SPEAKS their intent (voice-in), not typing:** like a real tabletop session, the player should be able to *say* what they want to do / say to an NPC, transcribed by the engine's existing STT (AssemblyAI), instead of typing into a box. Ties into the voice work: the client captures mic → STT → the text becomes the `talk`/`do` input. (Text entry stays as a fallback.)
- **Stage directions → DM narrates them IF relevant (NOT shown as text).** *Done so far:* the reply is split into quoted speech vs. third-person action beats; only the **quoted speech** is shown as the dialogue line and voiced (Hume). *Corrected design (owner, 2026-07-06)* for the action beats: they are **not rendered as description text** ("isn't gonna be read"). Instead, an NPC's stage directions are handed to the **DM, which decides by relevance whether to narrate them aloud** (RR/DM-gated — a hand drifting to a weapon matters; shifting weight off a leg usually doesn't), narrated as DM narration (optionally in a narrator voice). To build: route the `action` field to the DM for a relevance judgment. **Design constraint (owner):** the DM is a **narrator/referee, NOT a character** (no mind, memory, RR) — so this must be *narrative* relevance ("what's worth telling the player", an ordinary narrator function), never *cognitive* relevance ("what the gesture means to the NPC", which is the engine's RR and off-limits to the DM). The moment the DM must interpret the NPC's inner state to judge a gesture, it's reaching for a mind it can't have. Lightest form: an NPC's visible action is just more world for the DM's normal narration pass to describe or skip — no new "relevance faculty" bolted on. **Do NOT** cap NPC reply length/verbosity with game-layer rules — length must emerge from the character + the relevance engine (a deterministic "keep it short" nudge was tried and reverted).
