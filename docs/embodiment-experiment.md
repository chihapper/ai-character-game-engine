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
<!-- RUNS_TABLE_END -->
