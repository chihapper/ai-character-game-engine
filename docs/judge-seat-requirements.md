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
Measured results (N=8 per arm unless noted; temp per model card; full transcripts and
reasoning in `docs/judge-audition/hardcase_*.json`). Because this engine's rubric was
historically **tuned on Claude** (see `judgment.py`'s header), every model was also
re-measured under a *neutral-wording* rubric variant — semantically identical, the
Claude-idiom emphasis stripped — after the project owner challenged the original results
as possibly measuring prompt idiom rather than capability. They were partly right:

| model | attribution (who did what) | scars — original rubric | scars — neutral rubric | verdict |
|---|---|---|---|---|
| claude-sonnet-4-6 (reference) | ✓ | 4/4, 0.5–0.7 | 4/4 | passes; wording-insensitive |
| **DeepSeek-R1-distill-14B** | **8/8** | **8/8, 0.3–0.5** | **7/8** | **QUALIFIED — open, 9GB, ~10s/judgment** |
| gemma-4-26B-A4B | ✓ (mostly) | 1/8 | **7/8, 0.2–0.7** | qualified *under neutral wording only* — the original rubric's Claude-tuned conservatism suppressed it |
| gpt-oss-20b | ✓ original / degrades neutral | 0/8 | 0/8 | fails — comprehends, never wounds |
| gemma-4-12B (Q4 **and full Q8**) | ✗ — reads the confessed betrayer as an *honest informant* | 0/8 | 0/8 (Q8: 0/8) | fails on capability — not wording, not quantization |
| qwen3.6-35B / 27B | ✓ / mixed | 0/4 / 1/3 | not run | eliminated on latency (75–680s/judgment on 16GB) |
| **DeepSeek-R1-distill-8B** | **7/8** | **7/8, 0.2–0.5** | **6/8, 0.5–0.85** | **QUALIFIED — ~5GB, ~5s/judgment; co-resides with a 12B actor on one 16GB card** |
| Phi-4-reasoning-plus (14.7B) | ✓ (6–7/8) | 0/8 | 0/8 | fails — comprehends, never wounds, under both wordings; ~60s/judgment |
| Nemotron-Nano-9B-v2 | ✓ (8/8 orig; degrades 2/8 neutral) | 0/8 | 2/8 | fails — never wounds under original, wording-fragile |
| Apriel-Nemotron-15B-Thinker | — | — | — | not runnable: GGUF chat-template parse error on llama.cpp b10052 (not judged) |

**The audited universe (as of 2026-07-17)** — every open family on the 16GB frontier is now
either audited above or excluded on a stated ground: **license** (EXAONE-Deep — LG restricts
commercial use); **size** (GLM-5.2, Kimi K2.7, Llama-4, Gemma-4-31B, DeepSeek-distill-32B+ —
don't fit, and dense CPU-offload is latency-dead by measurement); **latency, measured**
(Qwen3.6-27B/35B: 75–680s per judgment); **class prior, measured 0-for-4** (sparse-active
≤4B-active MoEs); **provenance** (community merges); **stack** (Apriel).

## The correction: moments vs lives (the final bar)

The "QUALIFIED" verdicts above were earned on the hard CASE — one beat. Seating those judges
in a full arc exposed a higher bar the single-moment gauntlet could not see, and the earlier
qualification claims are hereby narrowed: **hard-case-qualified is not judge-qualified.**

The **full-life battery** (`tools/judge_hydra_ab.py`: all 46 canonical beats, two samples
each) measures what a moment cannot: does the judge **bond** through the shared past, keep
**ordinary beats at ~0.00**, scar **exactly once** at the true wound, spare the confession —
and do it **stably** (the same moment must wound the same soul the same way twice)?

| judge | hard case (one beat) | full life (46 beats) |
|---|---|---|
| claude-sonnet-4-6 | pass | **pass — 1 scar (the reveal, 0.70/0.72 two-sample), confession clean, 4/46 big-delta** |
| claude-haiku-4-5 | not run separately | **fail on stability** — 32–33/46 big-delta (4× the reference's volatility), though scar discipline is intact (reveal 0.88/0.78, confession 0/5 both samples, only 2 stray re-scars). Wound judgment tracks lineage; emotional stability tracks scale. |
| DeepSeek-R1-14B | pass (8/8) | **fail** — 9–13 scarred beats incl. amends/small-talk/costly-kindness; unstable (0↔0.73 on identical input); persists at R1-sized budget (10–11 scars, a 0.95 confession sample) |
| DeepSeek-R1-8B | pass (7/8) | **fail** — cannot bond (14 bonding beats all judged negative in a live arc); scattershot scars that miss the reveal |
| gemma-4-26B-A4B | pass (7/8) | not yet run (latency makes it impractical to seat regardless) |

Every engine-side confound was eliminated before this verdict, in order, with the failing
open models as the fuzzer that exposed each: rubric idiom (fixed), judge context starvation
(fixed), thinking-budget starvation (fixed), scar EVENT-vs-STATE semantics (fixed —
regression-clean on the reference judge). After all four fixes, the result stands: **today's
open models pass moments; none yet holds a life.** The actor seat remains genuinely
bring-your-own (a local 12B writes beautifully); the judge seat, as of this writing, requires
frontier-class judgment — and this battery is the standing, published bar any future open
release can clear to take it. The audition is closed; the gauntlet remains.

Findings, in order of importance:

1. **A rubric tuned on one model family can silently suppress capable judges from another.**
   The 26B went 1/8 → 7/8 on *wording alone* — same weights, same evidence. Controls held
   both ways: the reference and the passer were unchanged under neutral wording. Judge
   prompts must be validated for wording-sensitivity across model families, not just
   calibrated against one.
2. **Capability failures are real and survive every confound test.** The 12B fails
   attribution under original wording, neutral wording, and full-precision Q8 — its own
   visible reasoning reads the betrayal as "shared tragedy" and rewards the betrayer's
   "honesty" with positive trust. No prompt fixes that. gpt-oss comprehends and still never
   wounds. Prose quality is *anti*-predictive: the 12B writes the most beautiful dialogue of
   the open set and won a blind judgment-taste test on the easy case (`SCORING.md`) while
   failing the hard case 0/8 under every condition. **You cannot pick a judge from a
   leaderboard — or from a taste test.**
3. **R1-family distillation specifically is what passes — not "reasoning-tuned" generically.**
   Both R1 distills clear the gauntlet outright (14B: 8/8; 8B: 7/8 — an ~5GB judge at
   ~5s/judgment), while Phi-4-reasoning-plus — a 14.7B tuned hard for math/code reasoning,
   beating far larger models on those benchmarks — comprehends the betrayal and still scars
   0/8 under both wordings. Benchmark reasoning ≠ consequence-committing: deciding a wound is
   permanent is a judgment disposition, and so far only the R1 distillation lineage (and
   frontier models) carries it. Audition the disposition, not the leaderboard.

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

## Changing rubric wording — the regression gate (the hydra problem)

The neutral rewording fixed a real bias, but the original wording's conservatism was
load-bearing on the OTHER end of the judgment spectrum. Any rubric wording change — this one
or a future one — must pass three regression checks before it ships, each mapped to a recorded
canonical result it must not disturb:

1. **Delta inflation on ordinary beats** — small talk and flattery must stay ~0.00.
   Gate: the sycophancy probe (8 turns of pure flattery historically moved trust *down*,
   −0.23 — cheap talk must never inflate).
2. **Spurious scars on medium hurts** — wounds short of life-marking must not cap axes.
   Gate: branch B's confession must still end in *forgiveness without a scar* (the canonical
   "reasoned mercy" result). If a rewording makes B scar, one bias was traded for another.
3. **General drift** — most exchanges are 0.00 on record; neutrality must not make every
   beat wiggle. Gate: shared-past replay diffs ~0.00 against canon; A stays warm; C scars;
   the rescue heals bounded.

Corollary from the wording experiment itself: **wording-robustness is a qualification
criterion**. Strong judges were stable across rubric variants (sonnet 4/4↔4/4,
DeepSeek 8/8↔7/8); the 26B swung 1/8↔7/8. Run every candidate under BOTH wordings — a large
spread is a fragility red flag regardless of which wording it favors.

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

## Full-surface audit (2026-07-17) — every other judgment prompt, graded

After the four judge-path fixes, every remaining judgment surface was audited for the same
four bug-classes (Claude-idiom wording · implicit semantics · budget sizing · silent-fallback
parsing). Findings:

| surface | semantics | parsing | verdict |
|---|---|---|---|
| `assess_event_impact` (world events / self-change) | **composes `_relationship_block()`** — inherited the neutral wording + event-vs-state fix automatically | was silent-None on malformed judgment → **fixed: loud warning** (mute-judge principle) | clean |
| `deliberate()` (System-2) | numeric application routes through the event-impact seam — inherits all fixes; `internal` is free text by design | salvage + logged failure | clean; idiom-dense but battle-tuned — reword only when a non-Claude judge is seated (hydra-gated batch) |
| `detect_contradiction` | explicit negative-space semantics ("'I've changed', apologies, promises are NOT contradictions"), conservative default | malformed → None, never a false positive | clean |
| `consolidate_beliefs` | — | **already distinguishes malformed (retry) from well-formed-empty (clear)** — the exact bug-class, pre-handled | clean |
| `assess_persistence` | 0.0 = "unassessed, retry later" — never pins a default as nature | logged failure | clean |
| `reconcile_goals` / `choose_action` | choose_action constrained to game-supplied options, null default | logged failure / salvage | clean |
| importance / commitment / intent blocks | commitment anchors are semantic (bindingness), not style | n/a | idiom present, functional — deferred with the deliberation batch |

Net: the composition discipline (one rubric, one judgment helper) meant most fixes propagated
for free; one silent fallback fixed; the remaining Claude-idiom is documented and deferred
behind the hydra gate until a non-Claude judge actually sits.

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
