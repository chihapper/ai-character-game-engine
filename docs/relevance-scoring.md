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
| `LONG_TERM_TOP_K` | 4 | budget: max memories injected per turn |

E.g. raise `RR_WEIGHT_IMPORTANCE` so world events dominate; raise `RR_WEIGHT_DIVERSITY`
to suppress near-duplicates; lower `RR_RELEVANCE_FLOOR` to admit weaker matches.

> This is a deliberate *approximation* of relevance realization (Vervaeke et al.) for an
> authored-goal NPC — the LLM remains the real relevance realizer over its context; this
> scorer shapes what enters that context.
