# Unity gray-box client — architecture (#35 / #38)

> **Status (2026-11-07):** Frozen history, not active work. The Unity client was last changed on
> 2026-07-02 (`7c15d40`, tag `archive/sandbox`), the day the project moved its demo client to Unreal
> ([unreal-port.md](unreal-port.md)). The Godot client on `game-rpg` came after that. Unity has not
> been run since 2026-07-05. A static read on 2026-11-07 shows its API calls still match the mind
> server, but no test covers that. It can't be rebuilt from this repo alone, because the repo holds
> scripts, not a Unity project. For the current picture, read
> [project-status.md](project-status.md), which also triages issues #35 to #39. All five are still
> open on GitHub.

> Original status (2026-07-02): **v0 skeleton landed** (`2451cc7`). Companions: [engine-game-contract.md](engine-game-contract.md)
> (the seam law), [embodied-demo-architecture.md](embodied-demo-architecture.md) (Phase A / grid),
> [embodiment-experiment.md](embodiment-experiment.md) (#30 protocol). Issues: #35 (track), #36
> (cadence), #37 (API hardening), #38 (perception adapter), #39 (protocol update).

## The one-sentence design

**Unity's scene is the authoritative world; the Python orchestrator is the mind server** — Unity
composes each NPC's first-person percept from real raycasts and sends it over HTTP; the engine
core is untouched (the whole point of the seam).

## Split of responsibilities (per the contract)

| concern | owner |
| --- | --- |
| positions, line of sight, gaze, hearing, collisions, time flow | **Unity** (the WORLD) |
| memory, salience appraisal, relationship, intent, goals, deliberation, replies | **Python** (the MIND) |
| react policy (thresholds, magnitudes) + name/acquaintance policy | **`game/policy.py`** — one module, shared by the grid arena and the bridge, so the two treatment arms can never drift apart |
| composing percepts into `Situation` text | Unity (client-side `PerceptComposer`) — the bridge passes it through `Situation.from_dict` untouched |
| enacting chosen actions (movement, animation) | Unity (`choose_action` returns a label; the game executes) |

## The wire (v0 — deliberately boring: JSON over the existing FastAPI server, port 8001)

All DTOs are flat/array-shaped so Unity's built-in `JsonUtility` handles them (no package deps).

- `POST /api/mind/session` `{scenario?, reply_model?}` →
  `{session_id, player_handle, react_at, speak_at, cast:[{slug, handle, here_because}]}`
  One live session per process (shared memory namespaces — same rule as the grid arena);
  creating a session finalizes the previous one.
- `POST /api/mind/{sid}/{slug}/respond` `{line?, event?, situation:{location, present[], clock, performance?}}`
  → `{reply, name_spoken}` — `line` is framed as spoken address by the engine; `event` is unframed.
  `name_spoken` = a first-name/nickname the character just said aloud (quoted speech only), so the
  client can reveal a nameplate the moment an introduction actually happens.
- `POST /api/mind/{sid}/{slug}/choose` `{situation, options[]}` → `{action, reason}` —
  options are the client's afforded-action labels; the engine picks grounded in evolved state.
- `POST /api/mind/{sid}/observe` `{clock, magnitude, items:[{slug, observed}]}` →
  `{results:[{slug, salience, react}]}` — the react RECIPE's server half: each listed witness
  `remember()`s its own first-person observation (appraised salience, #25 magnitude hint), and the
  shared policy maps salience → `"speak" | "act" | ""`. The client then calls respond/choose for
  the reactors. Unity decides WHO witnessed (LoS/earshot — free from the scene).
- `POST /api/mind/{sid}/finish` → flushes background reflection, closes the experiment-log row.

Known v0 limits (tracked in #36/#37): blocking POSTs (no streaming), no idempotency keys, one
session per process, cadence is client-side timers rather than a designed real-time model.

**Changed since v0.** [`game/bridge/mind_api.py`](../game/bridge/mind_api.py) is the source of
truth. Checked against it on 2026-11-07:

- `/session` also returns `title` and `voice`.
- `situation` also takes `ambient`, and `/respond` also returns `face_marks`.
- `/choose` also returns `expression` and `face`.
- `/observe` results also carry `flinch`.
- `/finish` takes `{outcome}` and returns `{ok, run_id}`.
- New `POST` routes: `/{sid}/{slug}/acted`, `/{sid}/{slug}/speak`, `/{sid}/{slug}/speak_anim`,
  `/{sid}/{slug}/speak_multi`, and `/{sid}/stt`. There is also `GET /bakeoff`.
- **Side effect:** creating a session deletes the cast's `.memory/` files, including
  `corvin-ashgrave-inworld`, the credibility demo's default mind.

## Unity side (`unity/Assets/Scripts/` — copy into any empty Unity 6 3D project)

Everything is **runtime-generated** — no scene authoring, no prefabs, no packages. An empty scene
plus these scripts is the whole game: `Bootstrap` self-spawns via `RuntimeInitializeOnLoadMethod`.

| script | job |
| --- | --- |
| `Bootstrap.cs` | builds the gray-box ferry inn (floor/walls/bar/hearth/tables as primitives), named region anchors, spawns player + NPC capsules, starts the session |
| `MindClient.cs` | the HTTP seam — session/respond/choose/observe/finish, JsonUtility DTOs |
| `PerceptComposer.cs` | **the #38 adapter**: raycast line-of-sight + facing cone + distance tiers → the same present-strings the grid produced, now earned from real space |
| `NpcAgent.cs` | per-NPC life: idle cadence → percept → choose → enact (walk to anchor / watch / stay); reaction beats when `observe` says so |
| `PlayerController.cs` | WASD + mouse look, E to talk to who you're facing |
| `DialogueUI.cs` | minimal IMGUI dialogue box (no UI packages) |
| `WorldClock` (a static class in `Bootstrap.cs`) | real seconds → game hours (the game owns the clock, engine only differences it) |

Added after v0: `CharacterRig.cs` (the procedural figures that replaced plain capsules),
`Flicker.cs`, `Nameplate.cs`, `StormAudio.cs`, and `StoryDirector.cs`. The fuller client in
`unity/pro/` (22 scripts, 8 editor tools) has no design doc of its own;
[unity/README.md](../unity/README.md) says what it is.

## What this buys the experiment (#30 / #39)

The percept channels the grid could never produce, each now a real input to the same mind:
**occlusion** (Corvin genuinely can't see through the bar), **gaze** ("the stranger is looking at
you" is geometry, not narration), **earshot** (overhearing is physics — dissolves the old #34
problem), **real time** (hesitation and interruption are measurable). TREAT-EMBODIED-3D runs the
same cast + scenario as CTRL-TEXT; run logging stays in the mind server.

## Milestones

This was the plan on 2026-07-02. v0 landed in `2451cc7`. v1 and v2 were not carried out: the cadence
design (#36) never landed, and although 131 `TREAT-EMBODIED-3D` runs were logged through 2026-07-05,
none was blind-judged. The `rr_judge` column is blank on all of them in
[embodiment-experiment.md](embodiment-experiment.md).

1. **v0 (this commit)**: bridge + skeleton; player walks the inn, talks to Della, NPCs idle via
   `choose`, observed acts trigger the react recipe through real LoS.
2. **v1**: cadence design lands (#36) — percept staleness, interruption, call budget.
3. **v2**: protocol update (#39) + first logged TREAT-EMBODIED-3D runs, blind-judged against CTRL.
