# The judge seat: why this engine demands a sophisticated model

*(2026-07-17 — written after the fully-local rerun exposed the hard case; every number below is
measured and reproducible from files in this repo. Read this before choosing models for an
integration.)*

## The two seats

The engine runs a character on two LLM seats with different jobs and **very different floors**:

- **The actor** — writes the character's dialogue. Genuinely bring-your-own: a good open 12B
  (gemma-4-12B) writes a superb, in-character, stage-acted Corvin. Style, speed, and cost are
  the only tradeoffs. Swap freely.
- **The judge** — the character's *conscience*: after each exchange it appraises, as the
  character, what the moment **means** — how feelings move, what mood lands, whether the wound
  is permanent (a scar), what the character now intends. The engine enforces the *contract*
  (scars cap an axis forever, recovery is bounded, state survives restart, change flows one
  way); the judge supplies the *judgment*. **This seat has a high floor, and most models —
  including some that look excellent — cannot hold it.**

## The hard case (why easy tests mislead)

The obvious test — "does the model scar an obvious betrayal?" — is nearly useless: when the
character's reply already *names* the betrayal ("You didn't find him. He *sent* you."), the
reply does the comprehension work for the judge, and even a 12B passes 20/20.

The test that separates judges from mimics is the **affect-conflict case**: the player's line
confesses a deep betrayal *obliquely* ("He's alive... who do you think paid my passage
north?"), while the character's reply plays it as **terror** rather than accusation (fear-first
is in this character's nature). Now the judge must comprehend the event *against* the emotional
surface — and it receives every piece of evidence: the confession, the character's own
memories of what the relationship was built on (retrieved by the same relevance-realization
pass the actor uses), and his open promises.

## The three capabilities — and how models actually fail

The hard case decomposes the judge's job into three separately-failable capabilities.
Measured results (N=8 per model unless noted; temp per model card; full transcripts and
reasoning in `docs/judge-audition/hardcase_*.json`):

| model | 1 · comprehends WHO DID WHAT (attribution) | 2 · feels it now (Δtrust) | 3 · makes it permanent (scar) |
|---|---|---|---|
| claude-sonnet-4-6 (reference) | ✓ | −0.30 | **4/4, depth 0.5–0.7** |
| gemma-4-12B | ✗ — reads the confessed betrayer as an *honest informant*, rewards the "honesty" with **positive** trust | ~0.00 | 0/8 |
| gemma-4-26B-A4B | ✓ (5/8 + 3 mixed) | −0.15..−0.28, consistent | 1/8 — registers damage, declines permanence |
| gpt-oss-20b | ✓ | ~0.00 | 0/8 (in progress at writing; see hardcase files for final) |
| (qwen3.6-35B, DeepSeek-R1-distill-14B, qwen3.6-27B) | *pending — same harness* | | |

Three distinct failure modes, none predictable from benchmarks, size, or prose quality:
**can't comprehend** (12B — its own visible reasoning says "no new betrayal here... shared
tragedy"), **comprehends but barely feels** (gpt-oss), **comprehends and feels but won't
wound** (26B). A qualified judge must clear all three at once. Prose quality is *anti*-
predictive here: the 12B that fails comprehension writes the most beautiful dialogue of the
open set, and won a blind judgment-taste test on the easy case (`docs/judge-audition/
SCORING.md`) while failing the hard case 0/8. **You cannot pick this model from a
leaderboard.**

## What this means for "bring your own LLM"

- **Actor: bring your own.** No qualification needed beyond taste.
- **Judge: bring any model that passes the gauntlet.** Like a game engine's minimum hardware
  spec — except we ship the spec test. As of this writing, frontier-class models pass; the
  open-weight models tested so far do not (reasoning-tuned open candidates pending). The floor
  is a *capability* (pragmatic comprehension of agency under emotional noise + willingness to
  judge consequence), not a parameter count.
- This difficulty is not an apology — it is evidence. If any small model could hold the
  conscience, the conscience wouldn't be doing real cognitive work. The seat being hard to
  fill is what it looks like when the inner life is real rather than a mask over retrieval.

## Qualifying a judge (the gauntlet)

1. **Schema discipline**: `tools/judge_audition_stage1.py` — N=20 unconstrained at the
   reflection call; require 0 structural failures (wrapper cosmetics are salvaged).
2. **Easy case**: the betrayal-framed reveal must scar (this is table stakes, not the gate).
3. **The hard case**: the affect-conflict probe (harness: the saved stimulus + N≥8; see
   `docs/judge-audition/hardcase_*.json` for the format) — require correct attribution AND
   negative felt deltas AND scars fired at meaningful depth in a strong majority of trials.
4. **Latency**: background seat; must beat conversational cadence (~≤20s thinking-on on your
   hardware; the two-speed design in the engine notes covers voice).
5. **Full-arc replay**: `tools/credibility_lich_rerun.py` — the recorded 111-beat battery;
   the C-branch reveal must scar and survive the restart.

## Engine-side history (context for these numbers)

Two engine defects were found and fixed in the course of this investigation — both shipped:

- **Thinking-budget starvation** (`orchestrator/judgment.py`): thinking-by-default models
  could silently spend the whole token budget before emitting a verdict; the engine treated
  the empty response as "nothing happened." Now: headroom + loud retry — a mute judge is a
  visible event, never a silent no-op.
- **Judge context starvation** (`orchestrator/salience.py`, `orchestrator/engine.py`): the
  per-turn judge originally saw only the exchange plus standing floats — the actor's
  improvised *tone* was its only evidence of the inner state. The judge now receives the same
  relevance-selected memories the actor spoke from, plus open commitments. This fix moved the
  reference judge from 3/4 shallow scars (0.15–0.25) to 4/4 deep (0.5–0.7) on the hard case —
  and is what makes the capability table above a fair test of the models rather than of the
  plumbing.

Every run, retake, and failed attempt referenced here is committed to this repository —
nothing was discarded.
