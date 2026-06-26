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
| **rec** | 0–100 | **Recency** — how recently it was stored; decays as newer memories pile on (half-life ≈ 20 memories). | temporal salience |
| **imp** | 0–100 | **Importance** — the salience stored *with* the memory. Conversation exchanges = **50**; world events from `remember()` default **70** (or whatever you pass). | goal / arena bearing |
| **base** | ~0–1.85 | The **weighted blend** of the three (see formula). The headline score. | — |

The blend (weights are tunable in `.env`):

```
base = w_sim·sim  +  w_rec·rec  +  w_imp·imp        (sim/rec/imp as 0–1 here)
     =  1.0·sim   +  0.35·rec   +  0.5·imp           (defaults)  → max ≈ 1.85
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
| `LONG_TERM_TOP_K` | 4 | budget: max memories injected per turn |

E.g. raise `RR_WEIGHT_IMPORTANCE` so world events dominate; raise `RR_WEIGHT_DIVERSITY`
to suppress near-duplicates; lower `RR_RELEVANCE_FLOOR` to admit weaker matches.

## Worked examples

All use the default weights (`sim 1.0, rec 0.35, imp 0.5`), so `base = sim + 0.35·rec +
0.5·imp` (sim/rec/imp as 0–1). Imagine the player asks **"do you remember my brother?"**
and these candidates are scored:

| memory | sim | rec | imp | base | outcome |
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

## Known limitation & queued work

- **[issue #3](https://github.com/chihapper/ai-character-game-engine/issues/3) (current focus):**
  important memories get buried by recency because (a) the embedder's similarities cluster
  too tightly and (b) `importance` is flat / not character-aware. Fixes: higher-spread
  similarity + character-aware salience at write time.
- **Queued next (after #3):**
  - **Write-time dedup** — skip storing identical facts and collapse near-duplicates (you
    can fire `remember()` twice today and both copies get injected).
  - **Arena query** — fold the live `Situation` + the character's goals into the *retrieval
    query*, so recall is searched against the whole scene, not just the last line
    (issue #2 / [`architecture-seams.md`](architecture-seams.md) §6 Track E step 4).

> This is a deliberate *approximation* of relevance realization (Vervaeke et al.) for an
> authored-goal NPC — the LLM remains the real relevance realizer over its context; this
> scorer shapes what enters that context.
