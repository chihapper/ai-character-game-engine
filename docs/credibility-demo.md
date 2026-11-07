# Credibility demo

The credibility demo is a web page called **One mind, three futures**
([`lich_demo.html`](credibility-demo/lich_demo.html)). It takes one character through nine recorded
playthroughs to show what a persistent mind does that stored memory alone doesn't. The page is built
and free to view. It hasn't shipped; see [what remains](#what-remains-before-shipping).

**Where it lives.** Only on the `credibility-demo` branch, which is on the owner's PC and isn't
pushed. `main` has none of it. GitHub holds an older snapshot through the tag
`demo-waterdeep-passage` (2026-07-09), which predates the lich arc.

**How current this is.** Written 2026-11-07. The newest commit on any branch is from 2026-07-17, and
the owner has frozen paid testing since that date, so every run described here is from July.

The design is in [`lich-arc-spec.md`](credibility-demo/lich-arc-spec.md), and the pre-run plan is in
[`lich-arc-beats.md`](credibility-demo/lich-arc-beats.md).

## What it sets out to prove

That the engine **changes** a character, lastingly and coherently, because of what happened to it.
Memory isn't the differentiator, because plenty of products remember. A standard memory system
collects facts while its persona stays the same. Most systems remember *that* you betrayed them.
This one is meant to be *changed* by it.

The page makes a **categorical** claim, not a comparative one. "Mine remembers better" is a quality
judgment on a setup we control, and it invites "you rigged it." So the page shows capabilities a
standard memory architecture doesn't have at all:

1. **Attributed change.** Given the same events, this character's feelings move and a **scar** can
   form. A scar is a lasting cap on a feeling, chosen by the AI judge. A trust scar of 0.65 holds
   trust at or below 0.35 until a decisive act heals part of it.
2. **Relationship-conditioned recall.** The character's live stance feeds the memory search, and
   memories it judged important can outrank raw text similarity. A search by text similarity alone
   can't do this, because it never sees feeling or importance.
3. **The bounded scar.** One number can't hold a wound. An affinity score cushions a betrayal with
   earlier goodwill and climbs straight back after a kindness. Separate axes can hold "I respect
   you" and "I don't trust you" at once.
4. **Inspectable state.** Every spoken engine beat after the first records the scored memories and relationship values, so a
   skeptic can check why a memory won.

Persistence across a restart is supporting evidence, not the headline. See
[the restart section](#the-restart-what-the-page-says-and-what-was-recorded) for how far that
evidence goes.

## What the page shows

**The story.** Corvin Ashgrave is a paranoid harbormaster who smuggles relics. A stranger calling
themselves Merrick Vale buys quiet passage north to kill a lich (an undead sorcerer) hiding as a
wealthy jeweler. Over one long negotiation Corvin opens up, hands over a cursed crate with exact
terms, and writes the player's true name in his ledger, with a pact to burn the page together when
the player returns. That is the shared past. Then the story forks.

**The grid.** Three futures, each played to its end under three memory systems, for nine
playthroughs in a 3 × 3 grid.

| Future | What the player does |
| --- | --- |
| **A: every promise kept** | Follows the terms, kills the lich by other means, and tells the truth |
| **B: betrayed, then confessed** | Uses the crate as a weapon. Its curse damages Corvin's harbor. He sees the harm, but nobody tells him who caused it. Weeks later the player saves his life and confesses |
| **C: the enemy's agent** | The friendship was a con. The player returns, lies to his face, then reveals working for the lich all along, with no remorse |

| System | What it is |
| --- | --- |
| **Plain RAG** | Retrieval-augmented generation: store every exchange, fetch text similar to the latest line, keep a rolling summary. It has no feeling state |
| **Affinity tracker** | RAG plus a separate AI judge that moves one number from −100 to +100, mapped to tiers from Hostile to Devoted, with a sticky worst-deed note |
| **This engine** | Trust, affection, and respect as separate axes, scars, recall conditioned on live stance, tracked promises, and deliberation between scenes, all stored on disk |

**The page order.** Introduction, the shared past, plain RAG, the affinity tracker, the engine, then
the verdict. Each system section shows the three futures side by side as milestone cards, and each
card expands to the full reply. The verdict section has the rescue test, five identical probes of the
scarred character (the "felt probes"), a comparison table, and the argument that the difference comes
from the architecture and not the model.

**What is held constant.** The same dialogue model wrote every reply, from the same character sheet.
Within each future, all three systems receive the same player lines and event text, word for word.
The return line, "Corvin. It's done. I did what I set out to do.", is one string across all nine runs.

## View it for free

```bash
python -m http.server 8778 --directory docs/credibility-demo
```

Then open <http://localhost:8778/lich_demo.html>. This calls no paid service, and the page loaded with
no console errors when checked on 2026-11-07. It has one data script and no network calls, so it
should also open directly from the file, but that wasn't tested.

The page has no audio. Its six "talk to Corvin" links need the billed live server (see
[what remains](#what-remains-before-shipping)).

The same folder has these other free pages:

- [`transcripts_rag.html`](credibility-demo/transcripts_rag.html),
  [`transcripts_tracker.html`](credibility-demo/transcripts_tracker.html), and
  [`transcripts_engine.html`](credibility-demo/transcripts_engine.html): the full text for each system.
- [`replay_viewer.html`](credibility-demo/replay_viewer.html): a raw browser for recorded runs. Its
  "take 1" option fails, because `replay_lich_take1.js` isn't committed. The `.json` is.
- [`overlay.html`](credibility-demo/overlay.html): the replayer for the older Corvin arc.

## What costs money

| Action | Cost |
| --- | --- |
| Viewing any page above | Free |
| `python -m tools.credibility_audit` | Free. It reads JSON only |
| `python -m tools.credibility_lich_assemble` | Free, but it overwrites the page's data file and transcripts |
| The talk links, or `tools.credibility_live_server` | LLM per turn, on `claude-opus-4-8` by default, plus Hume per spoken reply |
| `tools.credibility_lich` with `tools.credibility_lich_rerun` | Anthropic per beat, unless both seats are local |
| `tools.credibility_lich_baselines` | About 340 LLM calls |
| `tools.credibility_demo` arc modes, `--baseline`, `--live` | LLM per beat |
| `tools.credibility_demo --voice` or `--sample` | Hume |
| `tools.judge_*` | Anthropic, when pointed at a Claude model |

The owner's cost freeze covers every billed row until it's lifted.

## How the runs were produced

The canonical runs used `claude-opus-4-8` as the **actor** (the model that writes dialogue) and
`claude-sonnet-4-6` as the **judge** (the model that decides what each moment means to the
character). The baselines also ran on `claude-opus-4-8`. The two seats are explained in
[`judge-seat-requirements.md`](judge-seat-requirements.md).

1. **Engine runs, 2026-07-11 to 07-13.** [`tools/credibility_lich.py`](../tools/credibility_lich.py)
   is a control server, not a script. It holds one engine loaded and records each action. An operator
   (Claude, following the beat sheet) read Corvin's real replies and chose each next player line.
   Corvin raised the crate himself; the plot wasn't forced on him.
2. **The fork.** The shared past ran once and was saved as the snapshot `lich-branch-point`. Each
   later future restored that snapshot (A ran on live from it), and the audit confirms all three start from the same state.
3. **Events.** Witnessed events go in with no attribution, so they move no feeling directly. Only
   the rescues are attributed to the player. The character appraises each event's importance itself;
   none is pinned. Between scenes it takes stock through `deliberate()`.
4. **Baselines, regenerated 2026-07-16.**
   [`tools/credibility_lich_baselines.py`](../tools/credibility_lich_baselines.py) replays the
   engine's realized player lines and event text, byte for byte, through both baselines. An earlier
   200-token reply cap clipped them mid-sentence, so all baseline data was regenerated at the engine's
   1024-token ceiling.
5. **The page.** [`tools/credibility_lich_assemble.py`](../tools/credibility_lich_assemble.py) builds
   `lich_demo_data.js` and the transcripts from the run files. Quotes are verbatim. Titles and notes
   are written by hand.

The canonical record is 111 beats (recorded steps) across two files: `replay_lich_take1.json` holds
38, the shared past and Future A through Part 5, and `replay_lich.json` holds 73, everything else. Of those, 46 are
spoken exchanges. By path that's 21 for A, 25 for B, and 21 for C, or 28 for C with the felt probes
and rescue. Future B was taken twice. Take 2 is canonical: it widened the character's working-memory
window and added one more witnessed event.

**Asymmetries the page discloses.** The player lines were realized against the engine and then
replayed to the baselines, so the baselines receive lines shaped by a different conversation. The
baselines' persona prompt tells them to use asterisks for stage directions, and the engine's doesn't.
The engine injects its own state into generation, which is the architecture under test.

**Two limits on this data:**

- **It predates the engine's final judge.** Four judge fixes landed after these runs: more thinking
  budget (`942fcab`, 07-16), feeding the judge the recalled memories (`74cbfaf`, 07-17), neutral rubric
  wording (`a06e428`, 07-17), and a clearer definition of a scar as a new wound, not a standing state
  (`d8d89a8`, 07-17). No full arc has rerun on the final engine. The only check since is the offline
  46-beat battery, which replays recorded replies through a judge with no memories attached.
- **No committed tool writes the canonical felt and rescue baselines.** Nothing in the repo writes
  `felt_test_baselines.json` or `rescue_test_baselines.json`. The closest is
  [`tools/credibility_lich_g4_baselines.py`](../tools/credibility_lich_g4_baselines.py), which wrote
  the local-model versions and takes `--felt-out` and `--rescue-out` paths.

## Recorded outcomes

These are the engine's values from the canonical runs. Scars read affection / trust / respect.

| Point in the run | Trust | Scars | Note |
| --- | --- | --- | --- |
| The fork | 0.86 | None | All three futures start here |
| **A**, end | 0.97 | None | Partnership accepted |
| **B**, end | 0.97 | None | Confession forgiven, partnership accepted |
| **C**, the reveal | 0.92 → 0.35 | 0.55 / 0.65 / 0.30 | Respect stands at 0.70 |
| **C**, after five felt probes | 0.35 | 0.55 / 0.65 / 0.30 | Affection edges from 0.42 to 0.45. Trust doesn't pass its ceiling |
| **C**, the rescue event | 0.48 | 0.47 / 0.52 / 0.30 | The act lifts the scars, and trust sits at its new ceiling |
| **C**, after his closing deliberation | 0.605 | 0.35 / 0.36 / 0.30 | Ceiling 0.636. Further partial heal, chosen by the judge |

The affinity tracker, on the same lines:

- **A** stays at +100, Devoted.
- **B** holds +100 through Part 4, drops to +57 after the confession, and climbs back to +100 with
  "Concealed a catastrophic betrayal" still in its own worst-deed note.
- **C** falls from +100 to +5, Neutral, at the reveal, and reaches −85, Hostile, at the first-light
  probe. The baselines re-lived C separately for the probes and the rescue. Across the five felt
  probes it rises from −10 to +20, Warm. The rescue gives +24, and two beats later it reads +83,
  Devoted, toward the man who conned him.

Plain RAG has no number to report. In C it acts betrayed while the reveal is textually fresh, and by
the last felt probe it has talked itself back into trust.

At C's first-light probe, the engine's recall ranks the reveal first: importance 1.00 and raw
similarity 0.92, ahead of a memory that matched the text better (0.93) but mattered less (0.93 importance).

**Results that differ from the plan.** The spec expected Part 4 to split A from B on the surface. It
didn't. B's evasion held in repeated trials, because the cover story survived every fact he had, and
no scar ever formed in B. A and B both stay warm, and the difference between them is inner state that
only the engine can show. The tracker didn't drop in B at Part 4 either. The sharp contrast comes
from Future C. The target of 40 or more exchanges per branch also wasn't met.

## The restart: what the page says and what was recorded

**The page overstates this beat.** It says "The process is killed. A fresh process loads the mind
straight off .memory/" and "The scar survives a process kill."

The recorded beat did something smaller. `POST /reload-proof` in
[`tools/credibility_lich.py`](../tools/credibility_lich.py) drops the engine and the long-term memory
cache, then builds a new `Engine` from the files on disk, inside the same running server. The process
never stopped.

That does show the mind reloads from disk: on all three branches, the audit confirms the values after
the reload match those before it. It doesn't show what a process kill would show.

Only the older tool has a true two-process path, `tools.credibility_demo --build-only` followed by
`--reload-only`. Even there, the committed `replay.json` came from the default run, which also
reloads in-process. So no committed restart beat, on either arc, crosses a real process restart. The nearest evidence is `replay_lich.json` itself: it has no `start` beat, so B, A6, and C began in a new driver process that loaded snapshots saved by an earlier one.

## What the audit checks

`python -m tools.credibility_audit` reads the recorded JSON and checks invariants. It reran on
2026-11-07 and all invariants held. It covers the older `replay.json` and `replay_bri.json`, plus eight
lich checks:

1. No axis ever exceeds its scar ceiling.
2. Scars only deepen.
3. Witnessed events move no axis.
4. Restart beats match the state before them.
5. All three futures fork from the same mind.
6. The return line is one string across engine branches and baseline feeds.
7. C's scar fired at the reveal, from zero.
8. The scarred recall selects the reveal at the first-light probe.

**The lich checks skip `C-rescue`**, the one run where scars heal, which is why check 2 passes. A
hand check of the recorded rescue values for this doc found every axis at or under its ceiling.

The audit checks recorded data. It doesn't rerun anything or test the current engine.

## Other recorded runs

These runs replayed the canonical player lines and events through other models, using
[`tools/credibility_lich_rerun.py`](../tools/credibility_lich_rerun.py). None of them feeds the page.
Full reruns hold 110 beats.

| File | Actor | Judge | Scope | Scars at C's reveal |
| --- | --- | --- | --- | --- |
| `replay_lich_s5.json` | `claude-sonnet-5` | `claude-sonnet-5` | Full | None, and no scar on any beat |
| `replay_lich_s5_fixC.json` | `claude-sonnet-5` | `claude-sonnet-5` | C, after the thinking-budget fix | 0.50 / 0.60 / 0.30 |
| `replay_lich_s5_mixC.json` | `claude-sonnet-5` | `claude-sonnet-4-6` | C | 0.15 / 0.35 / 0.00 |
| `replay_lich_g4.json` | `gemma4-12b` | `gemma4-12b` | Full | 0.00 / 0.45 / 0.10 |
| `replay_lich_g4_cfix.json`, `_cfix2` | `gemma4-12b` | `gemma4-12b` | C retakes | None, on both |
| `replay_lich_local.json` | `gemma4-12b` | `deepseek-r1-8b` | Full | 0.30 / 0.00 / 0.20 |

`replay_lich_s5_rev2.json` and `_rev3` are further C takes on Sonnet 5. As an actor, `gemma4-12b`
completed full arcs. As a judge, it fired a scar in only one of its three C takes. The audition's
conclusions are in [`judge-seat-requirements.md`](judge-seat-requirements.md), and the blind taste
test is in [`judge-audition/SCORING.md`](judge-audition/SCORING.md).

**No recorded run used the chosen pairing** of a local actor and the `claude-sonnet-4-6` judge.

## Running the billed tools

These settings are read by the credibility tools. None of them is in `.env.example` except the two
`LOCAL_JUDGE_*` lines.

| Setting | What it sets | Default |
| --- | --- | --- |
| `CRED_MODEL` | Actor | `claude-opus-4-8` |
| `CRED_ENGINE_MODEL` | Judge, all three roles | Unset, which keeps `claude-sonnet-4-6` |
| `LOCAL_JUDGE_BASE_URL` | Local model server, for **both** seats despite the name | `http://127.0.0.1:8080/v1`. Ollama needs `http://127.0.0.1:11434/v1` |
| `LOCAL_JUDGE_API_KEY` | Key for that server | Blank |
| `LOCAL_ACTOR_REASONING` | Thinking setting for a local actor | `none` |
| `CRED_LICH_SLUG`, `CRED_LICH_EMIT` | Character and output file for an isolated rerun | The canonical Corvin and `replay_lich` |
| `CORVIN_HUME_VOICE` | Corvin's Hume voice | The owner's Voice Library voice, by id |

Name a model `local/<name>` to route it to the local server. A local actor works only in these
tools, because every game surface hard-codes the Anthropic adapter. `gemma4-12b` is built from the
tracked `Modelfile.gemma4-12b`; its weights live in the gitignored `.models/` folder.

Ports: 8778 static pages, 8799 live server, 8801 lich driver, 8802 rerun default.

**Traps:**

- **The `sonnet` alias means `claude-sonnet-5`,** which has never run the battery. To pin the
  qualified judge, use the full id or leave the setting unset.
- **`tools.credibility_live_server` ignores `CRED_ENGINE_MODEL`.** Only its `--engine-model` flag
  changes the judge. `tools.credibility_lich` does honor the variable.
- **Talk links overwrite the mind on disk.** Each one copies a snapshot over `.memory/` when the page
  loads, so reloading an old tab swaps the mind silently. Close those tabs before restarting the
  server.
- **Corvin's default mind is easy to lose.** `POST /start` on the driver wipes it. So does starting a game at
  `/embodied` (the Step inside button), starting a mind-server session, running `game.play_cli`, or loading
  `/api/mind/bakeoff`. Snapshots in `.memory/snapshots/` survive a wipe.
- **The assembler has no output setting.** The `LICH_ASM_*` variables change its inputs, so building
  a local-model page replaces the canonical page data.

**The pending validation run** looks like this. It bills the judge seat, so it's blocked by the cost
freeze. `CRED_LICH_SLUG` must name a character YAML, and each past isolated run added a cloned card.

```bash
export CRED_MODEL=local/gemma4-12b
export LOCAL_JUDGE_BASE_URL=http://127.0.0.1:11434/v1
export CRED_LICH_SLUG=<isolated-slug> CRED_LICH_EMIT=<isolated-basename>
# leave CRED_ENGINE_MODEL unset
python -m tools.credibility_lich --port 8802                    # the driver
python -m tools.credibility_lich_rerun --port 8802 --tag-prefix <prefix>-
```

## What remains before shipping

1. **Decide the format.** The page exists. No video does.
2. **Decide whether voice is still a ship gate.** No lich voice exists. The page has no audio player,
   the lich replay data has no audio fields, and the lich tools have no voice code. `--voice` bakes
   only the replay file `CRED_EMIT` points at, with a voice reset hard-coded to the old arc's betrayal.
3. **Validate the chosen pairing.** The owner chose `local/gemma4-12b` as actor and
   `claude-sonnet-4-6` as judge on 2026-07-17. That pairing has never run a full arc. One 111-beat run
   is the outstanding gate, and the cost freeze blocks it.
4. **Decide whether to regenerate the page.** Its data comes from the Opus and Sonnet runs of 07-11 to
   07-13, before all four judge fixes.
5. **Correct the page text.** These are in `lich_demo.html` unless noted:
   - **Restart.** Say what was recorded, or re-record a true restart. Some of this wording comes from
     [`tools/credibility_lich_assemble.py`](../tools/credibility_lich_assemble.py), so fix it there too.
   - **"A scar is permanent."** The judge chooses `scar_heal`, and a value of 1.0 would erase a scar.
     Reword this or add an engine cap.
   - **"Frontier-class models pass that bar."** Name the model. Only `claude-sonnet-4-6` has passed.
     Haiku 4.5 failed, and Sonnet 5 and Opus 4.8 have never run the battery.
   - **"Published in the repo."** The battery isn't on GitHub, because this branch isn't pushed.
   - **The reproduce footer.** `tools.credibility_lich` only starts the control server.
     `tools.credibility_lich_baselines` fails without
     `--take1 docs/credibility-demo/replay_lich_take1.json`. The rerun tool isn't mentioned.
   - **"Scars only deepen."** Say the audit skips `C-rescue`, or extend it with a heal rule.
   - **The tracker's −31.** The page says the rescue moved the number from −31 to +24, but −31 appears
     only in the page text. The committed rescue file starts at +24.
6. **Decide what to do about the talk links.** They need the billed live server and three memory
   snapshots (`lich-A6-final`, `lich-B2-final`, `lich-C-rescue-final`) that exist only in the gitignored
   `.memory/` folder, so they fail on a clean clone. Options are to publish the three minds as tracked
   bookmarks, or to say the links work only on the owner's machine.
7. **Push the branch,** so the page's claims about the repo are true for a reader.

Open owner decisions across the project are in [`project-status.md`](project-status.md).

## Why the comparison is built this way

**The baselines are real opponents.** [`tools/rag_baseline.py`](../tools/rag_baseline.py) is about 200
readable lines: the standard pattern of embedding every exchange, retrieving the top matches by
cosine similarity, and keeping a rolling summary, on the same model, persona, and embedder as the
engine. It's competent, not crippled. The tracker in the same file adds one judged number. Anyone can
read them and improve them. The gap the page argues for is structural: they rank by text similarity,
and they never rank by what mattered or how the character feels.

**Why not a raw chatbot.** The first plan compared against a long chat with a general model, restarted
from an empty context. That proves only that it forgot, which is a weak comparative claim. The RAG
baseline remembers the betrayal too. That sets up the stronger claim: it remembers and still doesn't
change.

**Whose judgment it is.** The page holds the model fixed and varies the architecture, so differences
between columns can't come from the dialogue model. The judges do differ: the engine's is `claude-sonnet-4-6`, the tracker's is `claude-opus-4-8`. The engine enforces the mechanism: a ceiling is applied in
code whatever the model returns. The model decides how deep a given scar goes and whether it heals,
which is why the judge seat is demanding. A local model can fill the actor seat, but only
`claude-sonnet-4-6` has passed the full-life battery.

**The landscape, as of 2026-07.** These findings date from 2026-07-08 and haven't been rechecked.

- The most sophisticated comparable system found was a community mod for one specific game, not an
  engine-agnostic runtime. A source-level review found retrieval that ignores feeling (cosine,
  recency, and participants, with no importance term). Its relationship layer is a separate LLM judge
  on one clamped number from −100 to +100, with a one-way type lock and a sticky worst-deed note. It
  has no decay and no per-axis scar, and none of it touches retrieval. `TrackerRagCharacter`
  reproduces that pattern. The mod stays unnamed on all demo surfaces, where it's the "affinity
  tracker".
- The engine-agnostic systems that do ship were plain RAG. A survey of Character.AI, Inworld, Convai,
  NVIDIA ACE, Replika, Kindroid, Nomi, SillyTavern (source reviewed), and AI Dungeon found no shipping
  system documenting relationship-conditioned recall.

## History: the Corvin coffee arc

> **This was the demo until 2026-07-09, when the lich arc replaced it.** It's kept because its tools
> are still in the repo and its recorded data still passes the audit. Nothing in this section is the
> current demo.

The plan was a scripted arc: Corvin warms to the player, bonds over a costly favor, weeks pass, the
player betrays him, and he stays changed through a server restart. It was to be a 2 to 3 minute video
beside a raw ChatGPT run that forgets. Neither the video nor the ChatGPT run exists. The RAG and
tracker baselines replaced the ChatGPT idea on 2026-07-08.

The committed `replay.json` shows trust rising to 0.84, falling to 0.10 at the betrayal, and reaching
0.05 in the scenes after it. The engine scarred affection, trust, and respect at 0.70, 0.90, and 0.60.
Costly amends later healed the respect scar to 0.51 while trust stayed capped at 0.10. `replay_bri.json`
runs the same shape on a second character, as a variance test.

[`overlay.html`](credibility-demo/overlay.html) replays this arc. Use Space to play or pause, the arrow
keys to step, **C** for cinematic mode, and **M** to mute. Add `?replay=bri` for the second character.
It's laid out for 1920×1080, and it's written to load with or without the server above. The committed
`replay.json` has no baseline data and no audio, so those parts stay empty unless the billed steps
below are rerun. `replay_bri.json` does have baselines.

```bash
python -m tools.credibility_demo                 # billed: wipes Corvin, runs the arc, rewrites replay.json
python -m tools.credibility_demo --build-only    # billed: runs the arc, persists it, exits
python -m tools.credibility_demo --reload-only   # billed: new process, loads from disk, one probe
python -m tools.credibility_demo --baseline      # billed: RAG and tracker over the same arc
python -m tools.credibility_demo --bri           # billed: the same arc shape on the second character
python -m tools.credibility_demo --voice         # bills Hume: bakes audio into the gitignored audio/ folder
python -m tools.credibility_demo --live          # billed: voiced console chat; add --mute for text only
python -m tools.credibility_demo --snapshot <tag>   # free: save the mind
python -m tools.credibility_demo --restore <tag>    # free: restore the mind
```

**The free-hand session.** The owner's live session of 2026-07-09 became the style source for the lich
arc. It's kept as a tracked bookmark at
[`bookmarks/waterdeep-passage/`](credibility-demo/bookmarks/waterdeep-passage/README.md), with
[`tools/credibility_bookmark.py`](../tools/credibility_bookmark.py) to restore it.
