# Engine overview — what's built and how to use it

Two tracks. **Track V** is *how a character talks* (the voice runtime). **Track E** is *how a
character thinks and remembers* (the engine + memory — the north-star game-director seam).

This doc describes the `credibility-demo` branch, and says so where `main` or `game-rpg` differ.
[`project-status.md`](project-status.md) has the branch map.

---

## Track V — Voice (two paths, one chosen provider)

**Hume Octave** is the chosen TTS after a provider bake-off, but **no provider setting selects it**:
`GAME_TTS` defaults to `inworld`, `DEFAULT_TTS_PROVIDER` to `elevenlabs`, and no character YAML
sets `hume`. Only the credibility tools, and on `game-rpg` the RPG server, call Hume directly. The [README](../README.md#voice) explains how to turn it on.

Voice reaches a character by two paths, and they run very different amounts of mind:

- **Streaming pipeline** ([`pipeline.py`](../orchestrator/pipeline.py)). Only the port 8000
  Conversation app uses it. STT → LLM → sentence chunks → TTS, with the stages overlapping so
  speech starts while the LLM is still writing. **`Pipeline` does not use `Engine`**, so almost
  none of Track E reaches it. About 1.3 s to first audio was measured on 2026-06-24 with AssemblyAI
  streaming, before Hume. No end-to-end Hume measurement through this path exists.
- **Engine paths** (Ferry text game, mind server, and, on this branch, the credibility tools).
  `Engine.respond()` generates the whole reply, then the driver hands it to a TTS adapter, so
  there is no sentence overlap. The routes are `/api/game/{gid}/voice` for Ferry and `/speak` and
  `/speak_anim` on the mind server, which is what the Unreal client called. This is the path that
  runs the full mind.

| Capability | What it does | Where / how |
| --- | --- | --- |
| **Provider seam** | Each provider is one adapter behind `TTSAdapter`; the bake-off swapped providers with a one-line change and settled on Hume. `credibility-demo` also has a provider registry, described in [`tts-providers.md`](tts-providers.md). | `orchestrator/adapters/base.py`, `tts_*.py` |
| **Acting directions** | Hume on the Engine paths. Each utterance carries a per-utterance acting `description` (a character's own stage business becomes the delivery note), dynamic trailing silences, and cross-turn continuity (`context.generation_id`, scoped per adapter instance). Stage business only becomes direction when the raw whole reply reaches the adapter, which the pipeline doesn't do: it feeds Hume one cleaned sentence at a time. | `tts_hume.py` |
| **Streaming overlap** | Pipeline only. Sentence-chunk the LLM stream: TTS sentence 1 while the LLM still writes sentence 2. The latency tests on the full-loop spike found first audio dominated by the LLM's time-to-first-token, *not* TTS. | `orchestrator/pipeline.py`, `sentence_chunker.py` |
| **Model selection** | Pick the LLM per session — Sonnet for richer roleplay, Haiku for speed. Ferry and the mind server also take a per-game `reply_model`. | UI dropdown, `LLM_MODEL` |
| **Expressivity directive** | Per-provider prompt instructions (`VoiceProfile.directive`) on how to tag delivery for that voice. Inworld's says to lead sentences with vivid delivery tags and pause via `…`/`<break time="600ms"/>` (never `[pause]`); the expressive profiles share a rule to match energy to punctuation (`!`/`?`). These reach the model only on the pipeline and the full loop. `Engine.respond()` passes no provider, so Engine paths get no directive. | `orchestrator/expressivity.py` |
| **Face / lip-sync** *(explored, paused)* | Audio→ARKit-blendshape lip-sync behind `FaceAnimAdapter` (A2F → self-hosted NeuroSync) drove a MetaHuman face in Unreal. On pause. The Godot talk scene on `game-rpg` uses voice-amplitude motion instead. | `orchestrator/adapters/faceanim_neurosync.py`, mind server `/speak_anim` |

> **Not adopted:** an Inworld single-session **full-loop** runtime
> (`VOICE_RUNTIME=inworld_fullloop`, `orchestrator/realtime/`) was spiked for native cross-turn
> voice continuity but not taken up — the modular pipeline was kept. The code remains behind that
> flag. See the [superseded plan](track-v-full-loop-plan.md).

---

## Track E — Engine & memory (the north star)

How a character decides *what's relevant* and *what to remember*. The unit of work is a
`RespondRequest` (a player line and/or game event + the live `Situation`), not "a chat
message" — so the same engine drives any game.

### Where this runs
Everything in this section runs through the `Engine` class
([`engine.py`](../orchestrator/engine.py)). The Ferry text game, grid arena, mind server, Director's
Sandbox, `tools/` harnesses, and the unadopted full loop each build one. On `game-rpg`, so does the
Godot RPG (`game/rpg/minds.py`).

**The port 8000 Conversation app does not use `Engine`.** Its `Pipeline` has long-term recall,
salience scoring, and the always-on performance directive, and none of the rest: no relationship or
scars, intent, beliefs, commitments, contradiction detection, working memory, or deliberation. To
watch the full mind on port 8000, use the Director's Sandbox at `/sandbox`, which shares the process.

The validation results quoted below come from the `tools/stress_*` harnesses, last run in June 2026,
before the July judge changes. Their reports are gitignored, so they aren't in the repo. The newest
engine-level check is the offline 46-beat judge battery of 2026-07-17, which replays recorded replies
with no memories attached.

### The two seats: actor and judge
A character runs on two LLM roles with very different requirements.

- **Actor** writes what the character says. It's the adapter passed as `Engine(llm=...)`, and it's
  used only for the spoken reply. The engine calls `stream_reply(messages, system,
  cache_messages=True)`, so a custom adapter must accept that keyword.
- **Judge** decides what each moment means. Every appraisal goes through `judgment.complete()`
  ([`judgment.py`](../orchestrator/judgment.py)), which picks a model by role:

| Role | Setting | What it decides |
| --- | --- | --- |
| `salience` | `SALIENCE_MODEL` | The per-turn judgment (importance, feelings, scars, intent, detected promises), event impact, contradiction checks, emotional persistence, `choose_action` |
| `deliberation` | `DELIBERATION_MODEL` | `deliberate()` and goal reconciliation |
| `reflection` | `REFLECTION_MODEL` | Belief formation |

All three default to `claude-sonnet-4-6`, **the only model that has passed the 46-beat full-life
battery**. Haiku 4.5 and the DeepSeek models failed it; Sonnet 5 and Opus 4.8 have never run it. A
local model is viable for the actor seat. See
[`judge-seat-requirements.md`](judge-seat-requirements.md).

The judgment layer guards against a silent judge. Each call adds 2,048 tokens of thinking room on
top of its visible budget. If the reply still comes back empty, it retries once with 4,096 more,
then logs a warning and the caller falls back to neutral. These guards are on `main` and
`credibility-demo`, not `game-rpg`. One gap remains: `judgment()` salvages complete fields from
truncated JSON, but the main per-turn call doesn't go through it, so malformed JSON there silently
yields an importance and no relationship update.

On `credibility-demo` only, any judge role can name a model `local/<name>`, which routes to an
OpenAI-compatible server such as Ollama or llama-server (`LOCAL_JUDGE_BASE_URL`,
`LOCAL_JUDGE_API_KEY`). A local **actor** works only through the credibility tools
(`make_engine` in `tools/_harness.py`), with thinking off by default (`LOCAL_ACTOR_REASONING`),
because every game surface hard-codes the Anthropic adapter.

### Memory: relevance realization
Instead of "grab the most similar k", recall balances four competing pressures
(opponent-processing, inspired by Vervaeke's relevance realization):

```
base = w_sim·similarity + w_rec·strength + w_imp·importance     (then greedy + diversity penalty)
```

The default weights are 1.0, 0.35, and 0.7, and at most 6 memories are injected per turn.

- **similarity** — meaning-match to the arena query (with anisotropy "spreading").
- **strength** — temporal salience (see decay below).
- **importance** — character-aware salience: an LLM rates how memorable an exchange is *to
  this character* at write time (`orchestrator/salience.py`).
- **diversity** — a near-duplicate already picked is penalized, so recall isn't redundant.

The **arena query** (`context.py build_arena_query`) is what we search against: trigger +
recent turns + live `Situation` + the character's goals — not just the last line.

### Temporal decay + reinforcement (issue #5)
The **strength** pole models *forgetting*, over **in-game time**:

```
strength  = 0.5 ^ (Δt / half_life)
half_life = base_half_life · scale^importance · (1 + cap·boost / (cap + boost))
boost     = reinforce_gain · reinforcement
```

- **Game-agnostic clock.** The game supplies a single monotonic number (`Situation.clock`,
  or `t` on `remember`) — days, ticks, turns, seconds; the engine only takes differences.
  No clock → falls back to decay-by-memory-count, so nothing breaks.
- **Significance lasts.** `scale^importance` is super-linear: a trivial one-off fades within
  the base half-life; a life-saving moment (importance ≈ .95) stays *vivid* for in-game
  years.
- **Reinforcement.** Re-encountering a fact (or recalling it, if `REINFORCE_ON_RECALL` is on)
  bumps a count and resets "last seen", so rehearsed memories resist decay. The stretch
  saturates: one reinforcement gives 1.92×, twelve give 7×, and the ceiling is 13× at defaults,
  so endless recall can't make a memory permanent. The simulation shows this is *selective* —
  it keeps revisited memories alive without inflating never-revisited ones.

### Commitments (issue #4)
A **commitment** (promise / deal / constraint — "meet at dawn", "never tell anyone the
player's name") is a *standing concern*, not a decaying memory. While **open** it's injected
into the prompt every turn, so the character always knows its active obligations, though whether
it keeps them is up to who it is. It doesn't decay or fall out of context. When it **closes** (the
game marks it fulfilled/broken, or it **expires** past its due clock) it converts into an ordinary
decaying memory of the outcome, inheriting its **significance** — a high-stakes betrayal stays
vivid for in-game years; a trivial broken promise fades. The game owns it via `Engine.commit()` /
`resolve_commitment()` (siblings of `remember`); `commit()` returns the `Commitment` whose `id`
closes it. `tools/commitment_scenarios.py` sweeps the lifecycle across timetables. With
`COMMITMENT_DETECTION` on, the engine also auto-detects commitments the character makes in
dialogue (folded into the per-turn judgment call — no extra round-trip), opt-in since it's
fuzzier than the explicit API. The same flag decides whether the judge sees open promises. It's
off on this branch's game surfaces unless set in `.env`, and `tools/credibility_lich.py` turns
it on. On `game-rpg`, the Godot RPG forces it on (`game/rpg/minds.py`).

### Relationship state (issue #6)
A character's feelings toward the player — **affection / trust / respect** (movement from a
baseline) plus an acute **mood** — that **evolve with the interaction** on top of the static
disposition. Updated by the folded per-turn judgment call, **character-aware** (pleasantries roll
off a guarded Corvin; only proven/costly acts move him, slowly — a warm Bri moves more readily).
It's RR-core: the stance folds into the **arena query**, so a wary character *recalls* a different
past (deception/threat) than a fond one. Behavioral payoff is visible — low trust → deflect/guard,
high trust → engage/help. `RELATIONSHIP_STATE` defaults off, but every game surface and the Sandbox
force it on in code. Scars, world-event impact, and self-driven change all sit under this one flag.

**Asymmetry + permanent scars.** Axes update *asymptotically* (saturating), so the extremes are
hard-won (a warm character no longer pins to 1.00 in five beats) and a betrayal from high trust
craters harder. Trust is **lost fast, regained slowly** — recovery after real damage is grinding
and *sacrifice-gated* (validated over ~3 in-game years: words ≈ nothing, favors are met with
suspicion then grudging, only sustained costly proof rebuilds — the reflection's job, character-
aware). And a deep betrayal leaves a **permanent scar** (issue #16): the judge assigns a
per-axis `scar` (0–1 = fraction of that axis put permanently out of reach) — *the AI chooses which
axes and how deep from character × betrayal-type, never a formula* (a business double-cross scars a
schemer's trust but spares his respect; a romantic betrayal scars trust, respect, *and* affection).
A `scar` records a **new wound from this exchange alone**: existing scars are already listed in the
character's standing and must not be restated, so an exchange that merely touches an old wound adds
nothing. That rule is in the judge's wording on `credibility-demo` only (`d8d89a8`, 2026-07-17).
The axis can rebuild only up to its ceiling (`1 − scar`), and a caution note stays in the prompt so
the wound shapes behavior even once the number climbs back. A scar can also **heal** (issue #17), but
only the hard way: the judge emits a per-axis `scar_heal` *exclusively* for **extraordinary,
wound-relevant proof** — it lifts a fraction (`scar *= 1 − heal`), so a trace normally lingers,
though nothing in the code stops a heal of 1.0 from erasing the scar outright. The betrayal
*memory* is never erased ("trust again, knowing what they did"), and a **safeguard ignores any heal
below 0.15** so words, time, and ordinary favors lift nothing and trivial acts can't accumulate
into forgiveness. In the June demo the AI judged by *relevance to the wound*, not magnitude (serving the prison term
your double-cross caused lifted the trust scar; an unrelated heroic act didn't), but the rubric doesn't require it: it asks only for extraordinary, costly proof.

**World events + time (issue #12).** Disposition no longer moves *only* through conversation, as
long as `relationship_state` is on. **(A)**
A player-attributable **world event** the game pushes (`remember(fact, player_role="caused" |
"benefited")`) shifts disposition too — the AI judges the character-aware impact (deltas + a possible
scar), weighing *indirect* blame in character (the player's faction burning your warehouse craters
trust and scars; their crew clearing your debt warms you). **(B)** Feelings **drift toward the
character's baseline disposition over in-game time** (lazy, on next contact): warmth fades if
neglected, a transient hurt cools off — but a **scar holds the line** (time never heals a betrayal;
only earned proof does). The drift rate is **per-character** (an AI-derived "emotional persistence"
from temperament, cached, further resisted by bond depth), and band-gated so it never reads as a
ticking meter. Because baseline = *their disposition*, a warm character fades back to warm, never to
cold.

**Self-driven change (issue #19).** Disposition can also shift from the character's **own** internal
change, with the **player doing nothing** — `remember(fact, actor="self")`. With
`relationship_state` on, the AI judges a *genuine,
hard-won transformation* (Corvin takes monastic vows and, after years of reflection, lets go of the
grudge) and can **warm disposition and heal a scar** — forgiveness the character reaches on their own
— while a passing mood changes nothing (the same `scar_heal` threshold + gating apply). This is the
seam a game with **autonomous NPC lives** drives: the game supplies the narrative ("he became a
monk"), the engine enacts the inner change. It's the *applier* half of NPC autonomy; the *generator*
half — the character deliberating and *deciding* such changes unprompted — is #20 below.

### Autonomous agency — the character decides on its own (issue #20)
The *generator* half of a living NPC. The **game** calls `Engine.deliberate(situation, mode=…)`
whenever it wants — **no engine cadence** — and the character, *between scenes with the player
absent*, decides what (if anything) it does or becomes from **everything that's accumulated**
(memory, beliefs, relationship + scars, intent, goals, elapsed time). The engine **applies the
inner half** through the seams already built — a change of heart via the #19 self-change path, an
updated intent, **evolved standing goals** — and **returns** the Decision so the game can enact any
`world_action` in its world. Default **`free`** mode lets the RR-grounded character act as it best
sees fit each tick; **`gated`** mode makes a real change need accumulated *cause* (most calls return
`changed:false`, plus a cheap structural skip) — for games that want a controlled/on-rails
environment or to minimize cost. The grounding *is* the guardrail: decisions are in-character, never
arbitrary. The autonomy-loop stress pass found the **counter-intuitive result that `free` is the
*more* coherent, identity-preserving mode**: by reconsidering each tick it *metabolizes every life
event* into a continuous, grounded evolution, where gated can only batch (holding a fixed plan and
skipping the texture between big jumps — and it can lock in an early, hot decision). So free is the
default; gating is the opt-in *constraint*, not the baseline. Validated over a full life (judge:
free recognizable 0.95, *"cynicism deepens into methodology; abbey exit is earned, not a betrayal of
self"*). Together with #19, this is the engine's bridge from *animating characters on demand* to
**NPCs that live their own lives**.

On this branch, only the Ferry text game, the Sandbox, and the tools call `deliberate()`. The arena
and the mind server use `choose_action` instead. On `game-rpg`, the RPG calls it too. Each real
deliberation costs a decision LLM call plus a goal-reconciliation call, plus an event-impact call
if an `internal` change is applied. A failed call returns only `{"changed": false}` and doesn't
advance the taken-stock clock, so its events get considered next time.

*Grounding + sticky trust (issues #21/#22).* The deliberation is grounded in the player's *actual*
activity — what they really did, plus an explicit note when they've been absent — so it interprets
real events naturally (human conflation is fine) but doesn't **fabricate** contact that never
happened. And player-**trust** is *sticky*: it moves only on real player acts (or `player_role` world
events), or a **coherent, decisive** autonomous reckoning — never on per-tick mood jitter, and decay
fades it smoothly toward baseline over absence rather than wobbling. How the character reads the
player's *absence* is left to relevance realization, not a rule: a **promise taken to heart** (or
warmth the character read *as* a promise — people do that) can sting or wound when the player goes
silent, while **passing contact** just drifts to neutral — and the character reacts *as they would*,
not as a fair arbiter would (validated: promises-Bri craters to 0.17 + scars; passing-Bri holds at
0.50, no scar).

That absence note is **rhythm-aware** (unrelated to `orchestrator/cadence.py`, which calibrates
speech turn timing): it weighs the gap since the player's last act against the
*rhythm* of real contact, not against zero. A gap of up to twice the median interval between
contacts reads as **presence**; only a gap that outruns the established rhythm reads as
pulling-away; and a single establishing contact with
nothing since is genuine, growing absence. Without this, a *loyal, frequently-polled* player was
misread as absent on every off-visit tick and saw earned trust collapse — caught by the Opus
grounding judge over a 6-character / 42-arc variation run (`tools/stress_variation.py`,
`--quick` for the regression canary). After the fix, a loyal weekly-present player **earns** trust
(0.08 → 0.92) while real betrayal still craters (player-betrayal → trust 0.0, scar 1.0) and the
shrug-vs-wound spread on passing contact is unchanged. That same run established the headline result:
**two uncoached "wildcard" characters** produced the full shrug-vs-wound range from their own
psychology — the variation is the engine's, not the authoring's.

### Goal reconciliation (#29)
The `new_goals` in a deliberation are only a proposal. A second, focused LLM call
(`reconcile_goals` in [`agency.py`](../orchestrator/agency.py)) is the **single authority on
standing goals**. It goes through them one by one and keeps, softens, replaces, or drops each,
treating the deliberation's proposal as strong input. It was split out because, folded into the big
decision JSON, goal revision competed with everything else and under-fired. It runs on every real
deliberation, even when `changed` is false, because goals can be stale against change that already
happened. A goal that moves sets `changed` to true.

It's deliberately conservative. A goal core to who the character is can persist against pressure,
and that tension is allowed to drive conflict later, even betrayal. It also anchors on existing
wording, so goals don't churn. Evolved goals are stored per character, then override the sheet's
goals in the prompt ("# What you want now") and in the arena query. The code comments flag this
second call as a candidate to gate for production.

### `choose_action` — the embodied-action seam (#30)
`Engine.choose_action(situation, options)` picks the one thing a character does right now, **only
from the options the game offers**, so it can never do something the world doesn't afford. It's one
judge call with no flag, grounded in who the character has become: evolved goals, near-term aim,
feelings and scars, and beliefs. It returns `{action, reason, expression, face}`, where `action` is
an exact option or `None`, and `face` is `neutral`, `happy`, `sad`, `angry`, `fear`, or `surprise`.
The game executes the choice and renders or ignores the face. Empty `options` returns only
`{action: None, reason: ""}`.

### Evolving intent (issue #8)
The character's **immediate short-term aim** with the player — a concrete agenda *from their
POV* ("find out who sent them", "keep them close tonight", "test if they can be trusted with
the ledger") that sits **on top of** their standing profile goals and **evolves** with the
scene and their feelings. Set in the same folded judgment call, persisted per character.
`INTENT_STATE` defaults off, but every game surface and the Sandbox force it on. It turns reaction
into **agency**: injected so the character pursues the aim
without announcing it, and folded into the **arena query** so recall serves the aim — RR
again: relevance is relative to the agent's *goals*, so intent conditions both behavior and
what past is retrieved, just as relationship (#6) conditions caring. **Character-aware**: the
same approach grows a schemer's probe in Corvin and a toying test in Bri.

### Reflection / consolidation — beliefs (issue #9)
Periodically the engine compresses raw exchanges into higher-level **beliefs** — the
through-lines a character forms from experience (*"either a trap or the one person I've waited
years for"*, *"no one down here is what they seem"*). An **importance-accumulation trigger**
(generative-agents style) fires one LLM call once enough has happened since the last
reflection (`REFLECTION_ENABLED` defaults off, and every game surface and the Sandbox force it on);
each belief is stored as an ordinary memory
(`kind="belief"`) with **high importance**, so it persists (long decay half-life — beliefs are
through-lines, not trivia) and **resurfaces through the normal arena query**, no separate path.
It's **character-aware** (the same loyal-player events make schemer Corvin *suspicious* and
honest Bri *warm*) and can **deepen/revise** the beliefs already held. RR-core: forming
higher-order abstractions *is* relevance realization — the agent compresses episodes into
convictions that bear on its goals more than any single line, and those convictions then
condition what it later finds relevant and how it behaves. Beliefs render in their **own prompt
section** ("What you've come to believe", issue #14) — distinct from recalled exchanges — and the
**top few are always surfaced** so convictions colour every turn, not only when a query happens to
recall one. The set stays tight: a new belief that's a near-duplicate of an existing one
**supersedes** it, and the total is **capped** (oldest evicted), so beliefs don't pile up as
reworded variants (issue #15).

### Knowledge boundaries + contradiction detection (issue #10)
A character knows only **its profile + what it actually lived with the player** (its memories) —
it is **not omniscient**. An always-on performance directive enforces this: asked about something
outside its world, expertise, or memory, it is **honestly ignorant in character** (*"WiFi? The hell
is that?"*) instead of fabricating, and it **refuses a fake shared past** (*"Mallorca. Never been —
and I'd remember a beach trip"*). The same directive makes it **notice contradictions**: if the
player asserts something that clashes with what it knows, it pushes back in character (*"Castel?
You told me Joran not two minutes ago"*). On top of that, opt-in **`CONTRADICTION_DETECTION`** runs
a post-reply check (only when memories were recalled) that **records** a
caught contradiction — claim vs established fact — as a salient memory, so a lie is carried forward
and feeds future recall + wariness. RR: a contradiction is high-relevance to a wary agent.

### Working memory (#30)
Recall can miss what just happened, so the engine also foregrounds it. Each turn,
`_recent_happenings` picks world and player events, plus the character's own decisions and changes
of heart, that fall within `RECENT_HAPPENINGS_WINDOW` of the clock and score at least 0.6 on
importance. It skips anything recall already surfaced, keeps at most 3 of each group, and renders
them under `# What's happening right now`. It needs a game clock. It's additive, so it doesn't use
up the recall budget or the short-term window, and items fade back into ordinary recall as the
scene moves on. The window is in the game's clock units and needs tuning per game: make it at least
as wide as a typical between-scene time skip. A scenario's `clock.recent_happenings_window`
overrides it on the three game surfaces.

### The seam (engine ↔ game)
[`engine-game-contract.md`](engine-game-contract.md) is the full integration contract. The surface:

- `respond(RespondRequest)` — one conversational turn: recall, generate, then judge.
- `prepare()` / `reflect()` — the two halves of `respond()`, for a host that generates the reply
  itself. Besides the unadopted full loop, only `tools/stress_suite.py` calls `prepare()` directly, to capture the injected context.
- `remember(fact, ...)` — the game pushes a durable world event into a character's memory and gets
  back its salience.
- `commit()` / `resolve_commitment()` — the game declares / closes a character's obligations.
- `deliberate(situation, mode=...)` — the character decides on its own between scenes. The engine
  applies the inner change and returns the decision.
- `choose_action(situation, options)` — the character picks one action the game offers.
- `flush_reflection()` — waits for background judgment to land. Call it at the end of a scene or
  run when `background_reflection` is on.
- `Situation` — transient "what's true now" (location, time, who's present, recent events,
  and the numeric `clock`), pushed per turn.
- `EngineCaps` — the engine's capability snapshot, below.

### Capabilities: `EngineCaps`
Each `Engine` takes a frozen snapshot of its behavior flags at construction: an `EngineCaps`
([`config.py`](../orchestrator/config.py)). `.env` supplies the process-wide defaults, and a driver
overrides them per engine with `EngineCaps.from_settings(get_settings(), relationship_state=True)`.
So one surface can't flip another's capability flags, and two engines with different capabilities can
share a process. Judge model ids stay process-global: any Sandbox call resets them to its own picker.

This means `.env` isn't the last word. The Ferry game, arena, mind server, and Sandbox all force
`relationship_state`, `reflection_enabled`, and `intent_state` on in code, so setting those in `.env`
has no effect there. The first three also force `background_reflection` on, because they're
long-lived servers. The Sandbox doesn't, so each state it returns already includes that turn's
judgment. `salience_scoring` only gates the standalone salience call, which needs both the cap and the global setting on. The folded per-turn judgment ignores both, so neither is a kill switch on a surface with relationship, intent, or commitment flags on. `deliberate()` and `choose_action()` have no flag at all.

### What's on disk
A character's mind is five files in `.memory/` (`MEMORY_DIR`), named after its `memory_namespace`,
which is how it survives a restart:

| File | Holds |
| --- | --- |
| `<namespace>.jsonl` | Long-term memories, including beliefs and decisions. Embeddings aren't stored; they're rebuilt at load |
| `<namespace>.commitments.jsonl` | Commitments, open and closed |
| `<namespace>.relationship.json` | Feelings, mood, scars, persistence half-life |
| `<namespace>.intent.json` | The current near-term aim |
| `<namespace>.agency.json` | Evolved goals and the last-deliberation clock |

Whole-file writes are atomic (temp file, fsync, replace), a new long-term memory is a plain append to the JSONL, and each file has one lock shared across the
process. A corrupt JSON store is moved aside to `<file>.corrupt-<timestamp>` and logged as an error,
never silently reset. Corrupt lines in a JSONL store are skipped and logged. The short-term buffer
isn't persisted.

---

## Examples

Anything that talks to a character bills your LLM key.

To drive the full mind, call `Engine` from Python. This writes to the character's real files in
`.memory/`, and the `await` lines belong inside an async function:

```python
from orchestrator.adapters.llm_anthropic import AnthropicLLM
from orchestrator.character_store import load_character
from orchestrator.config import EngineCaps, get_settings
from orchestrator.context import RespondRequest, Situation
from orchestrator.engine import Engine

caps = EngineCaps.from_settings(get_settings(), relationship_state=True,
                                reflection_enabled=True, intent_state=True)
eng = Engine(load_character("brielle-bri-castellano"), AnthropicLLM(), caps=caps)

# Push a durable world event, stamped with the game clock. `importance` pins its weight;
# leave it out and the character appraises the event itself.
await eng.remember("the player saved Bri from the harbor fire", importance=0.95, t=120,
                   player_role="caused")

# Drive a turn with live situation + clock (so recall decays against in-game time):
reply = await eng.respond(RespondRequest(player_input="remember me?",
    situation=Situation(location="the docks", clock=120, present=["Marco"])))

# Give the character an obligation (always injected until it closes); break it later:
c = eng.commit("meet the player at the harbor at dawn", importance=0.85, due_t=130,
               parties=["the player"])
await eng.resolve_commitment(c.id, "broken", t=131)
```

The port 8000 Conversation app exposes its WebSocket in the browser console as `__ws`. That path is
memory-only. `remember` writes straight to long-term memory, so `player_role` and `actor` do nothing
there, and importance is 0.7 unless you send one:

```js
// Push a durable world event, stamped with the game clock (decays slowly — high importance):
__ws.send(JSON.stringify({ type:"remember",
  fact:"the player saved Bri from the harbor fire", importance:0.95, t:120 }))

// Drive a turn with live situation + clock (so recall decays against in-game time):
__ws.send(JSON.stringify({ type:"text", text:"remember me?",
  situation:{ location:"the docks", clock:120, present:["Marco"] } }))
```

The `commit` and `resolve_commitment` WebSocket messages exist only on the unadopted full loop
(`VOICE_RUNTIME=inworld_fullloop`). The default path ignores them, so use the `Engine` methods.

These two are pure computation, so they're free:

```bash
# See the decay curves + "years later" recall:
python -m tools.decay_demo

# Simulate a long game to vet recall-as-reinforcement:
python -m tools.recall_reinforce_sim
```

## Config quick-reference (set in `.env`, then restart)

"Engine surfaces" below means the Ferry game, arena, mind server, Sandbox, and tools. None of these
flags changes `Pipeline` unless the table says so. For how game surfaces override `.env`, see
[`EngineCaps`](#capabilities-enginecaps).

**Off by default**

| Flag | Applies to | What it does |
| --- | --- | --- |
| `RELATIONSHIP_STATE` | Engine surfaces. Forced on by the game surfaces and Sandbox | Evolving affection/trust/respect + mood toward the player, plus scars, world-event impact, and self-driven change |
| `INTENT_STATE` | Engine surfaces. Forced on by the game surfaces and Sandbox | The character's evolving near-term aim |
| `REFLECTION_ENABLED` | Engine surfaces. Forced on by the game surfaces and Sandbox | Consolidates exchanges into beliefs |
| `BACKGROUND_REFLECTION` | Engine surfaces. Forced on by Ferry, arena, and mind server | Runs the post-reply judgment as a background task, so the player doesn't wait for it |
| `COMMITMENT_DETECTION` | Engine surfaces, when set in `.env` or by a tool | Auto-detects commitments the character makes in dialogue, and shows the judge open promises |
| `CONTRADICTION_DETECTION` | Engine surfaces, when set in `.env` | Records a caught contradiction as a memory, when memories were recalled |
| `REINFORCE_ON_RECALL` | All recall, including `Pipeline` | Recalling a memory rehearses it (slows decay), and writes the store on each retrieve |
| `MEMORY_DEBUG` | `Pipeline` and the full loop | Emits the 🧠 score panel each turn (shows `str` / `↺N` / `t`) |
| `MEMORY_READONLY` | `Pipeline` (long-term memory only) and the full loop | Freezes writes for controlled A/B. Engine surfaces ignore it; use `Engine(readonly=True)` |

**On by default**

| Flag | Applies to | What it does |
| --- | --- | --- |
| `SALIENCE_SCORING` | Standalone salience calls: `Pipeline`, and `Engine` paths with no relationship, intent, or commitment flag | An LLM rates how memorable each moment is to this character. Off stores a flat 0.5 on those paths. On game surfaces the folded per-turn judgment still rates exchanges, and an unpinned `Engine.remember()` stores 0.7 |
| `ARENA_QUERY` | All recall, including `Pipeline` | Searches on the trigger + recent turns + `Situation` + goals. Off searches the last line only |
| `RELATIONSHIP_TIME_DECAY` | Engine surfaces, with `relationship_state` on | Feelings drift toward baseline over in-game time; scars hold |
| `RECENT_HAPPENINGS` | Engine surfaces | Working-memory foregrounding |

**Models and providers**

| Setting | Default | What it does |
| --- | --- | --- |
| `VOICE_RUNTIME` | `pipeline` | Keep this. `inworld_fullloop` is the spiked-but-not-adopted agent |
| `LLM_MODEL` | `claude-sonnet-4-6` | Default actor wherever no model is passed: port 8000, plus Ferry, arena, and mind server without a `reply_model`. The port 8000 dropdown overrides it per session |
| `SALIENCE_MODEL` | `claude-sonnet-4-6` | Judge: the `salience` role |
| `DELIBERATION_MODEL` | `claude-sonnet-4-6` | Judge: the `deliberation` role |
| `REFLECTION_MODEL` | `claude-sonnet-4-6` | Judge: the `reflection` role |
| `LOCAL_JUDGE_BASE_URL` | `http://127.0.0.1:8080/v1` | Server for `local/<name>` models (`credibility-demo` only). Ollama uses port 11434 |
| `LOCAL_JUDGE_API_KEY` | empty | Sent as a bearer token when set |
| `LOCAL_ACTOR_REASONING` | `none` | Thinking for a local actor in the credibility tools. `none` turns it off |
| `DEFAULT_TTS_PROVIDER` | `elevenlabs` | Port 8000, when a character sets no provider. Every shipped YAML sets one, so to use Hume there, set `tts_provider: hume` in the YAML |
| `GAME_TTS` | `inworld` | Game and mind server voice. Ferry's voice route works only with `hume` |
| `REALTIME_LLM_MODEL` | `anthropic/claude-haiku-4-5` | Full-loop LLM (only used by the not-adopted `inworld_fullloop`) |
| `REALTIME_DELIVERY_MODE` | `CREATIVE` | tts-2 expressiveness (full-loop only) |

`LOCAL_*` exist on `credibility-demo` only. They and `GAME_TTS` are read straight from the process
environment. The game server and tools load `.env` into it, but `orchestrator.main` doesn't, so for
port 8000 set `LOCAL_*` in your shell.

**Tuning**

| Setting | Default | What it does |
| --- | --- | --- |
| `RR_DECAY_HALF_LIFE` | 30 | Base half-life in the **game's** time units |
| `RR_DECAY_IMPORTANCE_SCALE` | 50 | Half-life ×= `scale^importance` (significance → near-permanent) |
| `RR_DECAY_REINFORCE_GAIN` | 1.0 | Initial slope of reinforcement: small N stretches the half-life by about `1 + gain·N` |
| `RR_DECAY_REINFORCE_CAP` | 12 | Reinforcement saturates at `1 + cap` times the half-life |
| `RELATIONSHIP_DECAY_HALF_LIFE` | 180 | Drift half-life until the character's own persistence is assessed |
| `RELATIONSHIP_DECAY_BOND_RESIST` | 0.05 | Each shaping turn extends the drift half-life by this fraction |
| `REFLECTION_IMPORTANCE_THRESHOLD` | 3.0 | Accumulated importance that triggers belief formation |
| `BELIEF_MAX` | 6 | Most beliefs a character holds; the oldest is evicted |
| `BELIEFS_ALWAYS_SURFACE` | 2 | Beliefs injected every turn, recalled or not |
| `RECENT_HAPPENINGS_WINDOW` | 1.0 | Working-memory freshness, in the game's clock units. Tune per game |
| `RECENT_HAPPENINGS_SALIENCE_FLOOR` | 0.6 | Lowest importance that counts as top of mind |
| `RECENT_HAPPENINGS_CAP` | 3 | At most this many events and this many own acts |

See [`relevance-scoring.md`](relevance-scoring.md) for the full memory-scoring detail, every recall
weight, and how to read the debug panel, [`engine-game-contract.md`](engine-game-contract.md) for
how a game integrates, and [`architecture-seams.md`](architecture-seams.md) for the engine/game seam
design.
