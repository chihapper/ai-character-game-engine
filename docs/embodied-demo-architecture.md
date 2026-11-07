# Embodied demo — rough architecture (draft for review)

> **Status (2026-11-07):** Design record, last edited 2026-07-01 and corrected in place on this date.
> The grid arena (`game/arena/`, served at `/embodied`) is built and is on every branch; its code
> last changed on 2026-07-02. The 3D phase was built differently from this design: Unity and Unreal
> each own their world and reach the engine through the mind server (`/api/mind`), not through the
> arena. Stakes were never built, and the embodiment comparison (GitHub issue #30) was never run. In
> the 2026-11-07 review the test suite passed (72 tests on this branch) and `/embodied` loaded, but
> nobody played the arena. Its last logged run is from 2026-07-01. The Unity and Unreal clients were
> not run either.

> The #30 **treatment arm**: an embodied version of the ferry scenario to sit beside the text game
> (the control). Written after playtesting exposed that every text bug — names, inner-state,
> spatial drift, who's-present — is the *same* root problem, and it's the one embodiment removes.
> This doc records the settled design; §14 holds the deferred future. Companions:
> [engine-game-contract.md](engine-game-contract.md),
> [embodiment-experiment.md](embodiment-experiment.md),
> [unity-client-architecture.md](unity-client-architecture.md), [unreal-port.md](unreal-port.md).

---

## Built vs proposed

The sections below keep the design rationale, with *As built* notes where the code differs. This
table is the summary, checked against the code. `game/arena/` is identical on `main`,
`credibility-demo`, and `game-rpg`.

| Proposed | State | What exists |
| --- | --- | --- |
| Arena world model (§3) | Built, narrowed | `game/arena/world.py` and `maps/ferry_inn.yaml`: an 11x7 grid, 6 named regions, 6 fixtures (one never appears), and bodies with a position and a stance |
| World facts: door state, held objects, storm, ferry (§3) | Not built | Only positions, stances, and the clock change |
| First-person perception (§4) | Built, narrowed | `game/arena/perception.py` derives each percept (what one agent perceives right now) from the world. Everyone in the room is always perceived |
| Visibility, earshot, facing (§3, §4) | Not built in the arena | Distance only grades a proximity phrase. Unity's client does its own line-of-sight checks |
| Action vocabulary and resolver (§5) | Built, narrowed | Five kinds: `move`, `approach`, `use`, `watch`, `wait`. A `use` action only changes the actor's stance text |
| Action seam (§5.1) | Built differently | `Engine.choose_action(situation, options)`. The game passes option labels on each call, and nothing is registered |
| `world_action` executed against the world (§2, §5) | Not built | The arena never calls `deliberate()`, so it never receives a `world_action` |
| Stakes and needs (§6) | Not built | The nearest things are per-act magnitude hints (`OBJ_MAGNITUDE` in `game/policy.py`) and the proximity phrase in what each NPC observes |
| Player as a body (§8) | Built | Position is authoritative. The page drives `act`, `talk`, and `advance` |
| Phase A, text view (§9) | Built | `render_player_view` is plain code with no LLM. The arena has no Game Master |
| Phase B, 2.5D web (§9) | Minimal version | `/embodied` draws a flat tile grid with tinted regions and letter markers. No fixtures, portraits, or line of sight |
| Phase C, 3D (§9) | Built differently, frozen | Unity (first commit 2026-07-02) and Unreal (first commit 2026-07-03), both over `/api/mind`, each with its own world. They share the engine, `game/policy.py`, `game/casting.py`, `game/experiment_log.py`, and the ferry scenario file with the arena, but not its world |
| #30 comparison (§10) | Not run | 210 rows logged up to 2026-07-05, none evaluated. No judge or emergence-metric tool exists |
| Procedural maps, action economy (§14) | Elsewhere | `game/rpg/` on the `game-rpg` branch, separate from the arena |

---

## 0. The one insight this is built on

The text game breaks because **prose has no world.** The Game Master is an LLM *inventing* the world
every turn, so it contradicts itself (you're at the bar, then the door), leaks names nobody gave, and
voices thoughts you couldn't know. We've been bolting on scaffolding (position tracking, name state,
name scrubbing, "player's-eyes" prompts) to *fake* a ground truth.

**The embodied demo inverts this: build an authoritative WORLD MODEL that is ground truth, and demote
the Game Master from an inventor to a *view* of it.** Perception is *derived* from the world (what you
can actually see from where you stand), actions *change* the world (with consequences you must
re-perceive), and the character's stakes are *in* the world. The grounding bugs don't get fixed — they
**can't happen by construction.**

This is also exactly the RR/embodiment thesis (#30): relevance realized by an agent **coupled to a
world through a first-person body**, not handed a paragraph.

---

## 1. What "embodied" means here (and what it doesn't)

- **NPC-side cognitive embodiment (the thesis-critical part):** the character perceives a real world
  from a *vantage* (partial, first-person), *acts* into it with consequences, and has *situated stakes*.
  Its relevance realization is grounded in that coupling.
- **Player-side presence (the "puppet"/presentation part):** how it looks on the player's screen —
  text, 2.5D, or 3D. This is real polish but it is **not** the cognitive variable.

**Key consequence:** the cognitive embodiment — the thing #30 actually tests — is achieved by the
**world model + perception/action/stakes loop**, *independent of the renderer*. A 3D engine adds
*presence and perceptual fidelity*, not a different kind of mind. So we can run the embodiment
experiment **without Unity** and add visual presence as a later, additive layer.

---

## 2. Layered architecture

The grid arena, as built:

```
┌───────────────────────────────────────────────────────────────────────┐
│ RENDERER   (player-side presence — swappable)                         │
│   /embodied page: text readout of the percept + flat tile grid        │
└───────────────▲───────────────────────────────────┬───────────────────┘
        player percept (derived)          player input (act / talk / advance)
┌───────────────┴───────────────────────────────────▼───────────────────┐
│ EMBODIMENT LAYER   (game/arena/)                                      │
│   • ARENA — authoritative world (grid, regions, fixtures, bodies)     │
│   • PERCEPTION — derive each agent's first-person percept from it     │
│   • ACTIONS — list what a place affords; apply the label chosen       │
│   • STAKES/NEEDS — proposed, not built                                │
└───────────────▲───────────────────────────────────┬───────────────────┘
   Situation + option labels (grounded percept)   chosen label → executed
┌───────────────┴───────────────────────────────────▼───────────────────┐
│ ENGINE   (orchestrator/; one agnostic seam added)                     │
│   respond · remember→salience(#25) · choose_action                    │
│   the MIND: memory, RR, relationship, goals, metamorphosis            │
└───────────────────────────────────────────────────────────────────────┘
```

The **engine core stays free of arena specifics.** It already took a `Situation`, and it gained one
agnostic seam, `Engine.choose_action`. `orchestrator/` imports nothing from `game/`. The richer
*game/arena* (a) feeds it a **grounded, derived** percept instead of Game Master prose, and (b) offers
bounded option labels, lets `Engine.choose_action` pick one, and **executes** that choice with
`execute()` in `game/arena/actions.py` instead of narrating it. The arena never calls `deliberate()`
and never uses `world_action`; on this branch, only the text game does among the game surfaces, and
it narrates the result. The world behind the seam becomes real.

The 3D clients are a separate path, not another renderer of this arena:

```
Unity or Unreal client   (owns its own world, composes each NPC's percept)
        │  HTTP
        ▼
Mind server, /api/mind   (game/bridge/mind_api.py)
        │
        ▼
ENGINE                   (same Engine; react thresholds from the same game/policy.py)
```

---

## 3. The Arena (authoritative world model)

Ground truth, engine-agnostic, renderer-agnostic:

- **Space.** A **grid (tiles)** under the hood — cells with (x,y) for distance / line-of-sight /
  pathfinding, a foundation ready for SRD-based tabletop rules and procedural maps — but **presented
  as NAMED LOCATIONS**,
  never raw coordinates. Labelled regions/landmarks ("the hearth", "the bar", "the door") overlay the
  grid, so perception and narration say *"by the hearth,"* not *"(12,4)."* Grid mechanics, human-legible
  place. (A small authored inn-map whose regions are its spots is enough to start; the grid earns its
  keep later for tabletop-RPG exploration/combat and procedural maps.) *As built: an 11x7 grid with 6
  named regions. Only distance reads the grid. There is no line-of-sight or pathfinding; a move places
  the body directly on a free cell.*
- **Entities.** Each NPC, the player, and objects have a position, and (for agents) a facing/attention.
  *As built: `Entity` has only `id`, `pos`, `kind`, and `stance` (observable activity, as text). There
  is no facing. Objects are `Fixture` records that nobody can hold or move.*
- **Objects & fixtures.** The fire, the bar, the door, the nailed warrant, a cup — with **affordances**
  (what can be done with them: `take`, `open`, `read`, `sit`, `warm-at`). *As built: the fixtures are
  the peat fire, the bar, the door, the shuttered window, a corner table, and a crown warrant that
  never appears, because no code sets its `present` flag. There is no cup. The affordances are warm at,
  watch, lean at, order a drink at, slip outside, bar, look out, and sit at, plus read and take down on
  the absent warrant. Using any of them only sets the actor's stance text.*
- **Visibility / earshot.** Who and what each position can *see* and *hear* (occlusion, distance,
  whether someone's back is turned). This is what makes perception **partial and first-person.**
  *As built: not built. Every entity and present fixture is perceived from anywhere, and everyone
  witnesses every player act. Distance only grades a proximity phrase ("close by", "across the room"),
  and the player view's "Within reach" line lists every fixture in the room.*
- **Time.** The existing game clock. *As built: the arena keeps its own clock, starting at 0. The
  page's "the night moves on" button advances it by 2 hours.*
- **Facts/state.** Door open/closed, who holds what, the storm's stage, the ferry's approach. *As built:
  not built. The only facts that change are positions, stances, and the clock. The storm arc exists
  only on the 3D path, as `ambient` text the client sends to the mind server.*

Everything downstream reads from the arena; nothing invents world facts.

---

## 4. Perception (first-person, derived — replaces `dm.scene_perception`)

For each agent, the perception system computes a **percept** from the arena + that agent's
position/senses:

- who & what is **in view/earshot** (not "all cast" — only what your vantage affords → **fixes
  presence by construction**). *Phase A narrowing: the ferry inn is ONE room, so everyone present
  is in view; distance still grades proximity. Vantage-limited presence (occlusion, earshot) is
  exactly what the continuous-space world model adds.*
- their **observable** state only — position, posture, action, facing, tone (never inner state →
  **fixes the inner-thought leak by construction**). *As built: region, proximity phrase, and stance.
  No facing or tone.*
- ambient (storm, firelight, smell). *As built: not built.*
- **what changed** since last tick. *As built: not built. `Percept` holds `agent_id`, `region`,
  `others`, `fixtures`, `clock`, and `elapsed`.*

This percept becomes the engine's `Situation` (structured, packed into `Situation.extra`/fields) for
`respond()`: grounded, consistent input. For action choices, `Engine.choose_action` receives the
percept as rendered text plus what just happened. **Names** are a property of *acquaintance* (have you
been introduced / do you recognize this face). *Phase A narrowing: acquaintance is tracked by the game
(`known_names`, learned from spoken introductions) and prose is still scrubbed as a safety net —
carrying it fully in the world is a visual-build win (see #34's closing analysis).*

The player gets a percept the same way; the renderer draws it.

---

## 5. Action & consequence (the enacted loop — the core)

In the text game, `world_action` is a prose string the game narrates. In the arena, the character
instead makes an **executable choice** that changes the world:

- A small **action vocabulary**. Proposed: `move/approach(target)`, `take/give(object[,who])`,
  `speak(who)`, `watch(who)`, `open/close(door)`, `hide`, `leave`, `intervene`, … *As built: five kinds,
  `move`, `approach`, `use`, `watch`, and `wait`. Talking is not an action; it runs through `respond()`.*
- The **resolver** maps the character's choice to world-state changes (Corvin *actually* crosses to the
  door), with **consequences the agent then re-perceives**. *As built: `execute()` in
  `game/arena/actions.py` applies the chosen label, and the consequences are a new position or a new
  stance. A `use` action such as `bar the door` changes no door state, and the proposed example of the
  warrant leaving the wall can't happen, because the warrant never appears.*
- That closes **perception → salience → action → consequence → perception** — the embodiment loop, and
  the RR frontier. The character isn't *described* as acting; it *acts*, and the world answers.

*As built, NPCs choose an action in two cases: when the clock advances, and when a player act scores
from 0.75 up to 0.9 on their own salience appraisal. At 0.9 or above they speak through `respond()`
instead. Below 0.75 the act is remembered and nothing else happens.*

**Decision — STRUCTURED actions via an agnostic "action seam" (§5.1).** Prose+resolver is a testing
shortcut, not product-grade; we go structured from the start (closer to the real product, and it's what
makes "you can't walk to Mother Sael's — she isn't here" true by construction).

### 5.1 The action seam (keeps the engine game-agnostic)

The worry — "does structured action force a game-specific engine?" — is answered by the **tool-calling
pattern**: the engine gains a *general* ability to emit a **structured action chosen from a vocabulary
the GAME supplies**; it never names any game's actions.

- The **game supplies its action vocabulary** on every call. The proposal was a registered schema
  (`move(to)`, `give(object, who)`, `hide`, … for a social scene; `attack`, `cast`, … for SRD-based
  combat) in the shape of `register_game_extension(namespace, renderer)`. *As built, nothing is
  registered and there is no schema: `game/arena/game.py` passes a fresh `list[str]` of afforded labels
  such as "cross to the bar", and the structured meaning stays in `game/arena/actions.py`.*
- The **engine** (`Engine.choose_action`) picks one valid label from what the arena currently affords
  and returns it with a short reason, plus expression fields the arena ignores. The choice is grounded
  in the character's evolved goals, near-term aim, feelings, and beliefs. `deliberate()` plays no part:
  neither the arena nor the mind server calls it.
- The **game/arena executes it** (per the contract: engine returns, game enacts).

Net: **engine core = free of arena specifics + agnostic; one new *agnostic* seam; the vocabulary lives
in `game/`.** This refines decision #5 from "engine frozen" to "core frozen + one agnostic seam." The
text control doesn't use the seam. The pair isn't cleanly matched for other reasons, listed in §10.

---

## 6. Stakes / needs (grounding salience in the body)

*As built: nothing in this section exists. `game/arena/` has no stakes or needs code. The nearest things
are the game's magnitude hints per act kind (`OBJ_MAGNITUDE` in `game/policy.py`) and the proximity
phrase inside what each NPC observes.*

The deepest embodiment variable: the agent's **viability is in the world.**

- **Situated stakes:** proximity to threat (the crown's men at the door), an exit blocked, being seen.
- **Bodily needs (optional, powerful):** cold/wet, fatigue, hunger — low-grade drives that *shape what's
  salient* (a fugitive near the door reads the room differently than one warming at the fire).
- These feed the existing salience appraisal (#25): relevance realized relative to embodied stakes, not
  only social/narrative ones. This is where "a body that can lose something" grounds caring.

---

## 7. The engine seam — what changes, what doesn't

The right column is as built.

| Concern | Text game (control) | Grid arena (treatment) |
| --- | --- | --- |
| World facts | invented by the Game Master (prose), over authored beats | **authoritative arena** |
| `Situation` | Game-Master-written perception | **derived first-person percept** |
| Presence | "all cast always" | everyone present is always perceived; distance grades a proximity phrase |
| Names | scrubbed from prose | `known_names` in the game, plus scrubbing of narration |
| `world_action` | narrated | **not used**; `choose_action` picks a label and `execute()` applies it |
| Stakes for salience | social/narrative | same as text; only the magnitude hint and proximity phrase differ |
| **The engine (`orchestrator/`)** | — | **free of arena specifics; one agnostic seam added, `Engine.choose_action`** |

The mind gained one seam and no knowledge of the arena. We gave it a world.

---

## 8. The player

The player is **also a body in the arena** (a position, a vantage). They perceive via the renderer and
act via input that resolves against the arena. *As built: the page drives a label-based `act` (which
includes movement labels), `talk`, and `advance`. A `/move` route also exists, but the page doesn't
call it.* Player position is authoritative → the spatial-drift bug is gone by construction (you are
where the world says you are, and you only move when you move).

---

## 9. Renderer ladder (as proposed: the same world model, three skins)

The proposal builds the world model **once**, and the renderer gets richer in phases. This de-risks
everything — each phase is playable and each is a valid experiment rung. *As built: this held for
Phases A and B, which share the arena. Phase C took a different route.*

- **Phase A — text view over the world model.** The Game Master becomes a pure *renderer* of the
  player's percept (narrate only what's in view; never invent). **The design expected this alone to
  deliver NPC cognitive embodiment and kill the grounding bugs**, as the fastest reference point. *As
  built: the arena has no Game Master. `render_player_view` is a plain function with no LLM, and
  `/embodied` is its own page (`game/web/embodied.html`, `embodied.js`), not the text game's UI. No
  evaluation has tested the expected result.*
- **Phase B — 2.5D web.** Draw the room: fixtures, character markers/portraits at their positions,
  movement, line-of-sight. Player-side *presence* without a game engine. Still the same arena. *As
  built: `/embodied` draws a flat tile grid with tinted regions and letter markers for people. It draws
  no fixtures, portraits, or line of sight.*
- **Phase C — 3D (Unity/Unreal).** Proposed: the arena becomes a 3D scene and the same world model
  drives it. Maximal presence + perceptual fidelity. The "full" embodied demo. Biggest cost; purely
  additive. *As built: the 3D clients don't use the arena. Unity came first (2026-07-02), then Unreal
  (2026-07-03). Each client owns its own world, composes percepts itself, and calls the mind server, and
  runs log as `TREAT-EMBODIED-3D`. The engine, `game/policy.py`, `game/casting.py`, `game/experiment_log.py`, and the ferry scenario file are shared with the arena; its world is not. Both
  clients are frozen; see [project-status.md](project-status.md).*

---

## 10. Mapping to the #30 experiment

The phases *are* an embodiment-richness gradient, which is exactly the experiment:

- **Control** = the prose text game (world invented by narration).
- **Treatment (min)** = **Phase A** (authoritative world model + enacted loop + situated stakes, text
  view). Isolates *"what does a real, coupled world buy?"* from mere prose.
- **Treatment (rich)** = **Phase B/C** (added continuous space + perceptual fidelity + presence).
  Isolates *"what does richer embodiment/immersion add on top?"*

The design: same scenario, same cast (the ferry-inn), same engine, same models held constant → the
matched-pair the notebook already specifies. Measures are unchanged (blind RR judge + emergence
metrics + blind human preference, all post-hoc on transcripts). **A real #30 comparison at Phase A
needs no Unity.** (Still Bet 1 only; a sim body isn't autopoietic, so this probes, never proves, Bet 2.)

*As built: no comparison has been run.* The run log has 210 rows, with no `rr_judge` or `emergence`
values, and no judge or metric script exists. The arena has no stakes, so the treatment is less than
the design above. The pair also isn't matched. The scenario file and cast are shared, but:

| | Text game (`/play`) | Grid arena (`/embodied`) |
| --- | --- | --- |
| Story | 5 authored beats with scripted events | no beats or events; the clock just advances |
| `deliberate()` | runs at each beat advance and for reactions | never runs |
| Reaction thresholds | 0.7, then `deliberate()` | 0.75, then `choose_action`; 0.9, then `respond()` |
| Default reply model | Haiku | Sonnet |

A fair run needs parity on beats, events, and deliberation first. The 3D arm records no transcripts,
so post-hoc measures can't reach it as built.

---

## 11. Rough build milestones

Status added 2026-11-07. Commits are dated 2026-07-01 unless noted.

1. **Arena** — the ferry-inn as a world model (grid with named regions, positions, objects/affordances,
   visibility, the cast placed in it). **Built** in `047932b`, without visibility.
2. **Perception** — derive each agent's first-person percept; feed it as the engine `Situation`. Demote
   the Game Master to a text renderer of the *player's* percept. **Built** in `047932b`, with no Game
   Master at all.
3. **Action/resolver** — map `world_action` → arena effects (approach/take/give/leave/watch); close the
   loop with re-perception. **Built differently** in `7ed875c` as `choose_action` over option labels,
   and moved onto `Engine` in `70ef84d`.
4. **Stakes/needs** — situated + light bodily drives feeding salience. **Not built.**
5. **Player embodiment** — position, move, interact; **Phase A playable** end-to-end. **Built** in
   `1877842`, with the page in `8618591`.
6. **#30 run** — Phase A vs the text control on the same scenario; read the judge + metrics. **Not run.**
7. **Phase B** — 2.5D web renderer over the same arena. **Minimal version only:** the tile grid in
   `/embodied`.
8. **(stretch) Phase C** — Unity/Unreal. **Built differently,** over the mind server: Unity in `2451cc7`
   (2026-07-02), then Unreal in `855b189` (2026-07-03). The move from Unity to Unreal was decided on
   2026-07-02 ([unreal-port.md](unreal-port.md)). Both are frozen.

---

## 12. Decisions — SETTLED (review 2026-07-01)

1. **Space model → GRID (tiles), presented as NAMED LOCATIONS.** Grid under the hood (ready for
   SRD-based rules and procedural maps); the player only ever sees labelled places ("the hearth"),
   never coordinates (§3).
2. **Action intent → STRUCTURED, via an agnostic action seam (§5.1).** No prose+resolver — not
   product-grade. Structured actions are the priority; they're what the real product needs and what
   makes "that place isn't reachable from here" true by construction.
3. **Stakes → situated only for now.** Bodily needs (cold/fatigue) deferred — build on the loop later.
   *As built: situated stakes weren't built either (§6).*
4. **First renderer → Phase A (text view) for CHEAP VALIDATION ONLY.** Prove the world-model + structured
   loop kill the grounding bugs; **not** a full play-through. Then move to the visual (a 2D tile map,
   given the grid). *Note (2026-11-07): a small grid view shipped with `/embodied`, and the project then
   went to Unity and Unreal. The tile-game direction came later as the Godot client on the `game-rpg`
   branch, which has its own game core in `game/rpg/` and doesn't use this arena.*
5. **Engine agnosticism preserved (refines "frozen").** Mind (`orchestrator/` core) free of arena
   specifics; add exactly ONE new *agnostic* seam — the action seam (§5.1). As built it is a method that
   takes labels on each call, not a registration point like `game_data`. Game-specific vocabulary lives
   in `game/` (e.g. `game/arena/`).
6. **Scenario → reuse the ferry-inn + cast** for the matched pair ("seems very real" bar the known text
   limits). Small AUTHORED map first; procedural later (§14).

---

## 13. Risks & honest limits

- **Scope creep:** an arena/immersive-sim is real engineering; the grid with named regions + minimal
  action set keep it bounded. Don't build a physics engine.
- **It still doesn't prove Bet 2.** A simulated body isn't autopoietic; even Phase C *probes* whether the
  enacted loop deepens RR — it can't establish that genuine embodiment is *necessary*.
- **The visual is not the mind.** Phase B/C are presence; if we ever feel "the 3D made it alive," check
  it against Phase A to separate presence from cognition.

---

## 14. Future directions (logged — not now)

*Note (2026-11-07): procedural dungeons and caverns and a turn-based action economy now exist in
`game/rpg/` on the `game-rpg` branch. That code doesn't use the arena's world or its `Action` records.
It does call the same `Engine.choose_action` seam for some NPC choices. The items below stay as the
original plan.*

- **Procedural dungeons + hand-authored cities (the intended hybrid).** The product design: maps are
  **procedurally generated for dungeon-crawling** and **hand-authored for city / settlement / social
  settings.** This is both a variety win (fresh dungeons every run) *and thesis-protective by
  construction*: the persistent, metamorphosis-carrying NPCs live in the **authored social hubs**
  (cities), where the character depth is, while procedural generation supplies the tactical / exploration
  breadth in dungeons where it's cheap and welcome. Kept OUT of the #30 experiment (randomised maps would
  break the matched pair) — a *product* feature, added once the embodied mind-loop is proven on a fixed
  authored map. The grid foundation is procedural-ready (dungeon generators produce grids).
- **Grid-tactical / open-exploration duality.** A resolution switch on the *same* world model: a fine
  grid for tactical / dungeon play, coarser/open movement for exploration. The pattern we want is the
  combat-grid + open-exploration duality, which hand-authored party RPGs already use.
- **Thread the needle — metamorphosis *and* a tabletop-RPG frame.** The thesis lives in social/relational
  depth; a tabletop-RPG frame adds tactical/exploration. The goal to attempt (not now): procedural
  *world/dungeons* as the stage **+** persistent, embodied, evolving *authored NPCs* carrying the soul —
  so the campaign has both. Flagged to watch that tactical/procedural breadth never buries the character
  depth we're proving.
- **Action economy (turn budget).** When action becomes tactical (SRD-based combat especially), agents
  need an **action economy** — a per-turn budget: e.g. the SRD's *action + bonus action +
  movement + reaction* — so a turn is a bounded set of choices, not unlimited. Not built in the arena
  (the social ferry demo is free-form), but the arena's `Action` records are **economy-ready**: each carries a
  `type`/`cost` (action / bonus / move / reaction), and a future turn-manager could spend the budget.
  Nothing spends it yet. Leaving room for it now so we don't repaint the action schema later.

---

**Bottom line:** the design was to build the world model once, demote narration to a view, close the
perception→action→consequence loop with situated stakes, and render it progressively (text → 2.5D →
3D). As built, the world model, the view, and the loop exist without stakes, in text plus a flat grid.
The 3D clients went their own way over the mind server, sharing the engine, `game/policy.py`, casting, run logging, and the scenario file, but not the arena's world,
and the #30 comparison has not been run.
