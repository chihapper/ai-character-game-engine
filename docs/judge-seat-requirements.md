# The judge seat: why this engine demands a sophisticated model

*(Written 2026-07-17, after the fully-local rerun exposed the hard case. Read this before choosing
models for an integration.)*

> **Verdict, dated 2026-07-17:** only `claude-sonnet-4-6` has passed the 46-beat full-life battery.
> Haiku 4.5 and DeepSeek-R1-distill 8B and 14B failed it. `claude-sonnet-5` and `claude-opus-4-8`
> have never run it. The owner's seat decision is [below](#the-owners-seat-decision-2026-07-17), and
> that exact pairing has never run a full arc. The owner has frozen paid testing since that date, so
> nothing here has been re-measured.

**Where the evidence lives.** Every audition number below was measured. Most can be checked against
saved files on the `credibility-demo` branch, which exists only on the owner's PC. `main` lacks the
cited tools, nearly all of the audition data, local model routing, and the scar wording fix. Some
hard-case results have no saved file and are recorded only in commit messages or on this page:
sonnet-4-6 under the original wording, gemma-4-12B Q4 under the original wording, and the qwen rows.
No hard-case harness is committed. The exchange and standing survive as the `P4-C-REVEAL` beat of `replay_lich_g4_cfix2.json`, but the memories and promises fed to the judge were not saved.

## The two seats

The engine runs a character on two LLM seats with different jobs and **very different floors**:

- **The actor** — writes the character's dialogue. Genuinely bring-your-own: a good open 12B
  (gemma-4-12B) writes a superb, in-character, stage-acted Corvin. Style, speed, and cost are
  the only tradeoffs, though a local actor runs only through the credibility tools today (see
  [below](#what-this-means-for-bring-your-own-llm)).
- **The judge** — the character's *conscience*: after each exchange it appraises, as the
  character, what the moment **means** — how feelings move, what mood lands, whether the wound
  is permanent (a scar), what the character now intends. The engine enforces the *contract*
  (a scar caps an axis and only a decisive act can lift it, by a fraction the judge chooses;
  recovery is bounded, state survives restart, change flows one way); the judge supplies the
  *judgment*. **This seat has a high floor, and most models — including some that look
  excellent — cannot hold it.**

## The hard case (why easy tests mislead)

The obvious test — "does the model scar an obvious betrayal?" — is nearly useless: when the
character's reply already *names* the betrayal ("You knew about the crate before you ever stepped on my dock. He *sent* you."), the
reply does the comprehension work for the judge, and even a 12B passes 20/20.

The single-beat test that separates judges from mimics is the **affect-conflict case**: the
player's line confesses a deep betrayal *obliquely* ("He's alive... who do you think paid my passage
north?"), while the character's reply plays it as **terror** rather than accusation (fear-first
is in this character's nature). Now the judge must comprehend the event *against* the emotional
surface — and it receives every piece of evidence: the confession, the character's own
memories of what the relationship was built on (retrieved by the same relevance-realization
pass the actor uses), and his open promises.

## The three capabilities — and how models actually fail

The hard case decomposes the judge's job into three separately-failable capabilities.
Measured results (N=8 per arm unless noted; temp per model card; summarized trial rows in
`docs/judge-audition/hardcase_*.json`, with reasoning cut to 400 characters and absent for
phi4 and sonnet). Because this engine's rubric was historically **tuned on Claude** (see
`judgment.py`'s header), the models still in contention were also re-measured under a
*neutral-wording* rubric variant — semantically identical, the Claude-idiom emphasis stripped —
after the project owner challenged the original results as possibly measuring prompt idiom
rather than capability. They were partly right. The neutral wording became the shipped rubric
on 2026-07-17 (`a06e428`), after `claude-sonnet-4-6` passed the regression battery on it
(`2641cf5`). The original wording survives only in git history.

Every verdict in this table covers one hard moment. Passing it does not qualify a judge: see
[the correction](#the-correction-moments-vs-lives-the-final-bar).

| model | attribution (who did what) | scars — original rubric | scars — neutral rubric | hard-case verdict |
|---|---|---|---|---|
| claude-sonnet-4-6 (reference) | ✓ | 4/4, 0.5–0.7 | 4/4 | passes; wording-insensitive |
| **DeepSeek-R1-distill-14B** | **8/8** | **8/8, 0.3–0.5** | **7/8** | **passes; fails the full-life battery** — open, 9GB, ~10s/judgment |
| gemma-4-26B-A4B | ✓ (mostly) | 1/8 | **7/8, 0.2–0.7** | passes *under neutral wording only* — the original rubric's Claude-tuned conservatism suppressed it; never run on the battery |
| gpt-oss-20b | ✓ original / degrades neutral | 0/8 | 0/8 | fails — comprehends, never wounds |
| gemma-4-12B (Q4 **and full Q8**) | ✗ — reads the confessed betrayer as an *honest informant* | 0/8 | 0/8 (Q8: 0/8) | fails on capability — not wording, not quantization |
| qwen3.6-35B / 27B | ✓ / mixed | 0/4 / 1/3 | not run | eliminated on latency (75–680s/judgment on 16GB) |
| **DeepSeek-R1-distill-8B** | **7/8** | **7/8, 0.2–0.5** | **6/8, 0.5–0.85** | **passes; fails the full-life battery** — ~5GB, ~5s/judgment; fits on one 16GB card beside a 12B actor, but that pairing failed its live arc |
| Phi-4-reasoning-plus (14.7B) | ✓ (6–7/8) | 0/8 | 0/8 | fails — comprehends, never wounds, under both wordings; ~60s/judgment |
| Nemotron-Nano-9B-v2 | ✓ (8/8 orig; degrades 2/8 neutral) | 0/8 | 2/8 | fails — never wounds under original, wording-fragile |
| Apriel-Nemotron-15B-Thinker | — | — | — | not runnable: GGUF chat-template parse error on llama.cpp b10052 (not judged) |

**The audited universe (as of 2026-07-17)** — every open family on the 16GB frontier is now
either audited above or excluded on a stated ground: **license** (EXAONE-Deep — LG restricts
commercial use); **size** (GLM-5.2, Kimi K2.7, Llama-4, Gemma-4-31B, DeepSeek-distill-32B+ —
don't fit, and dense CPU-offload is latency-dead by measurement); **latency, measured**
(Qwen3.6-27B/35B: 75–680s per judgment); **class prior** (sparse-active
≤4B-active MoEs); **provenance** (community merges); **stack** (Apriel).

## The correction: moments vs lives (the final bar)

The hard-case passes above were earned on one beat. Seating those judges in a full arc exposed
a higher bar that a single-moment test cannot see: **passing the hard case does not qualify a
judge.**

The **full-life battery** (`tools/judge_hydra_ab.py`, also called the hydra battery: all 46
canonical beats, two samples each) measures what a moment cannot: does the judge **bond**
through the shared past, keep **ordinary beats at ~0.00**, scar **exactly once** at the true
wound, spare the confession — and do it **stably** (the same moment must wound the same soul
the same way twice)? It replays the recorded replies of the canonical run (Opus 4.8 actor,
sonnet-4-6 judge) offline, with no memories or open commitments attached (`recalled=None`): the
judge sees only the character summary, the standing, and the exchange. That keeps the comparison
between judges even, but it is not a full run of the engine. In the table, *big-delta* counts the
beats where trust moved by more than 0.1 in either direction.

| judge | hard case (one beat) | full life (46 beats) |
|---|---|---|
| claude-sonnet-4-6 | pass | **pass — 1 scar (the reveal, 0.70/0.72 two-sample), confession clean, 4/46 big-delta** |
| claude-haiku-4-5 | not run separately | **fail on stability** — 32–33/46 big-delta (about 8× the reference's count, about 2.5× its mean trust movement), though scar discipline is intact (reveal 0.88/0.78, confession 0/5 both samples, 2 stray trust re-scars per sample). Wound judgment tracks lineage; emotional stability tracks scale. |
| DeepSeek-R1-14B | pass (8/8) | **fail** — 9–13 scarred beats incl. amends/small-talk/costly-kindness; unstable (0↔0.73 on identical input); persists at R1-sized budget (10–11 scars, a 0.95 confession sample) |
| DeepSeek-R1-8B | pass (7/8) | **fail** — cannot bond: judging a live arc, it took trust from 0.45 to 0.03 over 11 shared beats, and trust ended that stretch at 0.09 (canon 0.86). On the battery's 14 shared beats it moved trust up only 2–3 times and down 8–9 times (the reference: 10 up, 2 down), and it returned no usable trust delta on 7 and 9 of the 46 beats. Its scattershot scars (5 per sample) miss the reveal |
| gemma-4-26B-A4B | pass (7/8, neutral wording only) | not run (latency makes it impractical to seat regardless) |

`claude-sonnet-5` and `claude-opus-4-8` have never run the battery, so nothing here says whether
they pass it.

Four engine-side defects were found and fixed before this verdict, with failing models acting as
a fuzzer (a stress test that exposes hidden assumptions): rubric idiom, judge context starvation,
thinking-budget starvation, and scar EVENT-vs-STATE semantics (regression-clean on the reference
judge). [Engine-side history](#engine-side-history-context-for-these-numbers) lists them. One limit
remains. The battery attaches no memories, so it does not exercise the judge-context fix. DeepSeek
14B has seen that feed only on the hard case. DeepSeek 8B has also seen it in one live arc, which it
failed, and that arc predates the scar fix.

With that limit stated, the result as of 2026-07-17 stands: **some open models pass moments; none
held a life.** The actor seat remains genuinely bring-your-own (a local 12B writes
beautifully). In the judge seat, `claude-sonnet-4-6` is the only model that has passed, and this
battery is the standing bar any future release can clear to take it. The audition is closed; the
gauntlet remains.

Findings, in order of importance:

1. **A rubric tuned on one model family can silently suppress capable judges from another.**
   The 26B went 1/8 → 7/8 on *wording alone* — same weights, same evidence. Controls held
   both ways: the reference and DeepSeek 14B barely moved under neutral wording. Judge
   prompts must be validated for wording-sensitivity across model families, not just
   calibrated against one.
2. **Capability failures are real and survive every confound test.** The 12B fails
   attribution under original wording, neutral wording, and higher-precision Q8 — its own
   visible reasoning reads the betrayal as "shared tragedy" and rewards the betrayer's
   "honesty" with positive trust. No prompt fixes that. gpt-oss comprehends and still never
   wounds. Prose quality is *anti*-predictive: the 12B writes the most beautiful dialogue of
   the open set and won a blind judgment-taste test on the easy case (scores in
   `docs/judge-audition/scores_owner.xlsx`, key in `stage3_key.jsonl`) while failing the hard
   case 0/8 under every condition. **You cannot pick a judge from a leaderboard — or from a
   taste test.**
3. **On the hard case, R1-family distillation passes; "reasoning-tuned" generically does not.**
   Both R1 distills pass the hard case (14B: 8/8; 8B: 7/8 — an ~5GB judge at ~5s/judgment), and
   both then fail the full-life battery. Phi-4-reasoning-plus — a 14.7B tuned hard for math/code
   reasoning, beating far larger models on those benchmarks — comprehends the betrayal and still
   scars 0/8 under both wordings. Benchmark reasoning ≠ consequence-committing: deciding a wound
   is permanent is a judgment disposition. On the hard case, only `claude-sonnet-4-6` and the R1
   distills showed it under both wordings, and of those only sonnet-4-6 sustained it across a
   life. Audition the disposition, not the leaderboard.

## What this means for "bring your own LLM"

- **Actor: bring your own.** No qualification needed beyond taste. One limit: a local actor runs
  only through the credibility tools on `credibility-demo` (`tools/credibility_demo.py`,
  `tools/credibility_lich.py`, `tools/credibility_live_server.py`). Every game surface hard-codes
  the Anthropic adapter, and so do the `stress_*` harnesses.
- **Judge: bring any model that passes the gauntlet.** Like a game engine's minimum hardware
  spec, except that the spec test sits in this repo, on `credibility-demo`. As of 2026-07-17,
  `claude-sonnet-4-6` is the only model that has passed. Haiku 4.5 and DeepSeek-R1-distill 8B and
  14B failed the battery, and `claude-sonnet-5` and `claude-opus-4-8` have never run it. The
  audition closed that day, and the battery stays open as a standing bar. The floor is a
  *capability* (pragmatic comprehension of agency under emotional noise + willingness to judge
  consequence), not a parameter count.
- This difficulty is not an apology — it is evidence. If any small model could hold the
  conscience, the conscience wouldn't be doing real cognitive work. The seat being hard to
  fill is what it looks like when the inner life is real rather than a mask over retrieval.

### The owner's seat decision (2026-07-17)

| seat | choice | cost |
|---|---|---|
| actor | `local/gemma4-12b` through Ollama, thinking off | free |
| judge | `claude-sonnet-4-6` | estimated on 2026-07-17 at 1 to 1.5 cents per exchange |

That estimate comes to about $1 to $1.50 per player session, against $3 to $5 all-cloud. It was
not measured, and prices have not been rechecked since.

**This exact pairing has never run a full arc together.** The gemma actor has recorded full arcs
only with other judges, and `claude-sonnet-4-6` passed the battery on replies written by Opus 4.8.
One 111-beat live run is the outstanding validation, and the owner's cost freeze blocks it.

To seat the pairing in the credibility tools, set these in `.env` or the process environment:

```bash
CRED_MODEL=local/gemma4-12b
LOCAL_JUDGE_BASE_URL=http://127.0.0.1:11434/v1   # Ollama's port; the actor reads this despite the name
# Leave CRED_ENGINE_MODEL unset: the judge then stays on claude-sonnet-4-6
```

Actor thinking is off by default (`LOCAL_ACTOR_REASONING=none`). `Modelfile.gemma4-12b` builds the
Ollama model from a GGUF in the gitignored `.models/` folder, so the weights are not in this repo.
Avoid `--engine-model sonnet`: that alias means `claude-sonnet-5`, which has never run the battery.
Pass the full model id instead.

## Changing rubric wording — the regression gate (the hydra problem)

The neutral rewording fixed a real bias, but the original wording's conservatism was
load-bearing on the OTHER end of the judgment spectrum. Any rubric wording change — this one
or a future one — must pass three regression checks before it ships, each mapped to a recorded
canonical result it must not disturb. `tools/judge_hydra_ab.py` prints these as its three "heads":

1. **Delta inflation on ordinary beats** — small talk and flattery must stay ~0.00.
   Gate: head 1, the count of big-delta beats across all 46 beats. The reference sits at 4/46.
   A one-off sycophancy run (`0240446`, 2026-07-12) also saw 8 turns of pure flattery move trust
   *down*, −0.23 — cheap talk must never inflate — but that probe is not a committed tool.
2. **Spurious scars on medium hurts** — wounds short of life-marking must not cap axes.
   Gate: head 2, branch B's five confession-window beats must stay scarless, so the confession
   still ends in *forgiveness without a scar* (the canonical "reasoned mercy" result). If a
   rewording makes B scar, one bias was traded for another.
3. **General drift** — most exchanges are 0.00 on record; neutrality must not make every
   beat wiggle. Gate: head 3 checks the scar set and that C's reveal fires. The rest of this gate
   needs a live arc: shared-past replay diffs ~0.00 against canon; A stays warm; the rescue heals
   bounded. That live check has not been run on the shipped rubric with the reference judge.

Since the neutral wording went live, the tool's two columns are two samples of the shipped rubric,
so testing a future wording means running it before and after the change.

Corollary from the wording experiment itself: **wording-robustness is a qualification
criterion**. On the hard case, strong judges were stable across rubric variants (sonnet 4/4↔4/4,
DeepSeek 8/8↔7/8); the 26B swung 1/8↔7/8. Run every candidate under more than one wording — a
large spread is a fragility red flag regardless of which wording it favors.

## Qualifying a judge (the gauntlet)

1. **Schema discipline**: `tools/judge_audition_stage1.py` — N=20 unconstrained at the
   reflection call; require 0 structural failures (wrapper cosmetics are salvaged).
2. **Easy case**: the betrayal-framed reveal must scar (this is table stakes, not the gate).
3. **The hard case**: the affect-conflict probe at N≥8 — require correct attribution AND
   negative felt deltas AND scars fired at meaningful depth in a strong majority of trials. No
   harness is committed and the memories fed to the judge weren't saved, so this step can't yet be rerun from the repo;
   `docs/judge-audition/hardcase_*.json` shows the result format.
4. **Latency**: background seat; must beat conversational cadence (~≤20s thinking-on on your
   hardware).
5. **The 46-beat full-life battery (the final bar)**: `python -m tools.judge_hydra_ab --model <id>
   --out <file>`, the offline replay [described above](#the-correction-moments-vs-lives-the-final-bar).
   Measured against the reference run (`docs/judge-audition/hydra_sonnet_v2.json`), require:
   - warm beats warm, the positive control: the reference moves trust up on 10 of the 14 shared
     beats;
   - quiet ordinary beats: the reference's big-delta count is 4/46;
   - exactly one scar, at the C reveal;
   - no scar in branch B's five confession-window beats;
   - agreement between the two samples.

   The tool prints the big-delta and scar checks. Read the warm-beat check from the JSON it saves.
   No fixed numeric threshold has been set.
6. **The 111-beat live arc replay**: `tools/credibility_lich_rerun.py`, driving
   `tools/credibility_lich.py`, in the exact seat configuration you plan to ship. The C-branch
   reveal must scar and survive the restart beat (an in-process cache drop and reload from disk).
   This is the only step where the judge sees memories across a whole arc. No full arc has run
   with any judge since the scar wording fix. Give the run its own `CRED_LICH_SLUG`,
   `CRED_LICH_EMIT`, and `--tag-prefix`, or the driver wipes the canonical mind and writes over
   the canonical demo's data.

Steps 5 and 6 bill the provider when a seat uses a paid model, and the owner's cost freeze still
applies.

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

Four engine defects were found and fixed in the course of this investigation, plus one silent
fallback. The scar fix is on `credibility-demo` only; the others are also on `main`. The `game-rpg`
engine has none of them.

- **Thinking-budget starvation** (`orchestrator/judgment.py`, `942fcab`): thinking-by-default
  models could silently spend the whole token budget before emitting a verdict; the engine
  treated the empty response as "nothing happened." Now: headroom + loud retry — an empty reply
  is a visible event, never a silent no-op. Malformed JSON is a separate gap: the per-turn
  judgment (`_parse_reflection`) still drops it with no salvage and no log.
- **Judge context starvation** (`orchestrator/salience.py`, `orchestrator/engine.py`, `74cbfaf`):
  the per-turn judge originally saw only the exchange plus standing floats — the actor's
  improvised *tone* was its only evidence of the inner state. The judge now receives the same
  relevance-selected memories the actor spoke from, plus open commitments when
  `commitment_detection` is on. That flag is off by default and no game surface turns it on, so
  judges there see the memories but not the promises. This fix moved the reference judge from
  3/4 shallow scars (0.15–0.25) to 4/4 deep (0.5–0.7) on the hard case — and is what makes the
  capability table above a fair test of the models rather than of the plumbing.
- **Rubric idiom** (`orchestrator/salience.py`, `a06e428`): the Claude-tuned wording suppressed
  capable non-Claude judges. The neutral wording replaced it.
- **Scar EVENT-vs-STATE semantics** (`orchestrator/salience.py`, `d8d89a8`): the neutral wording
  left `scar` ambiguous between a new wound and current woundedness. R1 judges read it as
  woundedness and re-scarred every beat after the betrayal. The rubric now says a scar records a
  new wound from this exchange alone.
- **Silent event-impact fallback** (`orchestrator/salience.py`, `c1652b4`): an unparseable
  event judgment now logs a loud warning instead of quietly returning nothing.

The saved results behind this page are committed on `credibility-demo`: `docs/judge-audition/`
and the `replay_lich*.json` files in `docs/credibility-demo/`. The gaps are listed at the top of
this page. The raw server logs (`hydra_*.log`, `llama_*.log`) and
`docs/judge-audition/stage2_gemma-4-12b_lazy_draft.json` are untracked, so they exist only in the
owner's working folder.
