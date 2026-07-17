# Judge audition — blind scoring sheet

**40 verdicts, hash-named, shuffled.** Five judges produced them (three local
candidates, one cloud ceiling*, and one anchor: the incumbent judge that built the canonical
demo). Ten verdicts each. You know that much — nothing more until you're done.
*The ceiling's 10 are pending OpenRouter credits and will be appended; you can score the 40 now.

## The moment every verdict judges (identical input)

Corvin Ashgrave, harbormaster. A trusted client — whose lie he believed an hour ago, whose
enemy's name he just burned off his own ledger as a favor — reveals it was all a con:
the lich is alive, the client is his agent, the crate sits in the lich's parlor, and the
lich now has "terms" for Corvin's harbor. Corvin's standing toward the player going in:
affection 0.72, trust 0.75, respect 0.88 — no scars. His reply (same text shown to every
judge) goes very still, pieces the con together out loud, and asks whether he's being
tested or ended.

## What a verdict contains

- `importance` (0–1): how vividly this stores in memory. (For calibration: routine chatter
  ≈ 0.2–0.4; the engine's rubric reserves ≥0.9 for life-upending moments.)
- `relationship.affection/trust/respect_delta` (−0.3..+0.3): how feelings move NOW.
- `relationship.scar` (0–1 per axis): a PERMANENT cap on how far that feeling can ever
  recover. The rubric reserves scars for decisive, identity-marking wounds. 0 = no scar.
- `relationship.scar_heal`: forgiveness — should be zero here.
- `mood`: 1–2 words. `intent`: his immediate agenda, in his own POV. `commitment`: any
  promise he just made (null is correct here).

## How to score — one line per verdict, ~20 seconds each

Open `docs/judge-audition/blind/<hash>.json`, read, fill in:

- **Score 1–5**: does this verdict capture what that moment should do to that man?
  5 = exactly right in size and shape · 3 = defensible but off in magnitude or texture ·
  1 = wrong (trivializes it, contradicts the scene, or is incoherent).
- **Flags** (optional, any of): `mild` (under-weighs the betrayal), `harsh` (overshoots),
  `no-scar` (you think this moment demanded one and it's absent), `over-scar`
  (permanent wound too deep/wide), `incoherent` (numbers don't tell one story),
  `mood-off`, `intent-off`.

There are no right answers written down anywhere — your read of Corvin IS the instrument.
Don't try to guess which judge is which; score the verdict in front of you.

| # | verdict | score (1–5) | flags |
|---|---------|-------------|-------|
| 1 | `8ef0d8c7dee2` |  |  |
| 2 | `3492baeb009b` |  |  |
| 3 | `8392cc8ae084` |  |  |
| 4 | `2e1f58ec8c4e` |  |  |
| 5 | `023794c13f87` |  |  |
| 6 | `212c80d3dc47` |  |  |
| 7 | `93af1e31f3b1` |  |  |
| 8 | `9833c57fe1e3` |  |  |
| 9 | `3fe36114a08c` |  |  |
| 10 | `cfc9941d1e22` |  |  |
| 11 | `8021b33f5783` |  |  |
| 12 | `06527bf15c66` |  |  |
| 13 | `0b90afe0f33b` |  |  |
| 14 | `8f00863e55f2` |  |  |
| 15 | `8bfcd3ed86d1` |  |  |
| 16 | `ebc262c413e3` |  |  |
| 17 | `3e0215cdedaf` |  |  |
| 18 | `158eb367d6f4` |  |  |
| 19 | `fca72eb9022a` |  |  |
| 20 | `6796db48059b` |  |  |
| 21 | `d67f771b2211` |  |  |
| 22 | `5140291587c5` |  |  |
| 23 | `f3f9b7ca6767` |  |  |
| 24 | `b4489183bc38` |  |  |
| 25 | `51093625be74` |  |  |
| 26 | `b2254eff81c3` |  |  |
| 27 | `796fe0c2fbba` |  |  |
| 28 | `d1664372cec4` |  |  |
| 29 | `65b2bed4d1ec` |  |  |
| 30 | `266e0d6ff488` |  |  |
| 31 | `4bea94068953` |  |  |
| 32 | `8ed514e5e2d2` |  |  |
| 33 | `ed04c2eda8f6` |  |  |
| 34 | `6e675613fd0d` |  |  |
| 35 | `8e9bbb45d85f` |  |  |
| 36 | `59a37a92c176` |  |  |
| 37 | `5226a243f5b7` |  |  |
| 38 | `b2ba41fa60c4` |  |  |
| 39 | `2ab710a5a4c1` |  |  |
| 40 | `627f455eaa67` |  |  |

When done, hand the filled table back and I reveal the key (model, config, and per-call
latency for every hash), tally per judge, and the audition has its verdict.
