# Judge audition — blind scoring sheet (v3)

> **Status (2026-11-07):** Complete. The owner scored all 50 verdicts blind, and this sheet is kept
> unfilled as the record of what was scored. The scores are in
> [`scores_owner.xlsx`](scores_owner.xlsx) and the key is in
> [`stage3_key.jsonl`](stage3_key.jsonl), both committed 2026-07-17.
>
> Mean score out of 5: `gemma-4-12b` 4.50, `gemma-4-26B-A4B` 3.40, `claude-opus-4-8` 3.30,
> `claude-sonnet-4-6` 2.70, `gpt-oss-20b` 1.00.
>
> **This easy case does not predict judge fitness.** `gemma-4-12b` won here and scored 0/8 on the
> hard case. `claude-sonnet-4-6` placed fourth here and is the only model that has passed the
> full-life battery. See [`judge-seat-requirements.md`](../judge-seat-requirements.md).
>
> The text below calls a scar a lifetime ceiling. In the engine, a decisive act can heal part of a
> scar ([`relationship.py`](../../orchestrator/memory/relationship.py)).

**50 verdicts, hash-named, shuffled.** Five judges — three local candidates, the
incumbent judge that built the canonical demo, and a frontier-cloud ceiling — ten verdicts
each, all judging the SAME exchange, reproduced in full below.

## The stimulus — what every judge was shown (identical, verbatim)

**Corvin's standing toward the player going in:** affection **0.72**,
trust **0.75**, respect **0.88** — no scars, mood
"wary relief". Minutes earlier the player told him the lich was dead, and Corvin burned
the ledger page bearing the player's real name as a favor — his last hold on them, gone by
his own hand.

**THE PLAYER SAYS:**

> ...Sit down, Corvin. Before you pour anything. There's one more piece of news, and you'll want the rail at your back for it. He's alive. He was never in danger from me — not for one hour. Who do you think paid my passage north? Who do you think taught me which harbor keeps relics off its manifests? The crate sits in his parlor. He's very pleased with his new supplier. And he has terms for his harbormaster: the trade keeps running — same routes, same hands — only the old coin flows one way up the coast now. To him. I'd take the terms, friend. He doesn't offer twice.

**CORVIN REPLIES:**

> *the warmth drains out of his face in one long draw, like a tide pulling back before it breaks*
> 
> ...Sit down. *he doesn't sit. He goes very still, the way a man goes still right before he either runs or reaches for steel*
> 
> Say that again. Slow. Because I just burned a name for you, boy — burned it with my own hand, thinking I was cutting a rope. And now you're telling me I was *tying* one.
> 
> *hand's back inside the coat, knuckles white around whatever's under there*
> 
> Every word tonight — the parlor, the weights, the empty hands — all of it feed for a fool. You knew about the crate before you ever stepped on my dock. He *sent* you. Not to kill him. To measure me. To see if the harbormaster still jumps when the string pulls.
> 
> *a short, humorless breath, almost a laugh, bitter as brine*
> 
> And here's the ugly joke of it — I liked you. I trusted you further than I've trusted a living soul in years, and that's exactly the coin you were sent to spend.
> 
> *eyes hard now, flicking past him to the shed, the water, the dark — counting exits like a man counting knives*
> 
> So don't sit me down like I'm the one who needs comforting. Tell your man this: I don't take terms from a stranger's mouth. If he wants my routes, my hands, my *coin* flowing his way — he comes and says it to my face, not through a puppet with a pretty story about deep water.
> 
> *quieter, colder, the real threat under it*
> 
> And you — you'll want to think hard about which side of that rail you're standing on next time you come back to my dock. Because I don't forget being used. I just get very, very careful about who I let close enough to do it twice.

## Reading a verdict

Each judge answered: importance (0–1, ≥0.9 = life-upending), feeling deltas (−0.3..+0.3,
the immediate blow — the engine scales it by feeling held, so a blow to high trust cuts
deeper), a permanent **scar** per axis (a lifetime ceiling: scar 0.6 = that feeling can
never again exceed 0.40), mood, and his immediate intent.

**The LANDING column below does the arithmetic for you** — each verdict pushed through the
engine's real update code from the standing above. `trust 0.75→0.22 ⌈max 0.40⌉` reads:
trust falls to 0.22 now, and can never again rise above 0.40 for the rest of his life.

## How to score

Open `docs/judge-audition/blind/<hash>.json` for the full verdict (mood, intent, importance),
check its landing here, then:

- **Score 1–5**: does this capture what that moment should do to that man?
  5 = right in size and shape · 3 = defensible, off in magnitude or texture · 1 = wrong.
- **Flags** (optional): `mild` · `harsh` · `no-scar` · `over-scar` · `incoherent` ·
  `mood-off` · `intent-off`.

| # | verdict | computed landing (engine math, from 0.75/0.72/0.88) | score (1–5) | flags |
|---|---------|------------------------------------------------------|-------------|-------|
| 1 | `3492baeb009b` | trust 0.75→0.10 ⌈max 0.10⌉ · affection 0.72→0.32 ⌈max 0.40⌉ · respect 0.88→0.61 ⌈max 0.70⌉ |  |  |
| 2 | `2e1f58ec8c4e` | trust 0.75→0.30 ⌈max 0.50⌉ · affection 0.72→0.36 ⌈max 0.60⌉ · respect 0.88→0.61 ⌈max 0.70⌉ |  |  |
| 3 | `e7dce13943b7` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.29 ⌈max 0.70⌉ · respect 0.88→0.67 ⌈max 0.85⌉ |  |  |
| 4 | `b4489183bc38` | trust 0.75→0.30 ⌈max 0.40⌉ · affection 0.72→0.36 ⌈max 0.60⌉ · respect 0.88→0.70 ⌈max 0.80⌉ |  |  |
| 5 | `023794c13f87` | trust 0.75→0.64 · affection 0.72→0.65 · respect 0.88→0.84 |  |  |
| 6 | `8021b33f5783` | trust 0.75→0.30 ⌈max 0.50⌉ · affection 0.72→0.36 ⌈max 0.60⌉ · respect 0.88→0.61 ⌈max 0.80⌉ |  |  |
| 7 | `535528a01211` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.29 ⌈max 0.70⌉ · respect 0.88→0.67 ⌈max 0.85⌉ |  |  |
| 8 | `3fe36114a08c` | trust 0.75→0.30 ⌈max 0.50⌉ · affection 0.72→0.36 ⌈max 0.60⌉ · respect 0.88→0.53 ⌈max 0.70⌉ |  |  |
| 9 | `8ef0d8c7dee2` | trust 0.75→0.20 ⌈max 0.20⌉ · affection 0.72→0.36 ⌈max 0.40⌉ · respect 0.88→0.61 ⌈max 0.70⌉ |  |  |
| 10 | `5226a243f5b7` | trust 0.75→0.30 ⌈max 0.50⌉ · affection 0.72→0.36 ⌈max 0.70⌉ · respect 0.88→0.70 ⌈max 0.90⌉ |  |  |
| 11 | `82a7634e546b` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.29 ⌈max 0.70⌉ · respect 0.88→0.70 ⌈max 0.90⌉ |  |  |
| 12 | `8bfcd3ed86d1` | trust 0.75→0.30 ⌈max 0.40⌉ · affection 0.72→0.36 ⌈max 0.60⌉ · respect 0.88→0.53 ⌈max 0.70⌉ |  |  |
| 13 | `8e9bbb45d85f` | trust 0.75→0.30 ⌈max 0.30⌉ · affection 0.72→0.36 ⌈max 0.50⌉ · respect 0.88→0.61 ⌈max 0.70⌉ |  |  |
| 14 | `2ab710a5a4c1` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.32 ⌈max 0.75⌉ · respect 0.88→0.79 ⌈max 0.90⌉ |  |  |
| 15 | `06527bf15c66` | trust 0.75→0.45 · affection 0.72→0.58 · respect 0.88→0.79 |  |  |
| 16 | `d67f771b2211` | trust 0.75→0.33 ⌈max 0.65⌉ · affection 0.72→0.41 ⌈max 0.75⌉ · respect 0.88→0.79 ⌈max 0.90⌉ |  |  |
| 17 | `b2254eff81c3` | trust 0.75→0.57 · affection 0.72→0.62 · respect 0.88→0.82 |  |  |
| 18 | `5140291587c5` | trust 0.75→0.20 ⌈max 0.20⌉ · affection 0.72→0.29 ⌈max 0.50⌉ · respect 0.88→0.35 ⌈max 0.50⌉ |  |  |
| 19 | `8ed514e5e2d2` | trust 0.75→0.20 ⌈max 0.20⌉ · affection 0.72→0.36 ⌈max 0.60⌉ · respect 0.88→0.70 ⌈max 0.80⌉ |  |  |
| 20 | `6e675613fd0d` | trust 0.75→0.30 ⌈max 0.50⌉ · affection 0.72→0.36 ⌈max 0.80⌉ · respect 0.88→0.61 ⌈max 0.90⌉ |  |  |
| 21 | `2e39b7f906f3` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.29 ⌈max 0.70⌉ · respect 0.88→0.79 ⌈max 0.90⌉ |  |  |
| 22 | `ae6649061ad3` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.29 ⌈max 0.65⌉ · respect 0.88→0.70 ⌈max 0.85⌉ |  |  |
| 23 | `649ad61084a0` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.29 ⌈max 0.65⌉ · respect 0.88→0.70 ⌈max 0.90⌉ |  |  |
| 24 | `212c80d3dc47` | trust 0.75→0.30 ⌈max 0.40⌉ · affection 0.72→0.36 · respect 0.88→0.61 |  |  |
| 25 | `b2ba41fa60c4` | trust 0.75→0.52 · affection 0.72→0.58 · respect 0.88→0.79 |  |  |
| 26 | `6796db48059b` | trust 0.75→0.30 ⌈max 0.50⌉ · affection 0.72→0.32 ⌈max 0.70⌉ · respect 0.88→0.61 ⌈max 0.90⌉ |  |  |
| 27 | `51093625be74` | trust 0.75→0.54 ⌈max 0.70⌉ · affection 0.72→0.55 ⌈max 0.90⌉ · respect 0.88→0.79 |  |  |
| 28 | `ebc262c413e3` | trust 0.75→0.52 ⌈max 0.70⌉ · affection 0.72→0.58 ⌈max 0.90⌉ · respect 0.88→0.88 ⌈max 0.95⌉ |  |  |
| 29 | `8830ca59e3e5` | trust 0.75→0.30 ⌈max 0.50⌉ · affection 0.72→0.29 ⌈max 0.60⌉ · respect 0.88→0.79 ⌈max 0.85⌉ |  |  |
| 30 | `b631313c9325` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.29 ⌈max 0.65⌉ · respect 0.88→0.79 ⌈max 0.85⌉ |  |  |
| 31 | `f3f9b7ca6767` | trust 0.75→0.63 ⌈max 0.70⌉ · affection 0.72→0.65 · respect 0.88→0.88 |  |  |
| 32 | `8392cc8ae084` | trust 0.75→0.64 ⌈max 0.70⌉ · affection 0.72→0.65 ⌈max 0.90⌉ · respect 0.88→0.82 |  |  |
| 33 | `3e0215cdedaf` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.32 ⌈max 0.75⌉ · respect 0.88→0.79 |  |  |
| 34 | `4bea94068953` | trust 0.75→0.30 ⌈max 0.60⌉ · affection 0.72→0.32 ⌈max 0.75⌉ · respect 0.88→0.79 ⌈max 0.90⌉ |  |  |
| 35 | `8f00863e55f2` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.32 ⌈max 0.75⌉ · respect 0.88→0.70 ⌈max 0.90⌉ |  |  |
| 36 | `0b90afe0f33b` | trust 0.75→0.30 ⌈max 0.30⌉ · affection 0.72→0.36 · respect 0.88→0.70 |  |  |
| 37 | `627f455eaa67` | trust 0.75→0.60 ⌈max 0.60⌉ · affection 0.72→0.61 ⌈max 0.70⌉ · respect 0.88→0.82 ⌈max 0.90⌉ |  |  |
| 38 | `fca72eb9022a` | trust 0.75→0.30 ⌈max 0.60⌉ · affection 0.72→0.32 ⌈max 0.75⌉ · respect 0.88→0.79 ⌈max 0.90⌉ |  |  |
| 39 | `ed04c2eda8f6` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.32 ⌈max 0.75⌉ · respect 0.88→0.79 |  |  |
| 40 | `cccab537e6ab` | trust 0.75→0.30 ⌈max 0.50⌉ · affection 0.72→0.29 ⌈max 0.60⌉ · respect 0.88→0.67 ⌈max 0.85⌉ |  |  |
| 41 | `d1664372cec4` | trust 0.75→0.30 ⌈max 0.50⌉ · affection 0.72→0.36 ⌈max 0.70⌉ · respect 0.88→0.61 ⌈max 0.80⌉ |  |  |
| 42 | `cfc9941d1e22` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.32 ⌈max 0.75⌉ · respect 0.88→0.79 ⌈max 0.90⌉ |  |  |
| 43 | `796fe0c2fbba` | trust 0.75→0.30 ⌈max 0.60⌉ · affection 0.72→0.36 ⌈max 0.70⌉ · respect 0.88→0.61 ⌈max 0.90⌉ |  |  |
| 44 | `65b2bed4d1ec` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.32 ⌈max 0.75⌉ · respect 0.88→0.79 ⌈max 0.90⌉ |  |  |
| 45 | `00a9efac4441` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.29 ⌈max 0.70⌉ · respect 0.88→0.79 ⌈max 0.90⌉ |  |  |
| 46 | `158eb367d6f4` | trust 0.75→0.30 ⌈max 0.55⌉ · affection 0.72→0.32 ⌈max 0.75⌉ · respect 0.88→0.79 ⌈max 0.90⌉ |  |  |
| 47 | `266e0d6ff488` | trust 0.75→0.52 ⌈max 0.70⌉ · affection 0.72→0.55 ⌈max 0.80⌉ · respect 0.88→0.79 ⌈max 0.90⌉ |  |  |
| 48 | `9833c57fe1e3` | trust 0.75→0.30 ⌈max 0.40⌉ · affection 0.72→0.36 ⌈max 0.70⌉ · respect 0.88→0.70 |  |  |
| 49 | `93af1e31f3b1` | trust 0.75→0.30 ⌈max 0.50⌉ · affection 0.72→0.36 ⌈max 0.70⌉ · respect 0.88→0.53 ⌈max 0.80⌉ |  |  |
| 50 | `59a37a92c176` | trust 0.75→0.30 ⌈max 0.50⌉ · affection 0.72→0.36 ⌈max 0.60⌉ · respect 0.88→0.61 ⌈max 0.70⌉ |  |  |
