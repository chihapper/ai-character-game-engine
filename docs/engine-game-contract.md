# The engine ↔ game contract

> **What this is.** The concrete, code-accurate interface a game builds against to drive
> this character engine — the methods, what they *apply* vs *return*, who owns time and
> cadence, and how in-the-moment reactions work without baking any one game's assumptions
> into the engine. It describes the code, not plans. Last checked by reading the
> `credibility-demo` branch on 2026-11-07. The examples were not run, because they call paid
> models. `main` has the same engine surface. `game-rpg` differs in ways not all marked here: for one, its `reflect()` gives the judge no recalled memories or open promises.
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
from orchestrator.adapters.llm_anthropic import AnthropicLLM
from orchestrator.character_store import load_character
from orchestrator.config import EngineCaps, get_settings
from orchestrator.context import RespondRequest, Situation
from orchestrator.engine import Engine

caps = EngineCaps.from_settings(
    get_settings(),
    relationship_state=True, reflection_enabled=True, intent_state=True,
    background_reflection=True,                        # long-lived processes only; see §1.1
)
eng = Engine(load_character("corvin-ashgrave-inworld"), AnthropicLLM(), caps=caps)
```

`llm` fills the actor seat (§6.5), and `respond()` raises an error without one. `caps` sets what
this mind can do: without it the engine uses the environment defaults, which leave relationship,
beliefs, and intent off (§6).

The slug is a file name in [`orchestrator/characters/`](../orchestrator/characters). Running this
writes to that character's `.memory/` files. On `credibility-demo`, `corvin-ashgrave-inworld` is
the credibility demo's default mind, so experiment with a different character.

`Engine(..., readonly=True)` freezes the character's stores, which suits replays and A/B runs. No
game surface passes it, and the `MEMORY_READONLY` setting doesn't reach them.

### 1.1 `respond` — a conversational turn (player speaks, character replies)

```python
reply: str = await eng.respond(RespondRequest(
    player_input="You still owe me for the last run.",
    situation=Situation(clock=day, location="the docks", present=["Dren"]),
))
```

The engine internally: builds the relevance query, retrieves memory (decay-aware),
foregrounds any fresh happenings (§4), renders the dynamic context, generates the line,
records the exchange, and reflects (the judge call that scores salience and moves any
relationship, intent, or commitment state; see §6.2).
**Returns only the spoken line.** All state changes are applied inside and owned by the
engine.

**When reflection runs.** By default `respond()` waits for reflection before it returns, so the
player waits too. With `background_reflection=True` it runs as a background task instead, and you
take on one duty: call `await eng.flush_reflection()` at the end of each scene and before the
process exits, or the last turn's memory and feeling updates may not land. The Ferry text game,
the mind server, and the grid arena work this way and flush when a game finishes. The Director's
Sandbox stays inline.

**The `[[...]]` postscript.** A game's performance rules may ask the actor to end its reply with a
`[[...]]` line of stage machinery. The engine detaches that line, so it stays out of the history
and the returned text, and keeps its inner text, without the brackets, in `eng.last_postscript` (`None` if there wasn't
one). The engine never interprets it. For example, the mind server passes `FACE happy@0 angry@0.6`
to `policy.parse_face_marks()`.

**`prepare()` and `reflect()`** are the two halves of `respond()`, for a host that generates the
reply itself. Such a host can omit `llm`. The only one today is the Inworld full-loop runtime,
which was not adopted.

### 1.2 `remember` — push a durable world event, get back its salience

```python
salience: float | None = await eng.remember(
    "Flames erupt from the granary across the square.",
    t=day,                       # numeric game-clock; the engine only takes differences
    magnitude=0.9,               # OPTIONAL coarse objective-scale hint (world/Game Master), 0..1
    # importance=0.8,            # OPTIONAL: PIN the weight instead of letting them appraise
    # player_role="caused",      # OPTIONAL: the PLAYER did it -> also shifts disposition
    # actor="self",              # OPTIONAL: the character's OWN change of heart
)
```

- **Omit `importance`** → the character appraises the event's *personal* salience for
  themselves (a distant war they shrug off; a small kindness that marks them), optionally
  informed by the coarse objective `magnitude` hint. **Pin `importance`** → honored verbatim.
- **`player_role` / `actor="self"`** make the event *attributable* → with `relationship_state`
  on, the engine also moves the character's feelings toward the player (deltas / scar /
  scar-heal). With neither argument, or with that capability off, it's a pure memory write.
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
| `internal` | a change of heart toward the player | **engine** (memory, plus disposition with `relationship_state` on) |
| `new_intent` | updated near-term aim | **engine** (intent store) |
| `new_goals` | the standing goals actually stored, or `[]` if they held | **engine** (agency store) |
| `world_action` | something they DO in the world | **the game** (see §2) |
| `skipped` | present only on a gated-mode structural skip (nothing happened, no LLM call) | — |

The engine **applies the inner half itself** (the soul — it needs no game architecture) and
**returns `world_action` for the game to enact.**

**Handle the failure shape.** A failed deliberation returns only `{"changed": False}`, with no
other keys, and doesn't advance the character's stock-taking clock, so a later run still sees the
same events. Read every other key with `.get()`.

**Goal reconciliation.** After a successful decision, a second, focused judge call
(`reconcile_goals`) reviews the standing goals one by one. It's the single authority on goals: the
deliberation's own `new_goals` are only a proposal it weighs. It runs even when `changed` came back
false, because goals can lag behind change that already happened. A goal moves only on accumulated
change, so a goal core to the character can hold even against the relationship. `new_goals` reports
what was actually stored, and a goal that moved sets `changed` to true. The pass needs existing
goals and a writable store. With no existing goals, or if the pass fails, the deliberation's proposal is stored unreviewed. With a read-only store nothing is stored and `new_goals` still shows the proposal.

**Cost.** A run that reaches a decision makes two judge calls, the decision and the reconciliation,
plus one for event impact if `internal` is applied with `relationship_state` on.

**Who calls it today.** The Ferry text game ([`game/runtime.py`](../game/runtime.py)), the
Director's Sandbox ([`orchestrator/sandbox.py`](../orchestrator/sandbox.py)), and scripts in
[`tools/`](../tools) call `deliberate()`. On `game-rpg`, `game/rpg/game.py` does too. The mind
server and the grid arena never call it; they use `choose_action()` only.

> **Always pass the current scene** (`location`, and the world frame / why-they're-here in
> `extra`). The engine can't invent where a character is, so a `deliberate()` with no scene
> anchor lets `world_action` drift to a locale from the character's backstory ("harbormaster
> of a smuggling port" → *slips out of the harbormaster's office* while stranded at a ferry-inn).
> `deliberate()` reads `location` and two exact `extra` keys, `"The world you live in"` and
> `"Why you're here tonight"`; a `Situation` with none of the three has no scene anchor.
> The engine **logs a warning** when it deliberates without a scene — treat that log line as a
> bug in the caller, not noise. Same scene you'd pass to `respond`/`choose_action`.

### 1.4 `choose_action` — the embodied-action seam (for games with a world model)

```python
choice: dict = await eng.choose_action(
    situation,                    # the perceived scene (a string, or a Situation to render)
    ["cross to the door", "watch the stranger", "stay where you are"],   # what the world AFFORDS
)
# -> {"action": "<exactly one of the options, or None>", "reason": "<short, in-character>",
#     "expression": "<what shows on their face, free text>",
#     "face": "<neutral|happy|sad|angry|fear|surprise>"}
```

For embodied/spatial games: the GAME enumerates the **concrete actions the world currently affords**
(its own vocabulary — the engine never knows what an action *means*), and the engine picks the one this
character would take — or none — **hard-bounded to the offered list**, so a character can never act
outside what the place allows. The choice is grounded in who they've *become* (evolved goals, near-term
aim, feelings/scars toward the player, formed beliefs), not just the authored sheet. Applied-vs-returned
holds here too: the engine only returns the choice; **the game executes it** against its world. A text
game simply never calls this; the grid arena and the mind server do.

`expression` and `face` are for the game to render or ignore (§7.5). Each call is one judge call.
With an empty `options` list the engine makes no call and returns only
`{"action": None, "reason": ""}`, so read those two keys with `.get()`.

### 1.5 Obligations (optional)

```python
c = eng.commit("meet the player at dawn", made_t=day, due_t=day+1)   # the character took on a promise
await eng.resolve_commitment(c.id, "fulfilled", t=day+1)              # ...later closed (-> a memory)
```

- **`commit()` returns a `Commitment` object**, not an id, or `None` for empty text or a read-only
  store. It also takes `parties` and `importance`.
- **`due_t` is the numeric deadline** on your clock. `due` is a separate display string, such as
  `"by dawn"`.
- **`resolve_commitment()`** takes `c.id` and a status of `"fulfilled"` or `"broken"`.
- **An open commitment expires** on the next `prepare()` or `respond()` after the clock passes
  `due_t`, and converts to a memory.
- **Open commitments are always in the character's turn context.** `commit()` works whether or not
  `commitment_detection` is on. That flag controls whether the judge finds promises in dialogue
  and sees the open ones.

---

## 2. The load-bearing distinction: APPLIED vs RETURNED

- **Inner change is APPLIED inside the engine** — memory, relationship, beliefs, goals,
  intent. The game cannot veto it and needs no architecture for it. A simple game only has to
  turn the capabilities on: relationship, beliefs, and per-turn intent default off, and one
  `EngineCaps` line enables them (§6.1).
- **Outward action is RETURNED, never enacted** — `world_action` is a *string the game does
  something with*. A spatial game moves the NPC; a text game narrates it; a game that can't
  represent it **ignores it**. The engine doesn't need your world to do anything in particular, but it does record the action: when `changed` is true it stores `world_action` in memory as the character's own choice, so the character believes it happened even if you ignored it.

> Never wait for the engine to "perform" a `world_action`. It won't. That's yours.

---

## 3. In-the-moment reactions — a *recipe*, not a method

There is deliberately **no `engine.react()`**. An in-the-moment reaction is the game
*composing* two primitives, so the policy stays yours:

```python
salience = await eng.remember(event, t=now)          # engine: how much does THIS character care?
if game_says_this_interrupts(salience, scene):        # GAME policy: worth breaking the scene for?
    decision = await eng.deliberate(
        Situation(clock=now, location=scene.location, extra=scene.extra), mode="free")
    if action := decision.get("world_action"):        # .get(): a failed deliberation lacks the key
        enact(action)                                 # GAME: do it / narrate it / ignore it
    # embodied variant: instead of enacting prose, offer the afforded options —
    # choice = await eng.choose_action(percept, afforded_options)   (§1.4)
# ...the character's NEXT respond() line carries the event + reaction automatically (§4)
```

`salience` can be `None` (§1.2), so your policy has to handle that.

The reference implementation is the Director's Sandbox route `POST /api/sandbox/{slug}/event`
([`orchestrator/sandbox.py`](../orchestrator/sandbox.py)): its "react now" toggle runs this
recipe, with a threshold (`REACT_SALIENCE_FLOOR = 0.7`) that lives **in the sandbox,
not the engine** — because "does a fire interrupt this conversation?" is a game decision, and
a tense scene, a calm one, or a real-time barge-in (the player talking over a voice line) each
want a different answer. Don't copy one thing from it: the sandbox passes only a clock, so it
trips the no-scene warning from §1.3.

Relevance realization (RR), the engine's way of judging what matters to this character right now,
reaches the game as the appraised salience. The engine supplies the signal, the game supplies the
policy.

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

Config: `recent_happenings*` in [`config.py`](../orchestrator/config.py). **This is a
per-game OBLIGATION, not a default to inherit:** `recent_happenings_window` is in **your**
time unit — a turn-based game in "days" and a real-time one in "seconds" set it differently —
and it must be tuned to your **scene cadence**: at least as wide as your typical time-skip
between scenes ("that evening…", "weeks pass…"), or foregrounding lapses at exactly the
moments it exists for. The engine never assumes the unit; it only takes `now_t − event_t`.
Set the window per engine through `EngineCaps` (§6.1). The Ferry text game, mind server, and grid
arena take it from the scenario's `clock.recent_happenings_window` when that's present; otherwise
the default of 1.0 applies.

> **Mis-tuning symptom (found live, 2026-07-10, lich-arc P4):** the window was 1.0 unit in a
> game whose scenes jump days at a time. The character's *deliberation* reasoned at length
> about his harbor burning (deliberation grounds on recent events directly) — yet in the
> *conversation* six days later he never mentioned it: too old to foreground, and retrieval
> under a trusting stance filled every slot with bond memories. The mind knew; the mouth's
> context didn't. If your NPCs deliberate about events they then never speak of, check this
> window against your cadence first.

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
([`config.py`](../orchestrator/config.py)). §6.2 lists what each one costs.

| flag | default | what it enables |
| --- | --- | --- |
| `relationship_state` | **off** | feelings/scars move from events + turns |
| `relationship_time_decay` | on | feelings drift toward baseline over absence (needs `relationship_state`) |
| `reflection_enabled` | **off** | exchanges consolidate into durable beliefs |
| `intent_state` | **off** | a tracked near-term aim |
| `salience_scoring` | on | NPC-appraised importance (else a flat default) |
| `commitment_detection` | **off** | promises the character makes are extracted + tracked, and the judge sees open promises |
| `contradiction_detection` | **off** | a caught player lie is recorded as a salient memory |
| `recent_happenings` | on | the working-memory foregrounding of §4 |
| `arena_query` | on | richer retrieval query (trigger + scene + goals) |
| `background_reflection` | **off** | reflection runs after the reply instead of before it; you must call `flush_reflection()` (§1.1) |
| `reinforce_on_recall` | **off** | recalling a memory reinforces it against decay. Process-wide, not in `EngineCaps` |

Note the defaults: the *affect/agency* trio (relationship, reflection, intent) defaults **off** and the
sandbox/games turn it on, but salience scoring, time decay, foregrounding, and the arena query default
**on** — a game integrator budgeting LLM calls should know `salience_scoring` is already live.

`deliberate()` and `choose_action()` have no flag; they run whenever the game calls them. Scars and
world-event impact have no flag of their own; both need `relationship_state`.

### 6.1 `EngineCaps`: flags are set per engine

Each `Engine` takes a frozen snapshot of these flags when it's built. One surface can't change
another's engines, and engines with different capabilities can share a process.

```python
caps = EngineCaps.from_settings(get_settings(), relationship_state=True, commitment_detection=True)
eng = Engine(character, llm, caps=caps)
```

`from_settings` starts from the environment values and applies your overrides. The snapshot also
holds the tuning values that go with the flags, such as `recent_happenings_window`,
`reflection_importance_threshold`, and `short_term_turns`. `reinforce_on_recall` is the one flag it
doesn't hold: long-term memory reads that setting directly, and passing it to `from_settings`
raises a `TypeError`.

**Game surfaces force some flags on in code,** so setting these in `.env` has no effect there:

| Surface | Forced on |
| --- | --- |
| Ferry text game ([`game/runtime.py`](../game/runtime.py)) | `relationship_state`, `reflection_enabled`, `intent_state`, `background_reflection` |
| Mind server ([`game/bridge/mind_api.py`](../game/bridge/mind_api.py)) | the same four |
| Grid arena ([`game/arena/game.py`](../game/arena/game.py)) | the same four |
| Director's Sandbox ([`orchestrator/sandbox.py`](../orchestrator/sandbox.py)) | `relationship_state`, `reflection_enabled`, `intent_state` |

Other flags on these surfaces come from the environment, so `commitment_detection` and
`contradiction_detection` stay off there unless `.env` turns them on. On `game-rpg`,
`game/rpg/minds.py` builds its own set with `full_depth_caps()`.

With the default `VOICE_RUNTIME=pipeline`, the conversation path on port 8000 builds no `Engine`, so `relationship_state`, `intent_state`, `reflection_enabled`, `commitment_detection`, and `contradiction_detection` have no effect on it. With `VOICE_RUNTIME=inworld_fullloop` it builds an `Engine` from the environment flags, so they do.

### 6.2 What each call costs

| You call | LLM calls |
| --- | --- |
| `respond()` | One actor call, then one judge call for reflection. That judge call is *folded*: it answers salience, relationship, intent, and commitments together, for whichever are on. With `relationship_state`, `intent_state`, and `commitment_detection` all off, it's a plain salience score, or nothing if `salience_scoring` is off too |
| `respond()`, on some turns | A contradiction check, with `contradiction_detection` on and memories recalled. Belief consolidation, with `reflection_enabled` on, when accumulated importance reaches `reflection_importance_threshold` (3.0 by default). One persistence assessment per character, with `relationship_state` and `relationship_time_decay` on, until it succeeds |
| `remember()` | One salience appraisal, unless `importance` is pinned or scoring is off. One more for event impact if the event is attributable and `relationship_state` is on |
| `deliberate()` | Two, plus one for event impact if `internal` is applied with `relationship_state` on. None on a gated skip |
| `choose_action()` | One |

---

## 6.5 The two LLM seats: actor and judge

A character runs on two LLM roles with very different requirements, and they're configured
separately.

| Seat | Job | Set by | Default |
| --- | --- | --- | --- |
| **Actor** | Writes the spoken line in `respond()` | The adapter passed as `Engine(llm=...)` | Varies by surface |
| **Judge** | Decides what each moment means, in every other LLM call | The role settings below | `claude-sonnet-4-6` for all three |

| Judge role | Setting | Covers |
| --- | --- | --- |
| `salience` | `SALIENCE_MODEL` | Salience, the folded per-turn judgment, event impact, persistence, contradiction checks, `choose_action()` |
| `deliberation` | `DELIBERATION_MODEL` | `deliberate()` and goal reconciliation |
| `reflection` | `REFLECTION_MODEL` | Belief consolidation |

- **The judge is process-wide.** These are settings, not `EngineCaps` fields, so every engine in a
  process shares them. `choose_action(..., model=...)` can override one call.
- **Changing the judge is a real decision.** Only `claude-sonnet-4-6` has passed the 46-beat
  full-life battery. See [`judge-seat-requirements.md`](judge-seat-requirements.md).
- **Thinking headroom.** Every judge call gets 2,048 tokens on top of its visible budget
  ([`judgment.py`](../orchestrator/judgment.py)), so a model that thinks by default can't spend the
  whole allowance before it answers. An empty reply is retried once with 4,096 more. If it's still
  empty, the engine logs a warning and the caller falls back to a neutral result.
- **A custom actor adapter** implements `stream_reply(messages, system, *, cache_messages=False)`
  from `LLMAdapter` ([`adapters/base.py`](../orchestrator/adapters/base.py)). The engine passes
  `cache_messages=True`, so the keyword is required.
- **Local models (`credibility-demo` only).** A judge model named `local/<name>` routes to an
  OpenAI-compatible server at `LOCAL_JUDGE_BASE_URL`. Among the existing surfaces, a local actor is wired only in `make_engine()`
  in `tools/_harness.py`, which the credibility tools use, because every game surface hard-codes
  `AnthropicLLM`. Your own host can pass `OpenAICompatLLM` to `Engine(llm=...)` directly.

---

## 7. What the engine NEVER does

- Invent world events (it only appraises + remembers what the game feeds it).
- Enact a `world_action` (it returns it; the game acts).
- Run its own clock or loop (cadence is 100% the game's calls).
- Name a game concept in engine logic (quests, character classes, calendars; the word "faction" appears only in the event-impact judge prompt and a docstring) — those
  live in `game_data` + a registered renderer (see architecture-seams §2). No game on any branch
  registers a renderer yet.
- Surface state as UI. Change is meant to be *felt through behavior and words*, never read off
  a stats panel. (The sandbox's bars are a **dev** instrument, not a game surface.)

---

## 7.5 Presentation services (voice + face) — beside the engine, not inside it

Voice (TTS) and facial animation (audio → ARKit blendshapes) are **bridge conveniences**,
not engine surface. They live behind `FaceAnimAdapter` / `TTSAdapter` seams next to the LLM
adapters; the engine core never references them, and a text-only game never touches them.
The transport is deliberately client-agnostic: raw PCM plus timestamped **ARKit-52**
blendshape frames (the current NeuroSync path adds 9 head and eye channels, 61 named channels in all) — Unreal, Unity, VRM, and web avatars all consume ARKit; how curves reach
a specific rig is the CLIENT's code.

> **Current status (2026-11-07):** **Hume Octave** won the TTS bake-off, but no provider
> setting selects it. A game turns it on with `GAME_TTS=hume` and `HUME_API_KEY`, and on this branch the mind server also needs a non-empty `ELEVENLABS_API_KEY` because its `voice_ready` check ignores the Hume key; see
> [`tts-providers.md`](tts-providers.md).
> The face seam had two implementations — NVIDIA **Audio2Face** (`faceanim_a2f.py`), then a
> self-hosted **NeuroSync** (`faceanim_neurosync.py`) once A2F needed hardware the dev GPU
> lacked — and drove a MetaHuman face in the Unreal client. **The face layer is paused.**
> A Godot RPG client exists on the `game-rpg` branch; it doesn't use this layer, and its talk
> scene uses voice-amplitude motion instead. The seam itself is unchanged and this contract
> holds regardless.

One deliberate crossing, in the correct direction: the engine's chosen expression (a mind
fact — `face` from `choose_action`, or the `[[FACE ...]]` marks a game's performance rules ask
for) may be passed DOWN to color the performance. Psychology tells the face what to feel; audio
only times the mouth. The reverse never happens — no presentation signal feeds the mind.

`/speak_anim` still accepts `face` and a per-timecode `emotions` list, but its current NeuroSync
path ignores both, because NeuroSync works from audio alone. Emotion reaches the face through the
acted voice.

---

## 8. Minimal integration checklist

To drive a character from a game:

1. **Load / construct** an `Engine` per character; give it an LLM and the `EngineCaps` you want
   (§6.1). A host that generates replies itself uses `prepare`/`reflect` instead.
2. **On a player line or trigger:** call `respond(RespondRequest(player_input=…,
   situation=Situation(clock=…, …)))`, show the returned line.
3. **On a world change worth remembering:** call `remember(fact, t=…, …)`; keep the returned
   salience if you want reactions.
4. **To let the character react / evolve:** on your own cadence, call `deliberate(situation)`
   with the current scene; **enact or narrate `world_action`** (read it with `.get()`), and let
   the engine keep the inner changes.
5. **Pass a numeric `clock`** in every `Situation` (your own unit) so decay + working memory
   work; **tune `recent_happenings_window`** to that unit.
6. **If you turned on `background_reflection`:** call `await eng.flush_reflection()` at the end of
   each scene and before the process exits.

That's the whole seam. Everything the character *is* stays behind it; everything the world
*is* stays in front of it.
