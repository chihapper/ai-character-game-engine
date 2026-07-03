# Embodiment experiment — lab notebook

> **Tracks [issue #30](https://github.com/chihapper/ai-character-game-engine/issues/30)** (Embodiment
> frontier / Bet 1). The **protocol** below is static. The **RUNS** section at the bottom is
> **auto-appended by the game runtime** when a playthrough starts (one row per run), and the metric
> columns are filled in **post-hoc** after evaluation. This file is the durable record of the
> experiment — do not delete rows.

---

## Hypothesis (Bet 1)

The *same* NPC mind (same engine, same character definition, same scenario) exhibits **measurably more
emergent, grounded, lifelike relevance realization** when its cognition is **embodied** — first-person
perception in, action out, consequences it must re-perceive, situated stakes — than when it is driven
purely by a **described-text** situation.

## What this is NOT

- **Not a proof of the necessity thesis (Bet 2).** A simulated / Unity body is not autopoietic, so its
  stakes are simulated. This experiment **probes** whether the *functional* enacted loop matters and is
  replicable; it cannot *prove* that genuine embodiment is metaphysically required. A positive result
  is evidence the loop matters; a plateau is *consistent with* (not proof of) the strong thesis.
- The realizer (the LLM) already carries **inherited / offline** embodiment (trained on embodied
  humans' language). The isolated variable is the **online, first-person, closed-loop** enaction a body
  adds on top of that — *does live enacted coupling add what inherited coupling can't?*

## Conditions (matched pair + a middle control)

| id | condition | perception | action | stakes |
| --- | --- | --- | --- | --- |
| `CTRL-TEXT` | text (the first game, #26) | described `Situation` | `world_action` narrated | social / narrative |
| `MID-RICHTEXT` | rich text | **same content** the embodied NPC would perceive, delivered as text | narrated | social / narrative |
| `TREAT-EMBODIED` | embodied | enacted first-person perception | enacted, consequences re-perceived | situated / bodily |

**Isolated variable:** the enacted closed perception→action→consequence loop + situated stakes —
**NOT** information volume. The `MID-RICHTEXT` arm exists to separate "richer perception" from "the
enacted consequence/stakes loop": if it captures most of the gain, the win was information; if
`TREAT-EMBODIED` pulls clearly ahead of it, that gap is the embodiment signal.

## Measures (ALL post-hoc on recorded transcripts — near-zero live cost)

1. **RR judge** (Opus, **blind** to condition) — grounding / emergence / in-character / coherence.
   Runs **offline on the saved transcript**, on a sample of runs; never during play.
2. **Behavioral emergence metrics** — computed from recorded state: unscripted actions,
   goal-evolution events, salience divergence, decisions not derivable from the prompt.
3. **Blind human preference** — logged by the human ("which felt more alive/agentive"), condition hidden.
4. **Coherence guard** — added emergence must not cost legibility (the thesis's bar).

## Controls & honest caveats

- **Matching rule:** a single source of truth = the scene state, rendered to text (control) or to
  enaction (treatment) — same information across conditions.
- **Perfect text/embodied parity is impossible** (text omits pre-reflective/peripheral cues); the
  residual is itself part of the signal, not a flaw.
- **A positive result is evidence, not proof** (see "What this is NOT").
- Judge and human eval are **blind**; runs are **sampled** to control cost.

## Field observations (things text costs that embodiment gives free)

A running list of concrete places where the *text medium* forces a workaround that an *embodied* build
would resolve natively — each one a small qualitative data point for the frontier.

- **Addressing / reference resolution.** In text, "who is this remark aimed at?" must be *inferred* by
  the DM from prose (`game/dm.py::pick_responders`). Under embodiment it's given by the body — gaze,
  orientation, proximity, who you turned toward. Addressing is a chore in text and free when embodied.
- **Spatial position / grounding (a big one).** The stateless text DM kept *re-inventing* where the
  player was (at the bar → "survey the room" → suddenly at the door), because prose has no persistent
  place. The fix is to have the game hold authoritative state (`Game.player_location`) and feed it to
  the DM every call, which may only move the player on explicit movement (`game/runtime.py`,
  `game/dm.py`). Under embodiment this is **free**: a body simply *is* somewhere; position, facing,
  proximity, and "you didn't move" are carried by the world, not tracked in a variable and re-narrated
  each turn. Spatial coherence is the clearest case so far of what the text medium fights and an
  embodied arena gives for nothing.
- **Name-discovery.** Text has to explicitly track which names the player has learned and swap
  handle↔name (`Game.known_names`); embodiment carries "you've been introduced / you recognize this
  face" as part of perceiving the person. The OVERHEARING case sharpens this (user-surfaced): when a
  third party speaks a name ("Corvin, another round?"), the listener still has to BIND the name to the
  right face. In text that binding is either a heuristic (only situationally consistent — fine at a
  cast of four, wrong with two plausible Corvins or a name spoken about someone absent) or a per-mention
  LLM judgment. A heuristic fix was tried and REVERTED (76b9ddf → #34, much later): a visual game
  dissolves the problem — the player sees who the speaker looked at and who answered, and what remains
  is nameplate-reveal polish, not cognition. Strongest single example yet of a whole bug CLASS that
  exists only because the surface is text.
- **Action grounded in backstory, not the scene.** Playtest: Corvin's `world_action` had him slip down
  an "alley" to his fence "Mother Sael's" while *stuck in the inn* — he acted in his imagined
  backstory-world, not the actual constrained place, because the engine has no world to be bounded by.
  Structured actions **chosen from the arena's affordances** (you can only do what THIS place allows)
  fix it by construction — "go to Mother Sael's" isn't an option that exists here.
- **Temporal grounding.** Playtest: after "the night moves on," an NPC replied as if no time had passed
  ("a few moments ago…" across a time-skip). Text has no *felt* clock; an embodied arena carries elapsed
  time as world state the character perceives, so "hours passed" is part of the percept, not a variable
  to re-narrate.

## Run parameters (what defines a run)

`scenario` · `condition` (id above) · `character set` · `models` (reply / deliberation / bookkeeping /
judge) · `engine flags` · `seed/notes` · `transcript path`.

---

## RUNS

> Auto-appended by the game runtime on playthrough start (run-start row). Metric columns
> (`rr_judge`, `emergence`, `human_note`) are filled in post-hoc after evaluation. Newest at the bottom.

<!-- RUNS_TABLE_START -->
| run_id | started | condition | scenario | characters | models | transcript | outcome | rr_judge | emergence | human_note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CTRL-TEXT-20260701-002425-233 | 2026-07-01 00:24:25 | CTRL-TEXT | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 dm=claude-haiku-4-5 book=claude-sonnet-4-6 | .game_runs\CTRL-TEXT-20260701-002425-233.jsonl | (in progress) | — | — | — |
| CTRL-TEXT-20260701-003101-6d4 | 2026-07-01 00:31:01 | CTRL-TEXT | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 dm=claude-haiku-4-5 book=claude-sonnet-4-6 | .game_runs\CTRL-TEXT-20260701-003101-6d4.jsonl | (in progress) | — | — | — |
| CTRL-TEXT-20260701-003450-24f | 2026-07-01 00:34:50 | CTRL-TEXT | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 dm=default book=claude-sonnet-4-6 | .game_runs\CTRL-TEXT-20260701-003450-24f.jsonl | (in progress) | — | — | — |
| CTRL-TEXT-20260701-003506-ce7 | 2026-07-01 00:35:06 | CTRL-TEXT | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 dm=default book=claude-sonnet-4-6 | .game_runs\CTRL-TEXT-20260701-003506-ce7.jsonl | (in progress) | — | — | — |
| CTRL-TEXT-20260701-005803-c95 | 2026-07-01 00:58:03 | CTRL-TEXT | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 dm=default book=claude-sonnet-4-6 | .game_runs\CTRL-TEXT-20260701-005803-c95.jsonl | (in progress) | — | — | — |
| CTRL-TEXT-20260701-012235-983 | 2026-07-01 01:22:35 | CTRL-TEXT | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 dm=default book=claude-sonnet-4-6 | .game_runs\CTRL-TEXT-20260701-012235-983.jsonl | (in progress) | — | — | — |
| CTRL-TEXT-20260701-013117-969 | 2026-07-01 01:31:17 | CTRL-TEXT | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 dm=default book=claude-sonnet-4-6 | .game_runs\CTRL-TEXT-20260701-013117-969.jsonl | (in progress) | — | — | — |
| CTRL-TEXT-20260701-015118-c72 | 2026-07-01 01:51:18 | CTRL-TEXT | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 dm=default book=claude-sonnet-4-6 | .game_runs\CTRL-TEXT-20260701-015118-c72.jsonl | (in progress) | — | — | — |
| CTRL-TEXT-20260701-111631-cee | 2026-07-01 11:16:31 | CTRL-TEXT | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 dm=default book=claude-sonnet-4-6 | .game_runs\CTRL-TEXT-20260701-111631-cee.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-20260701-151407-371 | 2026-07-01 15:14:07 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | .game_runs\TREAT-EMBODIED-20260701-151407-371.jsonl | (in progress) | — | — | — |
| CTRL-TEXT-20260701-153347-7a0 | 2026-07-01 15:33:47 | CTRL-TEXT | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 dm=default book=claude-sonnet-4-6 | .game_runs\CTRL-TEXT-20260701-153347-7a0.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-20260701-153633-3f0 | 2026-07-01 15:36:33 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-sonnet-4-6 book=claude-sonnet-4-6 | .game_runs\TREAT-EMBODIED-20260701-153633-3f0.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-20260701-162711-e57 | 2026-07-01 16:27:11 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | .game_runs\TREAT-EMBODIED-20260701-162711-e57.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-20260701-163342-400 | 2026-07-01 16:33:42 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | .game_runs\TREAT-EMBODIED-20260701-163342-400.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-20260701-181055-c9b | 2026-07-01 18:10:55 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | C:\Users\Alejandro\claude-sandbox\ai-character-game-engine\.game_runs\TREAT-EMBODIED-20260701-181055-c9b.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-20260701-181130-8f7 | 2026-07-01 18:11:30 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | C:\Users\Alejandro\claude-sandbox\ai-character-game-engine\.game_runs\TREAT-EMBODIED-20260701-181130-8f7.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-20260701-204011-714 | 2026-07-01 20:40:11 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | C:\Users\Alejandro\claude-sandbox\ai-character-game-engine\.game_runs\TREAT-EMBODIED-20260701-204011-714.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-20260701-204415-635 | 2026-07-01 20:44:15 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | C:\Users\Alejandro\claude-sandbox\ai-character-game-engine\.game_runs\TREAT-EMBODIED-20260701-204415-635.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-20260701-210131-015 | 2026-07-01 21:01:31 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | C:\Users\Alejandro\claude-sandbox\ai-character-game-engine\.game_runs\TREAT-EMBODIED-20260701-210131-015.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-20260701-212713-d5c | 2026-07-01 21:27:13 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | C:\Users\Alejandro\claude-sandbox\ai-character-game-engine\.game_runs\TREAT-EMBODIED-20260701-212713-d5c.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-20260701-215437-916 | 2026-07-01 21:54:37 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | C:\Users\Alejandro\claude-sandbox\ai-character-game-engine\.game_runs\TREAT-EMBODIED-20260701-215437-916.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-20260701-233948-2a4 | 2026-07-01 23:39:48 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | C:\Users\Alejandro\claude-sandbox\ai-character-game-engine\.game_runs\TREAT-EMBODIED-20260701-233948-2a4.jsonl | (superseded by a new run) | — | — | — |
| TREAT-EMBODIED-20260701-234115-288 | 2026-07-01 23:41:15 | TREAT-EMBODIED | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-sonnet-4-6 book=claude-sonnet-4-6 | C:\Users\Alejandro\claude-sandbox\ai-character-game-engine\.game_runs\TREAT-EMBODIED-20260701-234115-288.jsonl | (in progress) | — | — | — |
| TREAT-EMBODIED-3D-20260702-001011-853 | 2026-07-02 00:10:11 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (bridge smoke test) | — | — | — |
| TREAT-EMBODIED-3D-20260702-003238-574 | 2026-07-02 00:32:38 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-003514-92b | 2026-07-02 00:35:14 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-003857-d41 | 2026-07-02 00:38:57 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-003920-d96 | 2026-07-02 00:39:20 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-004150-7aa | 2026-07-02 00:41:50 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-004432-25b | 2026-07-02 00:44:32 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-005404-3a3 | 2026-07-02 00:54:04 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-005956-c8e | 2026-07-02 00:59:56 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (in progress) | — | — | UNPROMPTED APPROACH: Bri crossed the room to the player on her own idle beat, unscripted (first live emergence datum on the 3D arm) |
| TREAT-EMBODIED-3D-20260702-011435-d38 | 2026-07-02 01:14:35 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (in progress) | — | — | — |
| TREAT-EMBODIED-3D-20260702-114122-79f | 2026-07-02 11:41:22 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (voice smoke) | — | — | — |
| TREAT-EMBODIED-3D-20260702-124434-80d | 2026-07-02 12:44:34 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (inworld voice smoke) | — | — | — |
| TREAT-EMBODIED-3D-20260702-124557-7b1 | 2026-07-02 12:45:57 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (inworld voice smoke 2) | — | — | — |
| TREAT-EMBODIED-3D-20260702-135936-942 | 2026-07-02 13:59:36 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-140047-d24 | 2026-07-02 14:00:47 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-140139-678 | 2026-07-02 14:01:39 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-143917-87d | 2026-07-02 14:39:17 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-144646-447 | 2026-07-02 14:46:46 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-145830-e87 | 2026-07-02 14:58:30 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-150450-b76 | 2026-07-02 15:04:50 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-151628-292 | 2026-07-02 15:16:28 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-152037-51e | 2026-07-02 15:20:37 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-153837-e46 | 2026-07-02 15:38:37 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-154433-41b | 2026-07-02 15:44:33 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-154713-fa7 | 2026-07-02 15:47:13 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-154934-7a0 | 2026-07-02 15:49:34 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-155158-c73 | 2026-07-02 15:51:58 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-155337-4a6 | 2026-07-02 15:53:37 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-155707-56a | 2026-07-02 15:57:07 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-155925-721 | 2026-07-02 15:59:25 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-160524-038 | 2026-07-02 16:05:24 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-161644-c1e | 2026-07-02 16:16:44 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-163515-156 | 2026-07-02 16:35:15 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-163640-344 | 2026-07-02 16:36:40 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-163902-4d8 | 2026-07-02 16:39:02 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-164512-964 | 2026-07-02 16:45:12 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-164851-c89 | 2026-07-02 16:48:51 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-165314-df9 | 2026-07-02 16:53:14 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-165438-412 | 2026-07-02 16:54:38 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-172219-cb9 | 2026-07-02 17:22:19 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-183351-e34 | 2026-07-02 18:33:51 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-191205-a21 | 2026-07-02 19:12:05 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-194131-620 | 2026-07-02 19:41:31 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-205355-914 | 2026-07-02 20:53:55 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-205526-152 | 2026-07-02 20:55:26 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-215422-86d | 2026-07-02 21:54:22 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-215641-0af | 2026-07-02 21:56:41 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-220723-4d7 | 2026-07-02 22:07:23 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (superseded by a new session) | — | — | — |
| TREAT-EMBODIED-3D-20260702-221234-8a1 | 2026-07-02 22:12:34 | TREAT-EMBODIED-3D | ferry-crossing | della-fenwick, brielle-bri-castellano, edwin-hale, corvin-ashgrave-inworld | reply=claude-haiku-4-5 book=claude-sonnet-4-6 | — | (in progress) | — | — | — |
<!-- RUNS_TABLE_END -->
