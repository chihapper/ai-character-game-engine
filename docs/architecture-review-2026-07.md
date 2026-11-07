# Architecture review — 2026-07 (full-codebase)

> **Status (2026-11-07):** Frozen record, not a description of today's code. The review was written
> and last changed on 2026-07-01 (`717ff80`, `1cedaad`), and its body stays as written apart from two corrected dates. For the
> current picture, read [`project-status.md`](project-status.md),
> [`architecture-seams.md`](architecture-seams.md), and
> [`engine-game-contract.md`](engine-game-contract.md).
>
> What has changed since:
>
> - **Theme E's "keeper" and "retiring" labels are now inverted.** The project kept the modular
>   pipeline and did not adopt the full loop. The pipeline branch in `orchestrator/main.py`, with
>   `orchestrator/legacy_voice.py`, is the live voice runtime. `orchestrator/realtime/full_loop.py`
>   is a dormant spike selected only by `VOICE_RUNTIME=inworld_fullloop`. Read row 7 and "Verified
>   GOOD" item 8 with that in mind. Code comments still use the old labels, and `main.py` is now
>   823 lines.
> - **Row 6's harness migration never happened.** `tools/_harness.py` landed, but none of the 8
>   `tools/stress_*` scripts moved to it and `tests/` doesn't use it. Only three credibility tools
>   and three judge tools do.
> - **Row 5 left one item undone.** `_character_summary` never moved onto `Character`. It is still
>   a private function in `orchestrator/salience.py`.
> - **"No automated tests" (Theme F) is out of date.** On 2026-11-07, 72 tests passed on
>   `credibility-demo`, 65 on `main`, and 60 on `game-rpg`.
> - **"Hard-wired to Anthropic" (Theme C) is partly out of date.** On `credibility-demo`, a model
>   named `local/<name>` sends judgment calls to an OpenAI-compatible local server. Game surfaces
>   still hard-code the Anthropic adapter for character replies.
> - **"Verified GOOD" item 7 no longer holds.** Both face adapters read `os.environ` directly. On
>   `credibility-demo`, so does `llm_openai_compat.py`, and `tts_providers.py` writes to it.
> - **Theme G:** the `_games` dicts are now bounded: `game/web.py` allows 5 active games, and
>   `game/arena/web.py` replaces the old game when a new one starts. Still open: the cwd-relative
>   globs in `game/arena/demo_perception.py`, and `experiment_log` editing a tracked doc.
> - **The closing deferrals:** per-engine model overrides, the `_safe_name` hash suffix, and the
>   REST routers are still not done. The cross-process store convention is partly done: the Ferry
>   web game isolates its namespaces per run, but the arena and mind server still share them.

> Four parallel reviews (engine core · memory subsystem · servers/adapters · cross-cutting), synthesized
> and de-duplicated. Scope per request: the engine + infrastructure (what's on `main`); game-layer (branch)
> observations are marked FYI. Findings are grouped by THEME because the reviews converged — several issues
> were independently found by 2-3 reviewers. Each theme ends with a recommended direction, not a patch.
> Point-in-time document (working tree as of 2026-07-01).

---

## Verdict in one paragraph

The **load-bearing architecture is sound and verified**: the engine↔game dependency direction is genuinely
one-way (grepped three ways — zero `game` imports in `orchestrator/`), the applied-vs-returned contract
matches the code signature-for-signature, the RR scorer is a clean pure module, and the settled design
principles (asymptotic curves, psychology-in-prompt, opaque clock) are consistently honored. The real
architectural debt is concentrated in **two HIGH-severity clusters** — state integrity (non-atomic writes +
zero concurrency control on the character's mind) and configuration-by-global-mutation — plus one
**missing abstraction** (the copy-pasted LLM-judgment pattern) whose absence makes everything else harder.
Notably, both HIGH clusters directly threaten the #30 matched-pair experiment's validity, so they're not
just "production someday" concerns.

---

## Theme A — State integrity: the character's mind can be silently lost (HIGH)
*Found independently by: memory, engine-core, and servers reviewers.*

1. **Non-atomic whole-file rewrites.** Every store writes with mode `"w"` (truncate-then-write), no
   temp-file + `os.replace`, no fsync — `long_term._rewrite`, `commitments._save`, and `write_text` in
   relationship/intent/agency stores. A crash mid-rewrite leaves a truncated file; `_load` silently skips
   bad lines, so corruption is invisible and made permanent by the next rewrite. With reinforce-on-recall
   ON, the **read path rewrites the whole file every retrieve** — a corruption window every turn.
2. **Zero concurrency control, lost updates reachable today.** (a) Two live `LongTermMemory` instances per
   namespace exist in one process (voice WS constructs fresh per session at `main.py:963`; sandbox caches
   per slug) — each caches `_records` and rewrites *its own copy as the whole truth*, so instance B can
   erase instance A's appends. (b) Within one instance, `asyncio.to_thread` workers mutate the shared list
   with no lock while the loop reads it. (c) Across *processes*, both servers (8000/8001) open the same
   JSONL files. (d) No lock on `Engine` either: a backgrounded `reflect()` races the next turn's
   `prepare()`; both call `_age_relationship → save()`.
3. **`readonly` means three different things** across the sibling stores (frozen vs
   mutates-in-memory-but-doesn't-persist vs inconsistent-within-one-store). Readonly is the safety rail
   for eval/replay/blind-eval — divergent semantics breaks experiment reproducibility.
4. **Corruption → silent amnesia.** relationship/intent load does `except Exception: return fresh-default`
   — a truncated relationship file silently resets to neutral (a vanished betrayal scar: invisible AND
   thematic), and the next save makes it permanent. No log.
5. **`_safe_name` collisions** can merge two characters' minds (`"bri!"`/`"bri?"` → `bri`; all-non-ASCII →
   `default`). Latent with authored slugs; real at scale/localization.

**Direction — one piece of work fixes all five:** a small shared `NamespaceStore` base owning path
construction, **atomic write** (tmp + fsync + `os.replace`), a **per-namespace instance registry + lock**,
**one readonly contract** (frozen), and **loud corruption handling** (quarantine to `.corrupt`, log at
error). The five stores keep their domain logic. Additionally: batch-embed at load (fastembed accepts
lists; currently one-at-a-time — full-history re-embed per WS session), and consider append-only
reinforcement events folded at load so reads stop rewriting.

---

## Theme B — Configuration by global mutation (HIGH)
*Found independently by: engine-core and servers reviewers.*

`get_settings()` is an `lru_cache` singleton, and the sandbox + game layers **mutate it at request time**
(`s.relationship_state = True`, `_apply_models` rebinding `salience_model`…). Consequences:
- One sandbox click flips affect features ON for every engine created afterward, process-wide, permanently
  (a ratchet — never unset). A sandbox model A/B silently swaps the **voice runtime's** bookkeeping model.
- Semantics are **inconsistent**: `LongTermMemory` *snapshots* settings at construction while `Engine`
  reads them *live* per call — a runtime mutation half-applies depending on the subsystem.
- **Two engines cannot have different minds in one process** — which is exactly what the #30 matched-pair
  (control + treatment arms) needs.

**Direction:** per-Engine capability config — `Engine(character, llm, caps=…)` with a frozen snapshot
defaulted from `Settings` at construction; `get_settings()` becomes env-derived process defaults only. The
repo already contains the right pattern in miniature (per-character `game_data.engine` overrides like
`memory_readonly`) — extend that shape. Also matches the settled "game-dependent semantics live in the
game layer" rule.

---

## Theme C — The missing "judgment call" abstraction (HIGH-leverage refactor)
*Found independently by: engine-core and servers reviewers.*

The pattern *construct fresh `AnthropicLLM` → stream-accumulate → regex `\{.*\}` → `except: log+fallback`*
is copy-pasted **9×** (agency ×3, salience ×4, consolidation, consistency) and each call builds a fresh
`AsyncAnthropic` client/connection pool. Only `deliberate()` has truncation salvage — the other eight lose
everything on truncated JSON. `_character_summary` is a *private* salience function imported by four
modules (with a stale "avoid import cycle" workaround guarding a cycle that doesn't exist). Model knobs
flow three incompatible ways (config fields read in helpers / explicit args / sandbox global mutation).

**Direction:** one `judgment(system, prompt, *, model_role, max_tokens, parser, fallback)` helper with a
shared client + salvage logic, plus a role→model factory (`llm_for("salience"| "deliberation"|…)`); move
`_character_summary` onto `Character`. Every future cognitive faculty then gets client reuse and
truncation-recovery for free, and mutation-route (c) dies. Related honesty item: the mind is hard-wired
to Anthropic despite the adapter rule — either document that as deliberate in the contract doc, or thread
the factory through `Engine`.

---

## Theme D — Seam completeness: `choose_action` (MEDIUM, **demo-relevant now**)

The new embodied-action seam is architecturally right (bounded to game-supplied options, agnostic) but:
- it's **not on the `Engine` surface** — the game imports `orchestrator.agency.choose_action` directly, and
  the contract doc (which claims to be "the whole seam") doesn't mention it;
- it takes a **bare `Character`**, so an embodied NPC picks actions **blind to its scars, relationship,
  evolved goals, beliefs** — Corvin chooses without being the Corvin the engine knows.

**Direction:** fold it into `Engine` (where it can reuse the same grounding as `deliberate`) and add it to
`docs/engine-game-contract.md` **before** Phase-B embodiment builds on the wrong entry point. This is the
one finding worth fixing *during* the current demo cycle — it directly deepens the embodied arm.

---

## Theme E — Fence the retiring path (MEDIUM)

`orchestrator/main.py` (1,236 lines) holds ~9 concerns, and the **keeper** (the ~230-line full-loop
runtime — the committed Track V direction) is interleaved with ~350 lines the docs say to delete
(pipeline WS branch, calibration WS, STT factory). Retirement is currently a scalpel job inside one file.

**Direction:** decompose **by fate, not by topic** — (a) full-loop runtime + its helpers into
`orchestrator/realtime/`; (b) the retiring branches into one `legacy_voice.py` router so retirement =
delete one file + one `include_router`; (c) character/voice REST into routers. Don't polish retiring code.

---

## Theme F — Verification: a concrete, cheap test seam (MEDIUM)

There are **no automated tests**, yet the most-tuned, most-regression-prone code is pure and testable with
zero LLM calls:
1. `memory/relevance.py` — the RR scorer/MMR/decay math (the crown jewels, currently protected only by
   expensive manual stress runs);
2. `memory/relationship.py` — asymptotic curves, scar caps, age-decay (settled principles a silent
   regression would re-litigate);
3. `context.py` — arena query + situation/context rendering;
4. `game/arena/world.py` + `perception.py` (FYI, branch) — pure state math, and it's *actively* regressing
   (the last three commits were map-bug fixes);
5. `game/experiment_log.py` (FYI, branch) — already validated by hand with a temp doc; codify it.

Plus a ~40-line `tools/_harness.py` (set_flags / wipe / make_engine) to replace the boilerplate copy-pasted
across ~17 stress scripts — which then doubles as the pytest fixture layer.

---

## Theme G — Hygiene batch (LOW, fast)

- **cwd-relative wipe/save paths** (`glob(".memory/…")` in sandbox + game) vs the absolute
  `settings.memory_dir` — launched from any other cwd, resets/saves silently no-op → corrupts experiment
  determinism. Derive from `settings.memory_dir`/`ROOT_DIR`. *(Highest-value item in this batch.)*
- **Scenario path allow-list**: `POST /api/game/new` accepts an arbitrary filesystem path as `scenario`
  (arbitrary-file-read + wipes cast memory as a side effect). One-line allow-list to `game/scenarios/`.
- **Contract doc flag-defaults are wrong for 4 of 7 flags** (salience_scoring, relationship_time_decay,
  recent_happenings, arena_query all default ON); table also omits commitment/contradiction detection.
  (The doc is otherwise verified code-accurate — worth keeping it that way.)
- **`.env.example` omits `ELEVENLABS_API_KEY`** — the *default* TTS provider's key; fresh clones launch
  keyless.
- **Stale markers**: architecture-seams still shows temporal decay as ⬜ (it shipped); `relationship.py`'s
  module NOTE says time-decay is "deferred" (it's implemented); `requirements.txt` header still says
  ChromaDB; `engine.py` references `docs/ENGINE_GAME_CONTRACT.md` (wrong case).
- **Unbounded `_games` dicts** in the two game web APIs (FYI, branch) — abandoned tabs leak engines;
  cap or idle-TTL before any shared deployment.
- **`experiment_log` machine-edits a tracked doc** (FYI, branch) — every playthrough dirties the working
  tree; consider a gitignored runs file the protocol doc links to.
- **Namespace hash suffix** for `_safe_name` (see Theme A.5).

---

## Verified GOOD — do not "fix"

1. **The engine↔game seam is real in the code**: zero orchestrator→game imports (checked module-level,
   function-level, bare-word); game imports only the public surface; applied-vs-returned executed exactly
   as documented; no game concept named in engine core; the reaction recipe + threshold live game-side.
2. **`memory/relevance.py` as a pure scorer** — no I/O, no settings import; injected weights; the same
   scorer reused for deliberation ranking. Keep it storage-free.
3. **Embeddings derived at load, never persisted** — embedder swaps safe by construction; store stays
   human-readable. Fix the load cost by batching/caching, never by persisting vectors.
4. **`game_data` + `register_game_extension`** — the registration-point + neutral-channel template, with
   isolated renderer failures.
5. **The opaque numeric clock discipline** — differenced everywhere, parsed nowhere.
6. **Psychology-in-prompt, geometry-in-code** — asymptotic curves character-blind; forgiveness semantics
   in the reflection rubric. Settled; leave it.
7. **`config.py` as the single env seam** — verified: no `os.environ` reads elsewhere in `orchestrator/`.
8. **Full-loop per-turn context discipline** (delete-then-add one RR context item; stable cacheable
   prefix) — the pattern to judge Track V work against.
9. **Server duplication (cache-busting/static-mount) between the two servers: keep it** — a shared helper
   would either put web plumbing in the engine or invent a third package for 40 lines.

---

## Recommended sequencing — ALL SEVEN LANDED (2026-07-01, commits 70ef84d..b680295)

| # | Work | Themes | Status |
|---|------|--------|--------|
| 1 | `choose_action` → Engine surface w/ full grounding + contract doc | D | ✅ `70ef84d` — Corvin now acts from lived state |
| 2 | Hygiene batch (paths, allow-list, doc fixes, .env.example) | G | ✅ `b91a033` |
| 3 | `NamespaceStore`: atomic writes + shared truth/locks + frozen readonly + quarantine | A | ✅ `40e8608` — 13/13 integrity checks |
| 4 | Per-Engine capability config (EngineCaps snapshot) | B | ✅ `d6d82ba` — in-process matched pair now possible |
| 5 | `judgment()` layer: shared client + salvage everywhere + role→model table | C | ✅ `74ce139` |
| 6 | Test seam: pytest, 38 pure unit tests + tools/_harness | F | ✅ `2c8c211` |
| 7 | main.py decompose-by-fate (full_loop.py keeper / legacy_voice.py quarantine) | E | ✅ `b680295` — 1,236→815 lines, route table byte-identical |

Deliberately NOT done (noted for later): per-engine *model* overrides (sandbox still sets role models
globally — dies naturally when models move onto EngineCaps or the factory is injected through Engine);
`_safe_name` hash-suffix (would orphan existing on-disk stores — needs a migration); cross-process
store convention (two servers, one .memory — run-scoped namespaces when the #30 runs get formal);
extracting the character/voice REST into routers (keeper code, cohesive — do with the Track V cutover).
