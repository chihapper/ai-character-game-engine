# Embodied demo — rough architecture (draft for review)

> The #30 **treatment arm**: an embodied version of the ferry scenario to sit beside the text game
> (the control). Written after playtesting exposed that every text bug — names, inner-state,
> spatial drift, who's-present — is the *same* root problem, and it's the one embodiment removes.
> Status: **Phase A BUILT and playable** (`game/arena/`, `/embodied`) — this doc records the
> settled design; §14 holds the deferred future. Where the build intentionally narrowed a proposal,
> the section notes it. Companions: [engine-game-contract.md](engine-game-contract.md),
> [embodiment-experiment.md](embodiment-experiment.md).

---

## 0. The one insight this is built on

The text game breaks because **prose has no world.** The DM is an LLM *inventing* the world every
turn, so it contradicts itself (you're at the bar, then the door), leaks names nobody gave, and voices
thoughts you couldn't know. We've been bolting on scaffolding (position tracking, name state, name
scrubbing, "player's-eyes" prompts) to *fake* a ground truth.

**The embodied demo inverts this: build an authoritative WORLD MODEL that is ground truth, and demote
the "DM" from an inventor to a *view* of it.** Perception is *derived* from the world (what you can
actually see from where you stand), actions *change* the world (with consequences you must re-perceive),
and the character's stakes are *in* the world. The grounding bugs don't get fixed — they **can't happen
by construction.**

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

```
┌───────────────────────────────────────────────────────────────────────┐
│ RENDERER / CLIENT   (player-side presence — swappable)                  │
│   Phase A: text view   →   Phase B: 2.5D web   →   Phase C: 3D (Unity)   │
└───────────────▲───────────────────────────────────┬───────────────────┘
        player percept (derived)          player input (move / act / speak)
┌───────────────┴───────────────────────────────────▼───────────────────┐
│ EMBODIMENT LAYER   (game/, the new work)                                │
│   • ARENA — authoritative world model (space, entities, objects, time)  │
│   • PERCEPTION — derive each agent's first-person percept from the arena│
│   • ACTION/RESOLVER — turn an agent's intent into world-state changes    │
│   • STAKES/NEEDS — situated viability that grounds salience              │
└───────────────▲───────────────────────────────────┬───────────────────┘
   structured Situation (grounded percept)   world_action (returned) → executed
┌───────────────┴───────────────────────────────────▼───────────────────┐
│ ENGINE   (orchestrator/, UNCHANGED)                                     │
│   respond · remember→salience(#25) · deliberate→Decision(world_action)  │
│   the MIND: memory, RR, relationship, goals, metamorphosis              │
└───────────────────────────────────────────────────────────────────────┘
```

The **engine does not change** — it already takes a `Situation` and returns a `world_action` for the
game to enact (per the contract). We're building a richer *game/arena* that (a) feeds it a **grounded,
derived** percept instead of DM prose, and (b) **executes** its `world_action` against real world state
instead of narrating it. The seam is the same; the world behind it becomes real.

---

## 3. The Arena (authoritative world model)

Ground truth, engine-agnostic, renderer-agnostic:

- **Space.** A **grid (tiles)** under the hood — cells with (x,y) for distance / line-of-sight /
  pathfinding, a D&D-native and procedural-ready foundation — but **presented as NAMED LOCATIONS**,
  never raw coordinates. Labelled regions/landmarks ("the hearth", "the bar", "the door") overlay the
  grid, so perception and narration say *"by the hearth,"* not *"(12,4)."* Grid mechanics, human-legible
  place. (A small authored inn-map whose regions are its spots is enough to start; the grid earns its
  keep later for D&D exploration/combat and procedural maps.)
- **Entities.** Each NPC, the player, and objects have a position, and (for agents) a facing/attention.
- **Objects & fixtures.** The fire, the bar, the door, the nailed warrant, a cup — with **affordances**
  (what can be done with them: `take`, `open`, `read`, `sit`, `warm-at`).
- **Visibility / earshot.** Who and what each position can *see* and *hear* (occlusion, distance,
  whether someone's back is turned). This is what makes perception **partial and first-person.**
- **Time.** The existing game clock.
- **Facts/state.** Door open/closed, who holds what, the storm's stage, the ferry's approach.

Everything downstream reads from the arena; nothing invents world facts.

---

## 4. Perception (first-person, derived — replaces DM "scene_perception")

For each agent, the perception system computes a **percept** from the arena + that agent's
position/senses:

- who & what is **in view/earshot** (not "all cast" — only what your vantage affords → **fixes
  presence by construction**). *Phase A narrowing: the ferry inn is ONE room, so everyone present
  is in view; distance still grades proximity. Vantage-limited presence (occlusion, earshot) is
  exactly what the continuous-space world model adds.*
- their **observable** state only — position, posture, action, facing, tone (never inner state →
  **fixes the inner-thought leak by construction**),
- ambient (storm, firelight, smell),
- **what changed** since last tick.

This percept becomes the engine's `Situation` (structured, packed into `Situation.extra`/fields). Same
`respond()`/`deliberate()`; grounded, consistent input. **Names** are a property of *acquaintance*
(have you been introduced / do you recognize this face). *Phase A narrowing: acquaintance is tracked
by the game (`known_names`, learned from spoken introductions) and prose is still scrubbed as a
safety net — carrying it fully in the world is a visual-build win (see #34's closing analysis).*

The player gets a percept the same way; the renderer draws it.

---

## 5. Action & consequence (the enacted loop — the core)

Today `world_action` is a prose string the game narrates. Here it becomes an **executable intent** that
changes the arena:

- A small **action vocabulary**: `move/approach(target)`, `take/give(object[,who])`, `speak(who)`,
  `watch(who)`, `open/close(door)`, `hide`, `leave`, `intervene`, …
- The **resolver** maps the character's intent to world-state changes (Corvin *actually* crosses to the
  door; the warrant *actually* leaves the wall), with **consequences the agent then re-perceives**.
- That closes **perception → salience → action → consequence → perception** — the embodiment loop, and
  the RR frontier. The character isn't *described* as acting; it *acts*, and the world answers.

**Decision — STRUCTURED actions via an agnostic "action seam" (§5.1).** Prose+resolver is a testing
shortcut, not product-grade; we go structured from the start (closer to the real product, and it's what
makes "you can't walk to Mother Sael's — she isn't here" true by construction).

### 5.1 The action seam (keeps the engine game-agnostic)

The worry — "does structured action force a game-specific engine?" — is answered by the **tool-calling
pattern**: the engine gains a *general* ability to emit a **structured action chosen from a vocabulary
the GAME supplies**; it never names any game's actions.

- The **game registers its action vocabulary** (a schema: `move(to)`, `give(object, who)`, `hide`, … for
  a social scene; `attack`, `cast`, … for D&D combat) through a **seam** — the same shape as the
  existing `register_game_extension(namespace, renderer)` / `game_data` point already in the engine.
- The **engine** (`deliberate()` / reactions) picks a valid action from what the arena currently
  affords + the registered schema, and returns it structured.
- The **game/arena executes it** (per the contract: engine returns, game enacts).

Net: **engine core = untouched + agnostic; one new *agnostic* seam; the vocabulary lives in `game/`.**
This refines decision #5 from "engine frozen" to "core frozen + one agnostic seam." The text control
simply doesn't use the seam, so the matched pair stays clean.

---

## 6. Stakes / needs (grounding salience in the body)

The deepest embodiment variable: the agent's **viability is in the world.**

- **Situated stakes:** proximity to threat (the crown's men at the door), an exit blocked, being seen.
- **Bodily needs (optional, powerful):** cold/wet, fatigue, hunger — low-grade drives that *shape what's
  salient* (a fugitive near the door reads the room differently than one warming at the fire).
- These feed the existing salience appraisal (#25): relevance realized relative to embodied stakes, not
  only social/narrative ones. This is where "a body that can lose something" grounds caring.

---

## 7. The engine seam — what changes, what doesn't

| Concern | Text game (control) | Embodied demo (treatment) |
| --- | --- | --- |
| World facts | invented by the DM (prose) | **authoritative arena** |
| `Situation` | DM-written perception | **derived first-person percept** |
| Presence | "all cast always" | **who your vantage affords** |
| Names | scrubbed from prose | **acquaintance state in the world** |
| `world_action` | narrated | **executed against the arena** |
| Stakes for salience | social/narrative | **+ situated/bodily** |
| **The engine (`orchestrator/`)** | — | **UNCHANGED** |

We are not touching the mind. We are giving it a world.

---

## 8. The player

The player is **also a body in the arena** (a position, a vantage). They perceive via the renderer and
act via input that resolves against the arena: `move`, `approach`, `talk`, `take`, `act`. Player
position is authoritative → the spatial-drift bug is gone by construction (you are where the world says
you are, and you only move when you move).

---

## 9. Renderer ladder (the same world model, three skins)

The world model is built **once**; the renderer gets richer in phases. This de-risks everything — each
phase is playable and each is a valid experiment rung.

- **Phase A — text view over the world model.** The "DM" becomes a pure *renderer* of the player's
  percept (narrate only what's in view; never invent). **This alone delivers NPC cognitive embodiment
  and kills the grounding bugs** — the fastest reference point, reuses the existing web UI.
- **Phase B — 2.5D web.** Draw the room: fixtures, character markers/portraits at their positions,
  movement, line-of-sight. Player-side *presence* without a game engine. Still the same arena.
- **Phase C — 3D (Unity/Unreal).** The arena becomes a 3D scene; the same world model drives it. Maximal
  presence + perceptual fidelity. The "full" embodied demo. Biggest cost; purely additive.

---

## 10. Mapping to the #30 experiment

The phases *are* an embodiment-richness gradient, which is exactly the experiment:

- **Control** = the prose text game (world invented by narration).
- **Treatment (min)** = **Phase A** (authoritative world model + enacted loop + situated stakes, text
  view). Isolates *"what does a real, coupled world buy?"* from mere prose.
- **Treatment (rich)** = **Phase B/C** (added continuous space + perceptual fidelity + presence).
  Isolates *"what does richer embodiment/immersion add on top?"*

Same scenario, same cast (the ferry-inn), same engine, same models held constant → the matched-pair the
notebook already specifies. Measures are unchanged (blind RR judge + emergence metrics + blind human
preference, all post-hoc on transcripts). **We can run a real #30 comparison at Phase A — no Unity
required.** (Still Bet 1 only; a sim body isn't autopoietic, so this probes, never proves, Bet 2.)

---

## 11. Rough build milestones

1. **Arena** — the ferry-inn as a world model (zones, positions, objects/affordances, visibility, the
   cast placed in it).
2. **Perception** — derive each agent's first-person percept; feed it as the engine `Situation`. Demote
   the DM to a text renderer of the *player's* percept.
3. **Action/resolver** — map `world_action` → arena effects (approach/take/give/leave/watch); close the
   loop with re-perception. (Fork 5a → 5b as needed.)
4. **Stakes/needs** — situated + light bodily drives feeding salience.
5. **Player embodiment** — position, move, interact; **Phase A playable** end-to-end.
6. **#30 run** — Phase A vs the text control on the same scenario; read the judge + metrics.
7. **Phase B** — 2.5D web renderer over the same arena.
8. **(stretch) Phase C** — Unity/Unreal.

---

## 12. Decisions — SETTLED (review 2026-07-02)

1. **Space model → GRID (tiles), presented as NAMED LOCATIONS.** Grid under the hood (D&D-native,
   procedural-ready); the player only ever sees labelled places ("the hearth"), never coordinates (§3).
2. **Action intent → STRUCTURED, via an agnostic action seam (§5.1).** No prose+resolver — not
   product-grade. Structured actions are the priority; they're what the real product needs and what
   makes "that place isn't reachable from here" true by construction.
3. **Stakes → situated only for now.** Bodily needs (cold/fatigue) deferred — build on the loop later.
4. **First renderer → Phase A (text view) for CHEAP VALIDATION ONLY.** Prove the world-model + structured
   loop kill the grounding bugs; **not** a full play-through. Then move to the visual (a 2D tile map,
   given the grid).
5. **Engine agnosticism preserved (refines "frozen").** Mind (`orchestrator/` core) untouched; add
   exactly ONE new *agnostic* seam — the action seam (§5.1) — same shape as the existing `game_data`
   extension point. Game-specific vocabulary lives in `game/` (e.g. `game/arena/`).
6. **Scenario → reuse the ferry-inn + cast** for the matched pair ("seems very real" bar the known text
   limits). Small AUTHORED map first; procedural later (§14).

---

## 13. Risks & honest limits

- **Scope creep:** an arena/immersive-sim is real engineering; the zone model + minimal action set keep
  it bounded. Don't build a physics engine.
- **Action-resolution fidelity:** parsing prose intent (5a) can be lossy; 5b is the fallback.
- **It still doesn't prove Bet 2.** A simulated body isn't autopoietic; even Phase C *probes* whether the
  enacted loop deepens RR — it can't establish that genuine embodiment is *necessary*.
- **The visual is not the mind.** Phase B/C are presence; if we ever feel "the 3D made it alive," check
  it against Phase A to separate presence from cognition.

---

## 14. Future directions (logged — not now)

- **Procedural dungeons + hand-authored cities (the intended hybrid).** The product design: maps are
  **procedurally generated for dungeon-crawling** and **hand-authored for city / settlement / social
  settings.** This is both a variety win (fresh dungeons every run) *and thesis-protective by
  construction*: the persistent, metamorphosis-carrying NPCs live in the **authored social hubs**
  (cities), where the character depth is, while procedural generation supplies the tactical / exploration
  breadth in dungeons where it's cheap and welcome. Kept OUT of the #30 experiment (randomised maps would
  break the matched pair) — a *product* feature, added once the embodied mind-loop is proven on a fixed
  authored map. The grid foundation is procedural-ready (dungeon generators produce grids).
- **Grid-tactical / open-exploration duality (BG3-style).** A resolution switch on the *same* world
  model: a fine grid for tactical / dungeon play, coarser/open movement for exploration. (BG3 itself is
  hand-authored; the pattern we want is the combat-grid + open-exploration duality.)
- **Thread the needle — metamorphosis *and* D&D.** The thesis lives in social/relational depth; a D&D
  frame adds tactical/exploration. The goal to attempt (not now): procedural *world/dungeons* as the
  stage **+** persistent, embodied, evolving *authored NPCs* carrying the soul — so the campaign has
  both. Flagged to watch that tactical/procedural breadth never buries the character depth we're proving.
- **Action economy (turn budget).** When action becomes tactical (D&D combat especially), agents need an
  **action economy** — a per-turn budget: e.g. D&D's *action + bonus action + movement + reaction* — so a
  turn is a bounded set of choices, not unlimited. Not built now (the social ferry demo is free-form), but
  the **action seam (§5.1) is designed economy-ready**: a structured action can carry a `type`/`cost`
  (action / bonus / move / reaction), and a future turn-manager spends the budget. Leaving room for it now
  so we don't repaint the action schema later.

---

**Bottom line:** build the world model once, demote narration to a view, close the perception→action→
consequence loop with situated stakes, and render it progressively (text → 2.5D → 3D). Phase A gives us
the embodied *mind* — and a real #30 comparison — fast and cheap; the 3D "full demo" becomes an additive
presence layer on the exact same foundation.
