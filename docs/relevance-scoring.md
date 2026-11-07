# How memory recall is scored (and how to read the debug panel)

When a character responds, the engine chooses *which past memories to put in front of
the LLM*. It does **not** simply grab the most similar ones — it balances four competing
pressures (an "opponent-processing" model inspired by relevance realization; see
[`architecture-seams.md`](architecture-seams.md) §4). With `MEMORY_DEBUG=true` in `.env`,
the 🧠 panel in the port 8000 Conversation app shows this happening live each turn.
Implementation: [`memory/relevance.py`](../orchestrator/memory/relevance.py).

Recall itself runs on every surface. The sections below on commitments and relationship state
describe the `Engine`, which the Conversation app doesn't use; see
[`engine-overview.md`](engine-overview.md).

## The numbers on each row

For every stored memory, scored against the current turn's query:

| Field | Range | Meaning | RR pole |
| --- | --- | --- | --- |
| **sim** | 0–100 | **Semantic similarity** — how close in *meaning* to the query. The cosine of the embeddings is normalized, then re-spread across this turn's candidates (see below), so ~50 means "average for this turn", not "unrelated". The expanded row also shows the raw value. | focusing / exploit |
| **str** | 0–100 | **Temporal strength** — the recency/"freshness" pole. With a game clock it **decays over in-game time** (half-life stretched by importance + reinforcement — see below); without one, falls back to decay-by-memory-count (half-life ≈ 20). | temporal salience |
| **imp** | 0–100 | **Importance** — the salience stored *with* the memory. By default **the character appraises it**: an LLM rates how memorable each exchange is to them, and does the same for an `Engine.remember()` event unless you pin a number. **50** is the fallback when scoring fails or is off on `Pipeline`; with scoring off, an unpinned `Engine.remember()` stores **70**. A pinned number is used as given, and the WebSocket `remember` on port 8000 pins **70** unless you send one. Beliefs and self-change store at 85, decisions and contradictions at 80. | goal / arena bearing |
| **↺N** | — | **Reinforcement** — times this memory has been *rehearsed* (re-encountered, or recalled when recall-reinforcement is on). Each one stretches the decay half-life, with diminishing returns. Shown only when N>0; the expanded row also lists its game clock `t`. | temporal salience |
| **base** | ~0–2.05 | The **weighted blend** of sim/str/imp (see formula). The headline score. | — |

The blend (weights are tunable in `.env`):

```
base = w_sim·sim  +  w_rec·str  +  w_imp·imp        (sim/str/imp as 0–1 here)
     =  1.0·sim   +  0.35·str   +  0.7·imp           (defaults)  → max = 2.05
```

This is why a `remember()`'d world event (imp 90) can sit **above** a more semantically
similar piece of chat (higher sim, lower imp): importance + recency outweigh raw similarity.
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
half_life = base_half_life · scale^importance · (1 + cap·boost / (cap + boost))
boost     = reinforce_gain · reinforcement
```

Two things stretch the half-life so a memory resists forgetting:

- **Salience** (`scale^importance`, super-linear): a trivial one-off fades within the base
  half-life; a life-saving moment (importance ≈ .95) lasts dozens of times longer — vivid
  even after in-game years. This is *on top of* importance's undecayed contribution to
  `base`, so a significant memory stays relevant two ways.
- **Reinforcement** (about `1 + gain·N` for small N, then saturating): a fact that's
  **re-encountered** — or **recalled**, when `REINFORCE_ON_RECALL` is on — bumps its count and
  resets its "last seen", so rehearsal keeps it alive. A one-off fades; something the player
  keeps bringing up persists. At defaults, one reinforcement stretches the half-life 1.92×,
  twelve stretch it 7×, and the ceiling is 13×, so endless recall can't make a memory permanent.

`tools/decay_demo.py` prints the curves as a table; `tools/recall_reinforce_sim.py` simulates
a long game to vet recall-as-reinforcement (it's *selective* — keeps revisited memories vivid
without inflating never-revisited ones).

## Commitments — always-injected obligations — [issue #4](https://github.com/chihapper/ai-character-game-engine/issues/4)

A **commitment** — a promise, deal, or constraint ("meet at dawn", "never tell anyone the
player's name") — is a *standing concern*, not a scored recollection. While **open** it's
injected **every turn** (a `# Open commitments you've made` section), so it never falls out of
context or competes in the relevance top-k, and it does **not** decay. The game owns it via
the `Engine.commit()` / `resolve_commitment()` methods (siblings of `remember`). The 🧠 panel's
amber banner of open commitments appears only on the unadopted full loop
(`VOICE_RUNTIME=inworld_fullloop`), which is also the only place `commit` and
`resolve_commitment` exist as WebSocket messages.

When a commitment **closes** — the game marks it fulfilled/broken, or it **expires** past its
due clock — it converts into an ordinary (decaying) memory of the outcome, inheriting the
commitment's **significance** to the NPC (an unkept promise stings a little more). So a
high-stakes betrayal (letting someone go to debtor's prison) stays vivid for in-game years
via the super-linear decay above, while a trivial broken promise fades; a constraint with no
deadline never lapses on its own. `tools/commitment_scenarios.py` sweeps the full lifecycle
across timetables.

Commitments are created two ways: the game declares them (`commit`), or — with
`COMMITMENT_DETECTION` on — the engine **detects** one the character makes in dialogue ("I'll
meet you at dawn"), folded into the per-turn judgment call so it costs no extra
round-trip. Detection is conservative (hedges/pleasantries/player-side promises don't count)
and opt-in, since it's fuzzier than the game API. It's off on this branch's game surfaces unless set in
`.env`; on `game-rpg`, the Godot RPG forces it on.

## Relationship state — feelings that evolve and condition recall — [issue #6](https://github.com/chihapper/ai-character-game-engine/issues/6)

A character's stance toward the player starts from their static `disposition` and then SHIFTS
with the interaction: **affection / trust / respect** as movement from a 0.5 baseline, plus an
acute **mood**. Updated by the **same folded per-turn judgment call** (one round-trip) and
CHARACTER-AWARE: most exchanges move nothing; pleasantries roll off a guarded character (water
off a duck's back), while genuine, proven, or costly acts move them slowly; a warm character
moves more readily. `RELATIONSHIP_STATE` defaults off, but every game surface and the Director's
Sandbox force it on in code. It has no effect on the port 8000 Conversation app.

It's **RR-core, not a tone sticker**: on `Engine` paths the current stance folds into the
**arena query**, so *recall itself* is relationship-conditioned — a wary character surfaces
deception/threat memories, a fond one surfaces warmth (relevance relative to the agent's
caring). The behavioral payoff is real — at low trust a character deflects and guards; at high
trust they engage and help, in character. The 🧠 panel's axes (▲/▼ = moved from baseline) and
mood appear only on the unadopted full loop. To inspect relationship state, use the Director's
Sandbox at `/sandbox`.

Disposition also shifts outside conversation
([#12](https://github.com/chihapper/ai-character-game-engine/issues/12)).
`Engine.remember(fact, player_role="caused" | "benefited")` has the AI judge a **world event's**
impact on the character's feelings, even an indirect one (the player's faction burns the NPC's
warehouse), and `actor="self"` covers the character's own change of heart. Feelings also **drift
toward baseline over in-game time**: `RelationshipState.age()` runs lazily on next contact, at an
AI-assessed per-character rate that deep bonds resist, and a scar holds the line. The state
persists on disk, so each conversation starts where the last one left off.

## How rows get the ★ (selection)

1. **Floor:** a memory is eligible only if `base` reaches `RR_RELEVANCE_FLOOR` times the
   maximum possible base, which is 0.15 × 2.05 = 0.3075 at defaults. Weak matches are *not*
   forced in (if nothing clears the floor, the single best is kept so a turn is never empty).
2. **Budget:** at most `LONG_TERM_TOP_K` memories are injected (default **6**, raised from 4
   after the stress test showed a defining memory getting edged out at long range).
3. **Diversity (the reason ★ order ≠ base order):** selection is greedy, and each pick
   maximizes `base − (diversity penalty)`, where the penalty grows with how similar the
   candidate is to memories *already picked* (weight `RR_WEIGHT_DIVERSITY`). The penalty only
   drops anything once the budget runs out: with fewer eligible memories than the budget, every
   one is injected and diversity just reorders them. When the budget does bind, a high-base
   **near-duplicate can be passed over** for something that adds new information.

**Reading it:** rows are listed **sorted by `base`**, but **★N is the order it was
*picked*** (after the diversity penalty). That's why you'll sometimes see `★3` listed
above `★2`. `★N` = injected into the prompt; `·` = scored but not sent; `⚑` = a
`world_event` (from `remember()`) rather than a conversation exchange. Click any row
(`▸`/`▾`) to expand the full text, exact scores, and `kind`/`when`.

## Persistence (important)

- **Long-term memory lives on disk** at `.memory/<namespace>.jsonl`, named after the
  character's `memory_namespace`, and **persists across server restarts** — this *is* the
  cross-session memory feature. Four sibling files sit beside it: `.commitments.jsonl`,
  `.relationship.json`, `.intent.json`, and `.agency.json`.
- The **short-term buffer** (recent verbatim turns) resets each session.
- **Write-time dedup:** a new memory that's an exact match, or at or above
  `MEMORY_DEDUP_THRESHOLD` in raw cosine, isn't stored. It reinforces the existing memory instead.
- **To wipe a character's mind:** delete `.memory/<namespace>.*`, not just the `.jsonl`, which
  would leave its relationship, intent, goals, and commitments behind. A running server holds this
  state in memory and would write it back, so restart the server afterwards. From code,
  `tools._harness.wipe(slug)` deletes the files and calls `LongTermMemory.invalidate(namespace)`
  to drop the long-term cache; build a fresh `Engine` after it, because a live one keeps its other
  stores. The Director's Sandbox reset does all of this for one character.

## Tuning

Set in `.env` and restart:

| Variable | Default | Effect |
| --- | --- | --- |
| `RR_WEIGHT_SIMILARITY` | 1.0 | weight of meaning-match |
| `RR_WEIGHT_RECENCY` | 0.35 | weight of freshness |
| `RR_WEIGHT_IMPORTANCE` | 0.7 | weight of stored salience |
| `RR_WEIGHT_DIVERSITY` | 0.4 | strength of the near-duplicate penalty |
| `RR_RECENCY_HALF_LIFE` | 20 | memories-newer before recency halves |
| `RR_RELEVANCE_FLOOR` | 0.15 | min normalized base to be eligible |
| `RR_SIMILARITY_SPREAD` | zscore | anisotropy correction: `zscore` / `minmax` / `none` |
| `RR_SPREAD_GAIN` | 1.5 | zscore steepness — higher = wider spread |
| `RR_DECAY_HALF_LIFE` | 30 | base half-life (importance 0) in the **game's** time units |
| `RR_DECAY_IMPORTANCE_SCALE` | 50 | half-life ×= `scale^importance` (super-linear; significant memories near-permanent) |
| `RR_DECAY_REINFORCE_GAIN` | 1.0 | initial slope of reinforcement: small N stretches the half-life by about `1 + gain·N` |
| `RR_DECAY_REINFORCE_CAP` | 12 | reinforcement saturates at `1 + cap` times the half-life |
| `REINFORCE_ON_RECALL` | off | recalling a memory rehearses it (slows decay); writes the store on each retrieve |
| `LONG_TERM_TOP_K` | 6 | budget: max memories injected per turn |
| `MEMORY_DEDUP_THRESHOLD` | 0.97 | raw cosine at which a new memory reinforces an existing one instead of being stored |

E.g. raise `RR_WEIGHT_IMPORTANCE` so world events dominate; raise `RR_WEIGHT_DIVERSITY`
to suppress near-duplicates; lower `RR_RELEVANCE_FLOOR` to admit weaker matches.

In [`memory/relevance.py`](../orchestrator/memory/relevance.py), `RelevanceWeights` still shows
importance 0.5 and `realize_relevance` still shows a budget of 4. `LongTermMemory` always passes
the values above, so those bare defaults apply only to tools that call the scorer directly, such
as `tools/decay_demo.py`.

## Worked example

This uses the default weights (`sim 1.0, str 0.35, imp 0.7`), so `base = sim + 0.35·str +
0.7·imp` (sim/str/imp as 0–1). Bri, a warm character, hears **"do you remember my brother?"**
and these candidates are scored, sorted by `base` as the panel sorts them.

**raw** is the normalized cosine and **sim** is the value after spreading, which is what feeds
`base`. Three simplifications keep the numbers readable. The **str** column shows index-recency
(no game clock); with a clock it would be the game-time decay above. The spreading runs over just
these five rows; a real store spreads across every memory. And the budget is set to
`LONG_TERM_TOP_K=3` so it actually binds.

| memory | raw | sim | str | imp | base | outcome |
| --- | --- | --- | --- | --- | --- | --- |
| "…my brother disappeared in the mines" (old exchange) | .81 | .83 | .35 | **.85** | **1.55** | ★0 |
| `remember()`: "the player saved Bri from the harbor fire" | .74 | .56 | .90 | **.95** | **1.54** | ★2 |
| an older exchange retelling the fire | .74 | .56 | .58 | .55 | 1.15 | · passed over by diversity |
| "Hey" (filler, very recent) | .77 | .69 | .97 | .10 | 1.10 | ★3 |
| "what's a good drink?" (unrelated, old) | .58 | .06 | .20 | .10 | 0.20 | · below the floor |

What each row teaches:
- **Row 1 — character-aware importance protects what matters.** Bri appraised this exchange at
  .85 when it happened, so it leads even though it's old (`str` .35). With scoring off or failed,
  every exchange sits at .50, and the filler "Hey" would score 1.38 against the brother memory's
  1.30. That's the recency trap of [issue
  #3](https://github.com/chihapper/ai-character-game-engine/issues/3): when nothing separates two
  memories, recency wins and buries the old-but-important one.
- **Row 2 — importance rescues relevance.** The fire event is only middling on `sim`, but its
  high `imp` lifts it to the top two. This .95 was pinned by the caller; leave `importance` out of
  `Engine.remember()` and the character appraises the event itself.
- **Row 3 — diversity.** This memory's cosine to the fire event is .92. That's under the 0.97
  dedup threshold, so it was stored as its own memory. Once rows 1 and 2 are picked, its penalty
  is `0.4 × .96` (the penalty uses the 0–1 normalized similarity), or .384. "Hey" is less similar
  to anything picked, say .65, for a penalty of .26. That leaves row 3 at roughly .77 against
  .84 for "Hey", so the higher-base memory loses the last slot.
- **Row 4 — the budget's last slot.** "Hey" isn't valuable. It wins because it repeats nothing
  already in the prompt. At the default budget of 6, rows 1–4 are all injected and diversity only
  sets their order.
- **Row 5 — relevance floor.** Off-topic and unmemorable, it scores 0.20, under the floor of
  0.3075, and is dropped rather than padding the budget.

Net intuition: **`sim` finds what's on-topic, `rec` favors what's fresh, `imp` protects
what matters — and they fight.** Tune the weights to change who wins that fight.

## Current status

All of this is built, on every branch. Items marked *Engine only* don't reach the port 8000
Conversation app.

- **Recall:** [#3](https://github.com/chihapper/ai-character-game-engine/issues/3) high-spread
  similarity + **character-aware salience** (an LLM rates how memorable an exchange is *to
  this character* at write time); **write-time dedup** (re-encounters *reinforce* instead of
  double-injecting); and the **arena query** (recall is searched against the trigger + recent
  turns + live `Situation` + goals, not just the last line).
- **Decay:** [#5](https://github.com/chihapper/ai-character-game-engine/issues/5) temporal decay
  + saturating reinforcement (above).
- **Commitments** (*Engine only*):
  [#4](https://github.com/chihapper/ai-character-game-engine/issues/4) durable obligations, always
  injected, converting to significance-weighted memories on close. Two ways to create them: the
  game API (`commit()` / `resolve_commitment()`) and opt-in **detection from dialogue**
  (`COMMITMENT_DETECTION`), folded into the per-turn judgment call (no extra round-trip). When it
  was built in June 2026, detection scored 8/8 on a discrimination set (real promises in,
  hedges/pleasantries/player-side/hypotheticals out).
- **Stance-conditioned recall** (*Engine only*):
  [#6](https://github.com/chihapper/ai-character-game-engine/issues/6) feelings, the current aim,
  and evolved goals all fold into the arena query. Port 8000 searches on the sheet's goals alone.
- **Beliefs** (*Engine only*): beliefs render under their own prompt header. The top 2 are always
  surfaced, plus any the query recalls. A near-duplicate belief (0.85) supersedes the old one, and
  the set is capped at 6, oldest evicted.
- **Working memory** (*Engine only*): the few fresh, high-salience things that just happened are
  surfaced whether or not recall picked them, on top of the budget. See
  [`engine-overview.md`](engine-overview.md#working-memory-30).
- **Deliberation grounding** (*Engine only*): `rank_window` runs this same scorer over what has
  happened since the character last took stock, skipping exchanges and player events (those render
  separately). Anything with importance of at least 0.9 is always kept, and the rest is
  acknowledged as background, never silently dropped.

> This is a deliberate *approximation* of relevance realization (Vervaeke et al.) for an
> authored-goal NPC — the LLM remains the real relevance realizer over its context; this
> scorer shapes what enters that context.
