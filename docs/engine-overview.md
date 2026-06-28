# Engine overview — what's built and how to use it

Two tracks. **Track V** is *how a character talks* (the voice runtime). **Track E** is *how a
character thinks and remembers* (the engine + memory — the north-star game-director seam).

---

## Track V — Voice runtime (Inworld full loop) — on `main`

One Inworld Realtime session owns the whole loop: speech-in → LLM → speech-out, with
cross-turn voice continuity. Enabled with `VOICE_RUNTIME=inworld_fullloop` (the default
runtime is still the older modular STT→LLM→TTS pipeline until the Phase-3 cutover).

| Capability | What it does | Where / how |
| --- | --- | --- |
| **Per-turn memory recall (§5.6)** | The voice loop retrieves + injects relevant memories every turn — the same relevance realization the modular path had. | `orchestrator/main.py` `run_full_loop` |
| **Model selection** | Pick the routed LLM per session. gpt-4o ≈ 1.1s to first audio, Haiku 4.5 ≈ 2.4s. First-audio latency is dominated by the LLM's time-to-first-token through Inworld, *not* TTS. | UI dropdown, `?realtime_llm=openai/gpt-4o`, or `REALTIME_LLM_MODEL` |
| **Delivery mode** | tts-2 expressiveness: Stable / Balanced / **Creative** (default). | UI "Voice delivery" dropdown, `?delivery=`, or `REALTIME_DELIVERY_MODE` |
| **Expressivity directive** | Drives the model to tag *every sentence* vividly, match intensity to punctuation (`!`/`?`), pause via `…`/`<break time="600ms"/>` (never `[pause]`), and lead/weave vocatives (not trailing pet-names). | `orchestrator/expressivity.py` |
| **Barge-in** | Talk over the character and she stops instantly (browser silences playback; server cancels the response + clears queued audio). | `InworldSession.interrupt`, `main.py` |
| **Reconnect** | If the Inworld session drops, it auto-rebuilds (backoff) and replays recent dialogue so the character keeps the thread. | `run_full_loop` supervisor |

**Key fact learned:** in the full loop the model's text/tags hit tts-2 **raw** (no modular
cleanup), so voice quality is controlled in the *prompt/profile* — tag richness, pause
syntax, and vocative placement all matter.

---

## Track E — Engine & memory (the north star)

How a character decides *what's relevant* and *what to remember*. The unit of work is a
`RespondRequest` (a player line and/or game event + the live `Situation`), not "a chat
message" — so the same engine drives any game.

### Memory: relevance realization
Instead of "grab the most similar k", recall balances four competing pressures
(opponent-processing, inspired by Vervaeke's relevance realization):

```
base = w_sim·similarity + w_rec·strength + w_imp·importance     (then greedy + diversity penalty)
```

- **similarity** — meaning-match to the arena query (with anisotropy "spreading").
- **strength** — temporal salience (see decay below).
- **importance** — character-aware salience: an LLM rates how memorable an exchange is *to
  this character* at write time (`orchestrator/salience.py`).
- **diversity** — a near-duplicate already picked is penalized, so recall isn't redundant.

The **arena query** (`context.py build_arena_query`) is what we search against: trigger +
recent turns + live `Situation` + the character's goals — not just the last line.

### Temporal decay + reinforcement (issue #5 — just built)
The **strength** pole models *forgetting*, over **in-game time**:

```
strength  = 0.5 ^ (Δt / half_life)
half_life = base_half_life · scale^importance · (1 + reinforce_gain · reinforcement)
```

- **Game-agnostic clock.** The game supplies a single monotonic number (`Situation.clock`,
  or `t` on `remember`) — days, ticks, turns, seconds; the engine only takes differences.
  No clock → falls back to decay-by-memory-count, so nothing breaks.
- **Significance lasts.** `scale^importance` is super-linear: a trivial one-off fades within
  the base half-life; a life-saving moment (importance ≈ .95) stays *vivid* for in-game
  years.
- **Reinforcement.** Re-encountering a fact (or recalling it, if `REINFORCE_ON_RECALL` is on)
  bumps a count and resets "last seen", so rehearsed memories resist decay. The simulation
  shows this is *selective* — it keeps revisited memories alive without inflating
  never-revisited ones.

### Commitments (issue #4)
A **commitment** (promise / deal / constraint — "meet at dawn", "never tell anyone the
player's name") is a *standing concern*, not a decaying memory. While **open** it's injected
into the prompt every turn, so the character always honors its active obligations; it doesn't
decay or fall out of context. When it **closes** (the game marks it fulfilled/broken, or it
**expires** past its due clock) it converts into an ordinary decaying memory of the outcome,
inheriting its **significance** — a high-stakes betrayal stays vivid for in-game years; a
trivial broken promise fades. The game owns it via `commit` / `resolve_commitment` (siblings
of `remember`); `tools/commitment_scenarios.py` sweeps the lifecycle across timetables. With
`COMMITMENT_DETECTION` on, the engine also auto-detects commitments the character makes in
dialogue (folded into the background salience call — no extra round-trip), opt-in since it's
fuzzier than the explicit API.

### Relationship state (issue #6)
A character's feelings toward the player — **affection / trust / respect** (movement from a
baseline) plus an acute **mood** — that **evolve with the interaction** on top of the static
disposition. Updated in the background (folded into the salience call, `RELATIONSHIP_STATE`
opt-in), **character-aware** (pleasantries roll off a guarded Corvin; only proven/costly acts
move him, slowly — a warm Bri moves more readily). It's RR-core: the stance folds into the
**arena query**, so a wary character *recalls* a different past (deception/threat) than a fond
one. Behavioral payoff is visible — low trust → deflect/guard, high trust → engage/help.

**Asymmetry + permanent scars.** Axes update *asymptotically* (saturating), so the extremes are
hard-won (a warm character no longer pins to 1.00 in five beats) and a betrayal from high trust
craters harder. Trust is **lost fast, regained slowly** — recovery after real damage is grinding
and *sacrifice-gated* (validated over ~3 in-game years: words ≈ nothing, favors are met with
suspicion then grudging, only sustained costly proof rebuilds — the reflection's job, character-
aware). And a deep betrayal leaves a **permanent scar** (issue #16): the reflection assigns a
per-axis `scar` (0–1 = fraction of that axis put permanently out of reach) — *the AI chooses which
axes and how deep from character × betrayal-type, never a formula* (a business double-cross scars a
schemer's trust but spares his respect; a romantic betrayal scars trust, respect, *and* affection).
The axis can rebuild only up to its ceiling (`1 − scar`), and a caution note stays in the prompt so
the wound shapes behavior even once the number climbs back. A scar can also **heal** (issue #17), but
only the hard way: the reflection emits a per-axis `scar_heal` *exclusively* for **extraordinary,
wound-relevant proof** — it's asymptotic (`scar *= 1 − heal`, a faint trace lingers), the betrayal
*memory* is never erased ("trust again, knowing what they did"), and a **safeguard ignores any heal
below a threshold** so words, time, and ordinary favors lift nothing and trivial acts can't accumulate
into forgiveness. The AI judges by *relevance to the wound*, not magnitude (serving the prison term
your double-cross caused lifts the trust scar; an unrelated heroic act doesn't).

**World events + time (issue #12).** Disposition no longer moves *only* through conversation. **(A)**
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
change, with the **player doing nothing** — `remember(fact, actor="self")`. The AI judges a *genuine,
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

### Evolving intent (issue #8)
The character's **immediate short-term aim** with the player — a concrete agenda *from their
POV* ("find out who sent them", "keep them close tonight", "test if they can be trusted with
the ledger") that sits **on top of** their standing profile goals and **evolves** with the
scene and their feelings. Set in the same background call (`INTENT_STATE` opt-in), persisted
per character. It turns reaction into **agency**: injected so the character pursues the aim
without announcing it, and folded into the **arena query** so recall serves the aim — RR
again: relevance is relative to the agent's *goals*, so intent conditions both behavior and
what past is retrieved, just as relationship (#6) conditions caring. **Character-aware**: the
same approach grows a schemer's probe in Corvin and a toying test in Bri.

### Reflection / consolidation — beliefs (issue #9)
Periodically the engine compresses raw exchanges into higher-level **beliefs** — the
through-lines a character forms from experience (*"either a trap or the one person I've waited
years for"*, *"no one down here is what they seem"*). An **importance-accumulation trigger**
(generative-agents style) fires one background LLM call once enough has happened since the last
reflection (`REFLECTION_ENABLED` opt-in); each belief is stored as an ordinary memory
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
a background check (off the critical path, only when memories were recalled) that **records** a
caught contradiction — claim vs established fact — as a salient memory, so a lie is carried forward
and feeds future recall + wariness. RR: a contradiction is high-relevance to a wary agent.

### The seam (engine ↔ game)
- `remember` — the game pushes a durable world event into a character's memory.
- `commit` / `resolve_commitment` — the game declares / closes a character's obligations.
- `Situation` — transient "what's true now" (location, time, who's present, recent events,
  and the numeric `clock`), pushed per turn.
- Memory persists per character at `.memory/<slug>.jsonl`.

---

## Examples (drive it from the browser console via `__ws`)

```js
// Push a durable world event, stamped with the game clock (decays slowly — high importance):
__ws.send(JSON.stringify({ type:"remember",
  fact:"the player saved Bri from the harbor fire", importance:0.95, t:120 }))

// Drive a turn with live situation + clock (so recall decays against in-game time):
__ws.send(JSON.stringify({ type:"text", text:"remember me?",
  situation:{ location:"the docks", clock:120, present:["Marco"] } }))

// Give the character an obligation (always injected until it closes); break it later:
__ws.send(JSON.stringify({ type:"commit",
  text:"meet the player at the harbor at dawn", importance:0.85, due_t:130, parties:["the player"] }))
__ws.send(JSON.stringify({ type:"resolve_commitment", id:"<id from 'committed'>", status:"broken", clock:131 }))
```

```bash
# See the decay curves + "years later" recall (pure computation, no billing):
python -m tools.decay_demo

# Simulate a long game to vet recall-as-reinforcement:
python -m tools.recall_reinforce_sim

# A/B a model live in the browser:
#   http://127.0.0.1:8000/?realtime_llm=openai/gpt-4o
```

## Config quick-reference (set in `.env`, then restart)

| Flag | Default | What it does |
| --- | --- | --- |
| `VOICE_RUNTIME` | `pipeline` | `inworld_fullloop` enables the voice loop |
| `REALTIME_LLM_MODEL` | `anthropic/claude-haiku-4-5` | full-loop LLM |
| `REALTIME_DELIVERY_MODE` | `CREATIVE` | tts-2 expressiveness |
| `MEMORY_DEBUG` | off | emit the 🧠 score panel each turn (shows `str` / `↺N` / `t`) |
| `MEMORY_READONLY` | off | freeze all stores (for controlled A/B — writes become no-ops) |
| `REINFORCE_ON_RECALL` | off | recalling a memory rehearses it (slows decay) |
| `COMMITMENT_DETECTION` | off | auto-detect commitments a character makes in dialogue (folded into salience) |
| `RELATIONSHIP_STATE` | off | evolving affection/trust/respect + mood toward the player (folded into salience; conditions recall) |
| `RR_DECAY_HALF_LIFE` | 30 | base half-life in the **game's** time units |
| `RR_DECAY_IMPORTANCE_SCALE` | 50 | half-life ×= `scale^importance` (significance → near-permanent) |
| `RR_DECAY_REINFORCE_GAIN` | 1.0 | each reinforcement ×= `(1+gain·N)` half-life |

See [`relevance-scoring.md`](relevance-scoring.md) for the full memory-scoring detail and how
to read the debug panel, and [`architecture-seams.md`](architecture-seams.md) for the
engine/game seam design.
