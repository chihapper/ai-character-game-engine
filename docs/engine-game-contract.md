# The engine ↔ game contract

> **What this is.** The concrete, code-accurate interface a game builds against to drive
> this character engine — the methods, what they *apply* vs *return*, who owns time and
> cadence, and how in-the-moment reactions work without baking any one game's assumptions
> into the engine. Reflects the code as it stands (not aspirational).
>
> **Companion doc.** [`architecture-seams.md`](architecture-seams.md) is the *design &
> rationale* for the seams (including the voice runtime); this is the *contract* for the
> engine/game seam specifically. When they disagree, the code + this doc win.

---

## 0. The one rule

**The engine owns the character's MIND. The game owns the WORLD.**

Everything below is a corollary. The engine decides who the character *is* and *becomes* —
memory, feelings, beliefs, goals, what they'd do. The game decides what *happens*, *when*,
and what any outward action *means* in its world. The engine never reaches into the game;
the game never reaches into the character's psychology except through the methods here.

| The engine owns (portable, game-agnostic) | The game owns (game-specific) |
| --- | --- |
| Memory (short + long term), retrieval / relevance | The world: what happens, who's where |
| Salience appraisal — how much an event matters *to this character* | **When** to call the engine (cadence) |
| Relationship / feelings / scars, decay | The **clock** and its unit (days/ticks/seconds) |
| Beliefs, standing goals, near-term intent | **Enacting** outward actions (or narrating them) |
| Autonomous inner change (`deliberate`) | The **policy** for whether an event interrupts a scene |
| Producing *one* character's line/decision per call | Multi-character scene orchestration (who speaks when) |

---

## 1. The surface

One `Engine` instance per character (keyed by `character.memory_namespace`; state persists
to `.memory/<namespace>.*`).

```python
from orchestrator.engine import Engine
from orchestrator.character_store import load_character
from orchestrator.context import RespondRequest, Situation

eng = Engine(load_character("corvin-ashgrave"), llm)   # llm optional; voice drivers omit it
```

### 1.1 `respond` — a conversational turn (player speaks, character replies)

```python
reply: str = await eng.respond(RespondRequest(
    player_input="You still owe me for the last run.",
    situation=Situation(clock=day, location="the docks", present=["Dren"]),
))
```

The engine internally: builds the relevance query, retrieves memory (decay-aware),
foregrounds any fresh happenings (§4), renders the dynamic context, generates the line,
records the exchange, and reflects (salience + any relationship shift) in the background.
**Returns only the spoken line.** All state changes are applied inside and owned by the
engine. For voice runtimes that host their own generation, call `prepare()` /
`reflect()` around it instead of `respond()`.

### 1.2 `remember` — push a durable world event, get back its salience

```python
salience: float | None = await eng.remember(
    "Flames erupt from the granary across the square.",
    t=day,                       # numeric game-clock; the engine only takes differences
    magnitude=0.9,               # OPTIONAL coarse objective-scale hint (world/DM), 0..1
    # importance=0.8,            # OPTIONAL: PIN the weight instead of letting them appraise
    # player_role="caused",      # OPTIONAL: the PLAYER did it -> also shifts disposition
    # actor="self",              # OPTIONAL: the character's OWN change of heart
)
```

- **Omit `importance`** → the character appraises the event's *personal* salience for
  themselves (a distant war they shrug off; a small kindness that marks them), optionally
  informed by the coarse objective `magnitude` hint. **Pin `importance`** → honored verbatim.
- **`player_role` / `actor="self"`** make the event *attributable* → the engine also moves
  the character's feelings toward the player (deltas / scar / scar-heal). With neither, it's
  a pure memory write.
- **Returns the stored salience** — the character's own weight for this event. This is the
  engine's half of the reaction seam (§3): the game reads it to decide, by *its own* policy,
  whether the event is worth interrupting the scene for. (Returns `None` only for an empty
  write, or when salience scoring is off and `importance` wasn't pinned.)

### 1.3 `deliberate` — the character decides / changes on its own (between scenes)

```python
decision: dict = await eng.deliberate(
    Situation(clock=day, location="the burning docks"),
    mode="free",                 # "free" (default, more coherent) | "gated" (fewer, larger moves)
)
```

Between scenes — the player need not be present — the character takes stock of everything
accumulated and decides what it does or becomes. The **Decision** dict:

| key | meaning | applied by | 
| --- | --- | --- |
| `changed` | did anything move | — |
| `reflection` | the character's inner take (first-person) | — (surface if you like) |
| `internal` | a change of heart toward the player | **engine** (memory + disposition) |
| `new_intent` | updated near-term aim | **engine** (intent store) |
| `new_goals` | evolved standing goals (or `[]` if held) | **engine** (agency store) |
| `world_action` | something they DO in the world | **the game** (see §2) |
| `skipped` | gated-mode structural skip (nothing happened) | — |

The engine **applies the inner half itself** (the soul — it needs no game architecture) and
**returns `world_action` for the game to enact.**

### 1.4 Obligations (optional)

```python
cid = eng.commit("meet the player at dawn", due=day+1)     # the character took on a promise
await eng.resolve_commitment(cid, "fulfilled", t=day+1)     # ...later closed (-> a memory)
```

---

## 2. The load-bearing distinction: APPLIED vs RETURNED

- **Inner change is APPLIED inside the engine** — memory, relationship, beliefs, goals,
  intent. The game cannot veto it and needs no architecture for it. A simple game gets the
  full living inner life for free.
- **Outward action is RETURNED, never enacted** — `world_action` is a *string the game does
  something with*. A spatial game moves the NPC; a text game narrates it; a game that can't
  represent it **ignores it**. This is the graceful-degradation guarantee: the engine never
  assumes your world can do anything in particular.

> Never wait for the engine to "perform" a `world_action`. It won't. That's yours.

---

## 3. In-the-moment reactions — a *recipe*, not a method

There is deliberately **no `engine.react()`**. An in-the-moment reaction is the game
*composing* two primitives, so the policy stays yours:

```python
salience = await eng.remember(event, t=now)          # engine: how much does THIS character care?
if game_says_this_interrupts(salience, scene):        # GAME policy: worth breaking the scene for?
    decision = await eng.deliberate(Situation(clock=now), mode="free")
    enact(decision["world_action"])                   # GAME: do it / narrate it / ignore it
# ...the character's NEXT respond() line carries the event + reaction automatically (§4)
```

The reference implementation is the director sandbox's `/event` endpoint
([`orchestrator/sandbox.py`](../orchestrator/sandbox.py)): its "react now" toggle runs
exactly this, with a threshold (`REACT_SALIENCE_FLOOR = 0.7`) that lives **in the sandbox,
not the engine** — because "does a fire interrupt this conversation?" is a game decision, and
a tense scene, a calm one, or a real-time barge-in (a Track V concern) each want a different
answer. RR — via the appraised salience — is what a game gates on; the engine supplies the
signal, the game supplies the policy.

> **Not built on purpose:** having `respond()` itself emit a reactive `world_action`
> mid-dialogue. It's too unpredictable (risks arbitrary scene exits). Game-cadence
> (`deliberate`) is the sanctioned path to an in-the-moment action.

---

## 4. Working memory (why the next line "just knows")

After an event or a `deliberate`, the character's **next `respond()` naturally reflects it**
even if the player's words don't mention it — no reminding. The engine foregrounds the few
*fresh, high-salience* happenings (events **and** the character's own just-taken acts) as
working memory. This is:

- **Additive** — its own small block; it does **not** shrink the retrieval budget or the
  short-term window, so it never crowds out the salient memories.
- **Salience-gated** (uses the appraised weight) and **capped** — never a flood.
- **Transient** — bounded by a recency window in *game-time*, so an item is top-of-mind for
  the beat it's live in, then falls back to ordinary relevance-retrieval as the scene ages.

Config: `recent_happenings*` in [`config.py`](../orchestrator/config.py). One integration
note: `recent_happenings_window` is in **your** time unit — a turn-based game in "days" and a
real-time one in "seconds" set it differently. The engine never assumes the unit; it only
takes `now_t − event_t`.

---

## 5. Game-dependent semantics — don't assume, don't hard-code

The engine must fit *any* game, so several behaviors are pushed to the game layer rather than
decided in the core (design rule: **game-dependent semantics stay in the game layer** — don't
hard-code one game's assumptions in the engine, and don't "fix" one by hard-coding the opposite):

- **World events are optional.** A game with none simply never calls `remember(event)`.
- **Attribution is optional.** Most events are pure world memories; only `player_role` /
  `actor="self"` move feelings.
- **A time gap is RR-judged, not a rule.** Whether an absence reads as abandonment depends on
  the character *and* the established rhythm of contact — the engine weighs it, it isn't a
  hard threshold.
- **Time is opaque.** `clock` is one monotonic number in the game's unit; the engine only
  differences it, never parses a calendar (`game_time` is a display string).

---

## 6. Capability flags (a game dials the engine up or down)

Behaviors are gated so a minimal game can run lean and a rich one can turn everything on
([`config.py`](../orchestrator/config.py)). The heavy ones each cost an extra LLM call:

| flag | what it enables |
| --- | --- |
| `relationship_state` | feelings/scars move from events + turns |
| `relationship_time_decay` | feelings drift toward baseline over absence |
| `reflection_enabled` | exchanges consolidate into durable beliefs |
| `intent_state` | a tracked near-term aim |
| `salience_scoring` | NPC-appraised importance (else a flat default) |
| `recent_happenings` | the working-memory foregrounding of §4 |
| `arena_query` | richer retrieval query (trigger + scene + goals) |

Off by default at the process level; the sandbox and demos turn on the set they need.

---

## 7. What the engine NEVER does

- Invent world events (it only appraises + remembers what the game feeds it).
- Enact a `world_action` (it returns it; the game acts).
- Run its own clock or loop (cadence is 100% the game's calls).
- Name a game concept in engine code (quests, factions, D&D classes, calendars) — those live
  in `game_data` + a registered renderer (see architecture-seams §2).
- Surface state as UI. Change is meant to be *felt through behavior and words*, never read off
  a stats panel. (The sandbox's bars are a **dev** instrument, not a game surface.)

---

## 8. Minimal integration checklist

To drive a character from a game:

1. **Load / construct** an `Engine` per character; give it an LLM (or use `prepare`/`reflect`
   for a voice runtime).
2. **On a player line or trigger:** call `respond(RespondRequest(player_input=…,
   situation=Situation(clock=…, …)))`, show the returned line.
3. **On a world change worth remembering:** call `remember(fact, t=…, …)`; keep the returned
   salience if you want reactions.
4. **To let the character react / evolve:** on your own cadence, call `deliberate(situation)`;
   **enact or narrate `world_action`**, and let the engine keep the inner changes.
5. **Pass a numeric `clock`** in every `Situation` (your own unit) so decay + working memory
   work; **tune `recent_happenings_window`** to that unit.

That's the whole seam. Everything the character *is* stays behind it; everything the world
*is* stays in front of it.
