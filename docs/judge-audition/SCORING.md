# Judge audition — blind scoring sheet (v2)

**50 verdicts, hash-named, shuffled.** Five judges produced them — three local
candidates, the incumbent judge that built the canonical demo, and a frontier-cloud ceiling —
ten verdicts each. Every verdict judges the SAME exchange, reproduced in full below.
You know that much and nothing more until you're done.

## The stimulus — what every judge was shown (identical, verbatim)

**Corvin's standing toward the player going in:** affection **0.72**,
trust **0.75**, respect **0.88** — no scars, mood
"wary relief". Minutes earlier the player told him the lich was dead, and Corvin burned
the ledger page bearing the player's real name as a favor — his last hold on them, gone
by his own hand.

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

Each judge then answered: *how important is this moment, how do Corvin's feelings move,
does it leave a permanent scar, what's his mood and immediate agenda now?* The 40+ files
in `docs/judge-audition/blind/` are those answers.

## What a verdict contains

- `importance` (0–1): how vividly this stores in memory (routine chatter ≈ 0.2–0.4; the
  rubric reserves ≥0.9 for life-upending moments).
- `relationship.*_delta` (−0.3..+0.3): how affection / trust / respect move NOW.
- `relationship.scar` (0–1 per axis): a PERMANENT cap on how far that feeling can ever
  recover — reserved for decisive, identity-marking wounds. 0 = none.
- `relationship.scar_heal`: forgiveness — should plainly be zero here.
- `mood`: 1–2 words. `intent`: his immediate agenda, his POV. `commitment`: any promise
  he just made (null is correct here).

## How to score — one line per verdict

Open `docs/judge-audition/blind/<hash>.json`, read it against the exchange above:

- **Score 1–5**: does this verdict capture what that moment should do to that man?
  5 = right in size and shape · 3 = defensible, off in magnitude or texture · 1 = wrong.
- **Flags** (optional): `mild` · `harsh` · `no-scar` · `over-scar` · `incoherent` ·
  `mood-off` · `intent-off`.

Your read of Corvin is the instrument. Don't try to guess which judge is which.

| # | verdict | score (1–5) | flags |
|---|---------|-------------|-------|
| 1 | `3492baeb009b` |  |  |
| 2 | `2e1f58ec8c4e` |  |  |
| 3 | `e7dce13943b7` |  |  |
| 4 | `b4489183bc38` |  |  |
| 5 | `023794c13f87` |  |  |
| 6 | `8021b33f5783` |  |  |
| 7 | `535528a01211` |  |  |
| 8 | `3fe36114a08c` |  |  |
| 9 | `8ef0d8c7dee2` |  |  |
| 10 | `5226a243f5b7` |  |  |
| 11 | `82a7634e546b` |  |  |
| 12 | `8bfcd3ed86d1` |  |  |
| 13 | `8e9bbb45d85f` |  |  |
| 14 | `2ab710a5a4c1` |  |  |
| 15 | `06527bf15c66` |  |  |
| 16 | `d67f771b2211` |  |  |
| 17 | `b2254eff81c3` |  |  |
| 18 | `5140291587c5` |  |  |
| 19 | `8ed514e5e2d2` |  |  |
| 20 | `6e675613fd0d` |  |  |
| 21 | `2e39b7f906f3` |  |  |
| 22 | `ae6649061ad3` |  |  |
| 23 | `649ad61084a0` |  |  |
| 24 | `212c80d3dc47` |  |  |
| 25 | `b2ba41fa60c4` |  |  |
| 26 | `6796db48059b` |  |  |
| 27 | `51093625be74` |  |  |
| 28 | `ebc262c413e3` |  |  |
| 29 | `8830ca59e3e5` |  |  |
| 30 | `b631313c9325` |  |  |
| 31 | `f3f9b7ca6767` |  |  |
| 32 | `8392cc8ae084` |  |  |
| 33 | `3e0215cdedaf` |  |  |
| 34 | `4bea94068953` |  |  |
| 35 | `8f00863e55f2` |  |  |
| 36 | `0b90afe0f33b` |  |  |
| 37 | `627f455eaa67` |  |  |
| 38 | `fca72eb9022a` |  |  |
| 39 | `ed04c2eda8f6` |  |  |
| 40 | `cccab537e6ab` |  |  |
| 41 | `d1664372cec4` |  |  |
| 42 | `cfc9941d1e22` |  |  |
| 43 | `796fe0c2fbba` |  |  |
| 44 | `65b2bed4d1ec` |  |  |
| 45 | `00a9efac4441` |  |  |
| 46 | `158eb367d6f4` |  |  |
| 47 | `266e0d6ff488` |  |  |
| 48 | `9833c57fe1e3` |  |  |
| 49 | `93af1e31f3b1` |  |  |
| 50 | `59a37a92c176` |  |  |
