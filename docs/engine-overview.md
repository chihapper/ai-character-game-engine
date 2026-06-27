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
*(Coming, #12: disposition also shifts from world events the game pushes, even indirect ones.)*

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
