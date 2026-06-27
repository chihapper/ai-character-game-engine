# How memory recall is scored (and how to read the debug panel)

When a character responds, the engine chooses *which past memories to put in front of
the LLM*. It does **not** simply grab the most similar ones — it balances four competing
pressures (an "opponent-processing" model inspired by relevance realization; see
[`architecture-seams.md`](architecture-seams.md) §4). With `MEMORY_DEBUG=true` in `.env`,
the 🧠 panel shows this happening live each turn. Implementation:
[`memory/relevance.py`](../orchestrator/memory/relevance.py).

## The numbers on each row

For every stored memory, scored against the current turn's query:

| Field | Range | Meaning | RR pole |
| --- | --- | --- | --- |
| **sim** | 0–100 | **Semantic similarity** — how close in *meaning* to the query (cosine of embeddings, normalized; ~50 = unrelated, 100 ≈ identical meaning). | focusing / exploit |
| **str** | 0–100 | **Temporal strength** — the recency/"freshness" pole. With a game clock it **decays over in-game time** (half-life stretched by importance + reinforcement — see below); without one, falls back to decay-by-memory-count (half-life ≈ 20). | temporal salience |
| **imp** | 0–100 | **Importance** — the salience stored *with* the memory. Conversation exchanges = **50**; world events from `remember()` default **70** (or whatever you pass). | goal / arena bearing |
| **↺N** | — | **Reinforcement** — times this memory has been *rehearsed* (re-encountered, or recalled when recall-reinforcement is on). Each one stretches the decay half-life. Shown only when N>0; the expanded row also lists its game clock `t`. | temporal salience |
| **base** | ~0–1.85 | The **weighted blend** of sim/str/imp (see formula). The headline score. | — |

The blend (weights are tunable in `.env`):

```
base = w_sim·sim  +  w_rec·str  +  w_imp·imp        (sim/str/imp as 0–1 here)
     =  1.0·sim   +  0.35·str   +  0.5·imp           (defaults)  → max ≈ 1.85
```

This is why a `remember()`'d world event (imp 90) can sit **above** a more semantically
similar piece of chat (higher sim, imp 50): importance + recency outweigh raw similarity.
That's the point — relevance isn't just "what matches."

**Similarity spreading (anisotropy correction).** Real embedders bunch cosine scores into
a narrow band (e.g. 0.72–0.88), so a relevant memory barely outscores noise and recency
drowns it out ([issue #3](https://github.com/chihapper/ai-character-game-engine/issues/3)).
So `sim` is **re-spread within each turn's candidates** before it feeds `base` — the
default `zscore` standardizes the set and squashes it logistically (on-topic memories rise
toward ~1.0, off-topic fall), `minmax` stretches to the full range (aggressive), `none`
disables it. The expanded panel shows both the spread `sim` and the `(raw …)` cosine, so
you can see the correction. Heavier alternatives, if this isn't enough, live at the
embedder layer: whitening/mean-centering the embeddings, or a less-anisotropic model.

## Temporal decay & reinforcement (game-time) — [issue #5](https://github.com/chihapper/ai-character-game-engine/issues/5)

The **str** pole models *forgetting*. When the game supplies a clock, a memory's strength
fades over **in-game time**, not over how many other memories piled on top. The game owns
the clock — a single monotonic number (days, ticks, turns, seconds; the engine never
interprets the unit, only takes a difference), passed as `Situation.clock` (or `t` on
`remember()`). No clock → falls back to decay-by-memory-count, so older saves still work.

```
strength  = 0.5 ^ (Δt / half_life)
half_life = base_half_life · scale^importance · (1 + reinforce_gain · reinforcement)
```

Two things stretch the half-life so a memory resists forgetting:

- **Salience** (`scale^importance`, super-linear): a trivial one-off fades within the base
  half-life; a life-saving moment (importance ≈ .95) lasts dozens of times longer — vivid
  even after in-game years. This is *on top of* importance's undecayed contribution to
  `base`, so a significant memory stays relevant two ways.
- **Reinforcement** (`1 + gain·N`): a fact that's **re-encountered** — or **recalled**, when
  `REINFORCE_ON_RECALL` is on — bumps its count and resets its "last seen", so rehearsal
  keeps it alive. A one-off fades; something the player keeps bringing up persists.

`tools/decay_demo.py` plots the curves; `tools/recall_reinforce_sim.py` simulates a long
game to vet recall-as-reinforcement (it's *selective* — keeps revisited memories vivid
without inflating never-revisited ones).

## How rows get the ★ (selection)

1. **Floor:** memories below `RR_RELEVANCE_FLOOR` are dropped — weak matches are *not*
   forced in (if nothing clears the floor, the single best is kept so a turn is never empty).
2. **Budget:** at most `LONG_TERM_TOP_K` memories are injected (default **4**).
3. **Diversity (the reason ★ order ≠ base order):** selection is greedy, and each pick
   maximizes `base − (diversity penalty)`, where the penalty grows with how similar the
   candidate is to memories *already picked* (weight `RR_WEIGHT_DIVERSITY`). So a high-base
   **near-duplicate can be passed over** for something that adds new information.

**Reading it:** rows are listed **sorted by `base`**, but **★N is the order it was
*picked*** (after the diversity penalty). That's why you'll sometimes see `★3` listed
above `★2`. `★N` = injected into the prompt; `·` = scored but not sent; `⚑` = a
`world_event` (from `remember()`) rather than a conversation exchange. Click any row
(`▸`/`▾`) to expand the full text, exact scores, and `kind`/`when`.

## Persistence (important)

- **Long-term memory lives on disk** at `.memory/<character-slug>.jsonl` and **persists
  across server restarts** — this *is* the cross-session memory feature.
- The **short-term buffer** (recent verbatim turns) resets each session.
- **To wipe a character's long-term memory:** delete its `.memory/<slug>.jsonl` file.

## Tuning

Set in `.env` and restart:

| Variable | Default | Effect |
| --- | --- | --- |
| `RR_WEIGHT_SIMILARITY` | 1.0 | weight of meaning-match |
| `RR_WEIGHT_RECENCY` | 0.35 | weight of freshness |
| `RR_WEIGHT_IMPORTANCE` | 0.5 | weight of stored salience |
| `RR_WEIGHT_DIVERSITY` | 0.4 | strength of the near-duplicate penalty |
| `RR_RECENCY_HALF_LIFE` | 20 | memories-newer before recency halves |
| `RR_RELEVANCE_FLOOR` | 0.15 | min normalized base to be eligible |
| `RR_SIMILARITY_SPREAD` | zscore | anisotropy correction: `zscore` / `minmax` / `none` |
| `RR_SPREAD_GAIN` | 1.5 | zscore steepness — higher = wider spread |
| `RR_DECAY_HALF_LIFE` | 30 | base half-life (importance 0) in the **game's** time units |
| `RR_DECAY_IMPORTANCE_SCALE` | 50 | half-life ×= `scale^importance` (super-linear; significant memories near-permanent) |
| `RR_DECAY_REINFORCE_GAIN` | 1.0 | each reinforcement ×= `(1+gain·N)` the half-life |
| `REINFORCE_ON_RECALL` | off | recalling a memory rehearses it (slows decay); writes the store on each retrieve |
| `LONG_TERM_TOP_K` | 4 | budget: max memories injected per turn |

E.g. raise `RR_WEIGHT_IMPORTANCE` so world events dominate; raise `RR_WEIGHT_DIVERSITY`
to suppress near-duplicates; lower `RR_RELEVANCE_FLOOR` to admit weaker matches.

## Worked examples

All use the default weights (`sim 1.0, str 0.35, imp 0.5`), so `base = sim + 0.35·str +
0.5·imp` (sim/str/imp as 0–1). The **str** column here shows index-recency (no game clock);
with a clock it would be the game-time decay above. Imagine the player asks **"do you
remember my brother?"** and these candidates are scored:

| memory | sim | str | imp | base | outcome |
| --- | --- | --- | --- | --- | --- |
| "…my brother disappeared in the mines" (old) | .81 | .35 | .50 | **1.18** | ❌ not injected |
| "Hey" (generic, very recent) | .77 | .97 | .50 | **1.36** | ✅ injected |
| `remember()`: "player saved Bri from the fire" | .74 | .90 | **.95** | **1.53** | ✅ injected |
| duplicate of the above | .74 | .88 | .95 | 1.51 | ⚠️ dropped by diversity |
| "what's a good drink?" (unrelated, old) | .58 | .20 | .50 | 0.90 | ❌ below interest |

What each row teaches:
- **Row 1 vs 2 — the recency trap.** A content-free "Hey" *outscores* the brother memory
  purely on recency (`.97` vs `.35`), because `sim` barely separates them (`.77` vs `.81`).
  This is exactly [issue #3](https://github.com/chihapper/ai-character-game-engine/issues/3):
  when similarity doesn't discriminate, recency wins and buries old-but-important memories.
- **Row 3 — importance rescues relevance.** The fire event isn't the most *similar*, but
  its high `imp` (.95, from `remember()`) lifts `base` above everything — a flagged event
  stays salient. (Imagine, instead, *character-aware* importance doing this automatically
  for the brother memory — the unbuilt salience fix.)
- **Row 4 — diversity.** Identical to row 3; after row 3 is picked, the duplicate's score
  is docked ~`0.4 × (its similarity to row 3)`, so it's passed over — no double-injection.
- **Row 5 — relevance floor.** Low on every axis; falls below the eligibility floor and is
  dropped rather than padding the budget.

Net intuition: **`sim` finds what's on-topic, `rec` favors what's fresh, `imp` protects
what matters — and they fight.** Tune the weights to change who wins that fight.

## Built since, and queued work

- **Done:** [#3](https://github.com/chihapper/ai-character-game-engine/issues/3) high-spread
  similarity + **character-aware salience** (an LLM rates how memorable an exchange is *to
  this character* at write time); **write-time dedup** (re-encounters now *reinforce* instead
  of double-injecting); **arena query** (recall is searched against the trigger + recent turns
  + live `Situation` + goals, not just the last line); and **[#5](https://github.com/chihapper/ai-character-game-engine/issues/5)
  temporal decay + reinforcement** (above).
- **Queued next — [#4](https://github.com/chihapper/ai-character-game-engine/issues/4)
  long-range commitment tracking:** promises/constraints a character makes ("I'll meet you at
  dawn") currently fall out of context once past the short-term buffer. They need to be held
  as durable, surfaced commitments rather than ordinary decaying memories.

> This is a deliberate *approximation* of relevance realization (Vervaeke et al.) for an
> authored-goal NPC — the LLM remains the real relevance realizer over its context; this
> scorer shapes what enters that context.
