# Project status

**Snapshot date: 2026-11-07.** The newest commit on any branch is from 2026-07-17, so nothing here
has changed since then. This page records what was actually checked and what is true today. It is
dated on purpose: refresh or delete it rather than letting it age quietly.

## The short version

- The character engine is real and its automated tests pass on all three lines of work.
- The newest work is **not on GitHub's default branch**. GitHub's `main` holds the engine and older
  clients. The Godot RPG and the credibility demo exist in full only on the owner's PC.
- The three lines have not been merged. No single branch is "the whole project" today.
- Paid-model testing has been frozen by the owner since 2026-07-17, so nothing that calls an LLM,
  text-to-speech, or speech-to-text service was exercised for this snapshot.

## Where the code lives

| Line of work | Where it is | What it holds | Tests (2026-11-07) |
| --- | --- | --- | --- |
| `main` | GitHub default branch | Engine, Ferry text game, grid arena, mind server, Director's Sandbox, frozen Unity and Unreal source | 65 passed |
| `credibility-demo` | This PC only | Everything on `main`, plus the lich demo, judge audition data, TTS provider registry, local-LLM adapter, and the scar wording fix | 72 passed |
| `game-rpg` | This PC, 70 commits ahead of GitHub | Godot 4.7 client (1,540 files), `game/rpg/` rules and dungeons, `LICENSE-SRD.md` | 60 passed |

GitHub's `origin/game-rpg` stops at `512da31` (2026-07-06), before the Godot client existed. The
first 27 `credibility-demo` commits are reachable on GitHub through the pushed tag
`demo-waterdeep-passage`, which predates the lich demo.

**Backup risk:** 148 commits exist only on this PC. If this machine were lost, the Godot client and
the lich demo would go with them. Also not in git anywhere: `.env`, `.memory/` (the characters'
minds), `.saves/`, the painted portraits in the untracked `godot/` folder, and the full Unreal and
Unity projects outside this repo.

**Branch merge outlook.** No engine fix is stranded on `game-rpg`; its six engine commits were
hand-ported to `main` in `d132cc9`. Merging `game-rpg` into `credibility-demo` gives three text
conflicts (`.gitignore`, `orchestrator/main.py`, `orchestrator/adapters/tts_hume.py`), plus four doc conflicts once this pass's edits are committed (`README.md`, `docs/architecture-seams.md`, `docs/embodied-demo-architecture.md`, `docs/engine-game-contract.md`), and two things
need attention beyond the conflicts:

1. `game/rpg/voice.py` creates a new `HumeTTS` for every line. After a merge, voice continuity across
   turns would silently stop, because continuity is now held per adapter instance.
2. The `voice_ready` fix in `game/bridge/mind_api.py` (`e3cbf61`) exists only on `game-rpg`. This merge carries it over cleanly, but `main` stays without it until then.

The `game-rpg` engine also lacks all the judge fixes from 2026-07-16 and 07-17, so playing the RPG
today uses an older judge than the one this repo's docs describe.

## What was checked

Run on 2026-11-07 with all API keys blanked or fake, so nothing could bill.

| Check | Result |
| --- | --- |
| `pytest tests` on all three lines | 72, 65, and 60 passed, 0 failed |
| Byte-compile `orchestrator`, `game`, `tools`, `tests` | Clean |
| Load `orchestrator.main`, request `/` | 200 |
| Load `game.server`, request `/`, `/play`, `/embodied` | 200 each |
| `python -m game.rpg.gencheck` (`game-rpg`) | All generators and content pass |
| `python -m game.rpg.harness vault emberdeep` (`game-rpg`) | Both pass all 5 checks, with no AI calls attempted |
| `python -m game.rpg.harness` with no argument | Crashes on the third slice. See defect 7 below |
| `python -m tools.credibility_audit` | All invariants hold on the recorded data |
| Open `lich_demo.html` in a browser | Loads with 6 sections and no console errors. No audio; 6 links need the paid live server |

**Not checked:** a live conversation with any character, any voice output, the Godot client itself,
the Unity or Unreal clients, Whisper speech-to-text (not installed in the dev environment), and the
AssemblyAI and Hume live docs. The model names pinned here may have changed since July.

## Where each workstream stopped

**Engine.** The mind is feature-complete for this phase: recall, salience, relationship, scars,
intent, beliefs, commitments, contradiction detection, world events, and autonomous deliberation.
Its broad validation harnesses (`tools/stress_*`) were last run in June 2026, before the July judge
changes. The newest engine-level check is the offline judge battery of 2026-07-17, which replays
recorded replies with no memories attached.

**Judge seat.** The audition closed 2026-07-17. Open models pass the single hard moment, but none
held up over the 46-beat full-life battery. Only `claude-sonnet-4-6` has passed it. Haiku 4.5 and
DeepSeek-R1-distill 8B and 14B failed. Sonnet 5 and Opus 4.8 have never run it. Details are in
[`judge-seat-requirements.md`](judge-seat-requirements.md).

**Owner's seat decision (2026-07-17).** Actor: `local/gemma4-12b`, free through Ollama with thinking
off. Judge: `claude-sonnet-4-6`, estimated then at 1 to 1.5 cents per exchange, or about $1 to $1.50
per player session against $3 to $5 all-cloud. These are unmeasured estimates. **This exact pairing
has never run a full arc together.** One 111-beat validation run is the outstanding gate, and it is
blocked by the cost freeze. Separately, no full arc has run with any judge since the scar wording
change (`d8d89a8`), so the final engine has never been through one. The local actor works only
through the credibility tools, because every game surface hard-codes the Anthropic adapter.

**Credibility demo.** The lich arc page (`docs/credibility-demo/lich_demo.html`) is built and viewable
for free. Remaining before it ships:

- Decide the final format. The page exists; no video does.
- Decide whether voice is still a ship gate. No lich voice bake exists, and the page has no player.
- Run the pairing validation, and decide whether to regenerate the page. Its engine data comes from the
  Opus actor and Sonnet judge runs of 07-11 to 07-13, and its baseline exhibits from a 07-16 regeneration, all before the four judge fixes.
- Fix the restart wording. The page says the process is killed at the restart beat, but the recorded
  beat is an in-process cache drop and reload. `tools/credibility_demo.py` has `--build-only` and
  `--reload-only` modes for a true two-process restart, but no committed recording used them.
- Decide what to do about the talk links. They need the live server, which bills per turn, and
  gitignored memory snapshots, so they fail on a clean clone.
- Check two page claims. The tracker's −31 starting figure is hard-coded in the page and appears in
  no recorded data. The page also says everything can be reproduced, but no committed tool writes
  `felt_test_baselines.json` or `rescue_test_baselines.json`.

**Godot RPG (`game-rpg`).** Playable by design, idle since 2026-07-08. Python owns all rules and
Godot 4.7 is a thin renderer over a local WebSocket. It has three slices. `vault` and `emberdeep`
complete end to end. `graywater` is a social town with five NPCs and no completable objective yet,
because the letter can't be delivered. Slices don't connect to each other.

Not built yet: the rest of the campaign, class choice, equipment and shops, ranged combat, spells,
applied conditions, voice input, scheduled NPC deliberation, native packaging, and any `pytest`
coverage of `game/rpg/`.

**Unity and Unreal clients.** Frozen history, not active work. Unity last changed 2026-07-02 and
Unreal 2026-07-04. Their API calls still match the mind server on a static read, but neither has
been run since 2026-07-05. Neither can be rebuilt from this repo alone.

**Face and lip-sync.** Paused. The Godot talk scene uses voice-amplitude motion instead.

**Embodiment experiment (#30).** 210 runs logged, none evaluated. No judge or emergence-scoring tool
exists. The owner needs to decide whether this is live, parked, or abandoned.

## Known defects

These are real code issues found during this review. **None were changed**, because this pass
touched documentation only.

| # | Issue | Effect |
| --- | --- | --- |
| 1 | `numpy` is in no requirements file, but `tts_hume.py` imports it | Hume fails on a core-only install. It works when the optional packages pull numpy in |
| 2 | `run.sh` is not marked executable in git | `./run.sh` fails on a fresh Mac or Linux clone. `bash run.sh` works |
| 3 | `voice_ready` in `mind_api.py` ignores `HUME_API_KEY` on `main` and `credibility-demo` | With `GAME_TTS=hume` and no ElevenLabs key, `/speak` returns 404 |
| 4 | Starting `/embodied`, starting a `/api/mind` session, running `game.play_cli`, or just opening `/api/mind/bakeoff` deletes `.memory/corvin-ashgrave-inworld.*` | Silently wipes the credibility demo's default mind |
| 5 | The `sonnet` alias in `tools/credibility_demo.py` means `claude-sonnet-5` | `--engine-model sonnet` selects a judge that has never passed the battery |
| 6 | `tools.credibility_live_server` ignores `CRED_ENGINE_MODEL` | Its `--engine-model` flag or the `SALIENCE_MODEL`, `REFLECTION_MODEL`, and `DELIBERATION_MODEL` env vars change the judge; `CRED_ENGINE_MODEL` does not |
| 7 | `game.rpg.harness` assumes every slice has a fight and a door | Crashes on `graywater`. A harness limit, not a game bug |
| 8 | `commitment_detection` is off on all game surfaces on `main` and `credibility-demo` (the `game-rpg` RPG turns it on) | Judges there never see open promises, though the judge doc implies they do |
| 9 | `.mcp.json` fails to start (no `mcp` package, hard-coded path) | The Unreal MCP server errors at each session start |
| 10 | `scar_heal` of 1.0 can fully erase a scar | Conflicts with the demo page's "permanent" wording |
| 11 | `.gitignore` here doesn't cover root logs, `godot/`, `asset_library/`, or `.saves/` | `git add -A` on this branch would stage them. Stage files by name |
| 12 | Code comments still call the pipeline "retiring" and the full loop the "keeper" | The opposite was decided |
| 13 | Three test clones (`corvin-ashgrave-g4`, `-loc`, `-s5`) are tracked in `orchestrator/characters/` | Four identical "Corvin Ashgrave (Inworld)" entries appear in character lists |
| 14 | `_parse_reflection` in `salience.py` drops malformed JSON with no salvage and no log | A garbled per-turn judgment silently applies no relationship update, despite the "never mute" principle |
| 15 | `Engine._agency_grounding` reads two game-named `Situation.extra` keys by their literal text | Breaks the rule that engine code names no game concepts |
| 16 | On `game-rpg`, `minds.py` requests `reinforce_on_recall`, which `EngineCaps` doesn't have | The request is silently dropped |
| 17 | `spikes/evi_clm_server.py` has no authentication and binds all interfaces | Dangerous if run on an open network. Removed on `game-rpg` but still on `main` and here |

## Decisions the owner needs to make

1. **Priority.** Godot RPG, credibility demo, or both?
2. **Branches.** Push `credibility-demo` and `game-rpg` for backup (about 82 MB more on GitHub), and
   choose which line becomes the new `main`.
3. **The port 8000 app.** Wire it to `Engine`, or keep documenting it as a memory-only voice demo?
4. **Hume as default.** It's the chosen voice, but `GAME_TTS` and `DEFAULT_TTS_PROVIDER` don't select it. Only the credibility live server and the RPG server have it written into their code.
5. **Local actor.** Make it a first-class option on game surfaces, or keep it tools-only?
6. **Retirements.** Are Unity, Unreal, the face layer, and the unadopted Inworld full loop retired?
   Does `/api/mind` stay supported, given that the Godot client doesn't use it?
7. **Before any public release.** There is no root licence. The vendored Unreal plugin names no
   upstream source. The `waterdeep-passage` name uses a published setting, and `LICENSE-SRD.md`
   recommends IP-attorney review before commercial release. Some docs and the runs table also contain
   local Windows paths with the owner's username.
8. **Cost freeze.** When does it lift, and is the single pairing run the agreed last gate?

## GitHub issue triage

This is a recommendation only. No issue was changed.

| Status | Issues |
| --- | --- |
| Done or superseded, candidates to close | [#11](https://github.com/chihapper/ai-character-game-engine/issues/11), [#26](https://github.com/chihapper/ai-character-game-engine/issues/26), [#35](https://github.com/chihapper/ai-character-game-engine/issues/35), [#38](https://github.com/chihapper/ai-character-game-engine/issues/38), [#41](https://github.com/chihapper/ai-character-game-engine/issues/41), [#42](https://github.com/chihapper/ai-character-game-engine/issues/42) |
| Premise out of date, rewrite | [#28](https://github.com/chihapper/ai-character-game-engine/issues/28), [#36](https://github.com/chihapper/ai-character-game-engine/issues/36) |
| Partly done | [#37](https://github.com/chihapper/ai-character-game-engine/issues/37), [#39](https://github.com/chihapper/ai-character-game-engine/issues/39), [#40](https://github.com/chihapper/ai-character-game-engine/issues/40) |
| Still open | [#27](https://github.com/chihapper/ai-character-game-engine/issues/27), [#30](https://github.com/chihapper/ai-character-game-engine/issues/30), [#31](https://github.com/chihapper/ai-character-game-engine/issues/31), [#33](https://github.com/chihapper/ai-character-game-engine/issues/33), [#43](https://github.com/chihapper/ai-character-game-engine/issues/43) |

The GitHub repo description is also out of date: it says the engine drives Inworld's full-loop voice
agent, which was never adopted. Low `#` numbers in `game-rpg` commit subjects are local task IDs, not
GitHub issues.

## Docs still to update on `game-rpg`

Those files live on another branch, so this pass didn't touch them. When that branch is next worked
on:

- `README.md`: replace it with the unified README from this branch. Its RPG section omits
  `graywater`, the 3D default, and the client settings.
- `docs/godot-game-build-plan.md`: add a status banner, keeping the owner's spec intact.
- `docs/godot-build-step0-inspection.md`: add a banner. Its decisions are settled.
- `docs/campaign-proposal.md`: add per-item status. This is still the live plan for unbuilt work.
- `docs/visual-polish-roadmap.md`: update Track 2, Track 3, and the sequence. Track 1 still holds.
- `godot/assets/portraits/README.md`: its licence table no longer matches the files.
- `godot/project.godot`: the project is still named "Sunken Vault" despite having three slices.

Most docs updated in this pass exist on those branches too, in their old form. The exceptions are the `docs/credibility-demo` docs, `docs/judge-audition/SCORING.md`, and `docs/tts-providers.md`, which exist only here, and `docs/judge-seat-requirements.md`, which isn't on `game-rpg`. Until the branches are
reconciled, `main` keeps the old text. That includes the judge doc's outdated verdicts and the
contract doc's code examples that crash.
