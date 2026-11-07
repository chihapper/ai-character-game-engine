# Unreal Demo Port — what carries over, what rebuilds, what changes strategy

> **Status (2026-11-07):** Frozen history, not active work. The Unreal client was last changed on
> 2026-07-04 (`bb1e572`) and has not been run since 2026-07-05. A static read on 2026-11-07 shows
> its API calls still match the mind server, but no test covers that. The front-end review
> mentioned below ended in a Godot client, built 2026-07-06 to 07-08 on the `game-rpg` branch, and
> that client doesn't use the mind server. The Unreal client can't be rebuilt from this repo alone:
> git holds its C++ source, editor scripts, and the MCP plugin, but no `.uproject` and no `Content`.
> The full project is on the owner's PC. For the current picture, read
> [project-status.md](project-status.md).

> **Earlier status (2026-07-05):** the Unreal client works — NPCs speak (Hume) and the engine drives
> them end-to-end. The **face/lip-sync layer is paused**, and the **front-end direction is under
> review**: a 2D game on **Godot** is being considered. None of that touches the engine or the
> mind server — the whole point below is that the front-end is swappable. Treat this doc as the
> Unreal-specific port record, not a committed roadmap.

Decision (2026-07-02): the demo client moves to Unreal Engine. The prior Unity client
(`unity/pro/`) stayed on the `sandbox` branch as a working reference implementation, and the
`unreal-demo` branch hosted the port. Both branches are gone and survive as tags `archive/sandbox`
and `archive/unreal-demo`. `unity/pro/` and `unreal/` are now on `main`, `credibility-demo`, and
`game-rpg`. The mind is untouched — that was always the design.

## Ports UNCHANGED (the actual product)

- **The engine** (`orchestrator/`; the core is `orchestrator/engine.py`): the RR-driven character minds. Zero changes.
- **The mind server** (`game/bridge/mind_api.py`): FastAPI over HTTP on :8001. Unreal speaks
  HTTP natively (`FHttpModule`). Same endpoints: `/session`, `/respond`, `/choose`,
  `/observe`, `/acted`, `/speak` (PCM + X-Sample-Rate), `/speak_anim`, `/stt`, `/finish`.
- **Scenario + policy + casting** (`game/scenarios/ferry_crossing.yaml`, `game/policy.py`,
  `game/casting.py`): engine-side, engine-owned. The react recipe, salience thresholds,
  name/acquaintance rules — all as-is.
- **The contract** (`docs/engine-game-contract.md`): engine owns the MIND, game owns the
  WORLD. Unreal is just a different WORLD.
- **Voice**: TTS (**Hume Octave**, chosen after a bake-off) / AssemblyAI STT already flow
  through the mind server, so the voice pipeline ports by doing nothing. Hume isn't automatic: the
  mind server defaults to `GAME_TTS=inworld`, so you must set `GAME_TTS=hume`. On `main` and
  `credibility-demo`, `/speak` also returns 404 without an ElevenLabs key, because `voice_ready`
  checks the wrong key. Only `game-rpg` has the fix (`e3cbf61`).
- **Face / lip-sync** *(explored, paused)*: audio→ARKit-blendshape lip-sync (NVIDIA Audio2Face)
  was wired through the mind server's `/speak_anim` and drove a MetaHuman face here. Self-hosted
  **NeuroSync** then replaced Audio2Face on the server with the same wire shape, but no commit
  shows it driving Unreal. The layer is **on pause** — see the status notes above and the
  [engine/game contract §7.5](engine-game-contract.md). The Godot talk scene uses voice-amplitude
  motion instead.

## Re-implements in Unreal (the client layer — designs proven in Unity, code rewritten)

| Unity (unity/pro/Scripts) | Unreal equivalent |
|---|---|
| NpcAgent (perceive→choose→enact loop, affordance option lists, seats, poses) | `ANpcAgent` actor + Blueprint/C++ component; options built the same way |
| PerceptComposer (who can SEE what) | line traces (`LineTraceSingleByChannel`) |
| Regions (named anchors) | tagged `ATargetPoint`s |
| DialogueUI / thought sidebar / nameplates | UMG widgets + `UWidgetComponent` |
| VoiceClient (HTTP PCM → positional audio) | `FHttpModule` → `USoundWaveProcedural` |
| StoryDirector (night spine: warrant → bell → dawn) | level Blueprint / director actor |
| BodyLanguage (voice-envelope head motion, lean-in, laugh) | Anim Blueprint layer + curves |
| WorldClock, StormAudio, PlayerController | trivial re-implementations |

That table was the plan. As built, read from `unreal/Source/FerryInn` on 2026-11-07:

- Percepts come from 2D distance and the nearest named region (`ANpcAgent::ComposeSituation`), with
  no line traces. `/observe` treats everyone in the taproom as a witness.
- Regions are a hard-coded map in `FerryRegions.h`, not tagged `ATargetPoint`s.
- On-screen text uses `GEngine` debug messages. There are no UMG widgets.
- Voice playback uses `USoundWaveProcedural`, as planned.
- There is no story director and no night spine.

## STRATEGY CHANGES (the lessons, encoded)

1. **No more scene-building from planks.** The single biggest failure mode of the Unity
   client was agent-authored architecture from kit pieces. In Unreal the environment is a
   COMPLETE prebuilt tavern/inn from FAB (free + cheap options; Quixel Megascans free with
   UE). The agent wires minds INTO a scene; it does not lay the bricks.
2. **MetaHuman characters from day one** (roadmap #42 becomes the default): native in UE,
   real faces, audio-driven facial animation. Mixamo + UAL clips retarget via IK Retargeter.
3. **Live-loop verification from day one**: Unreal ships remote Python editor scripting and
   console capture (`HighResShot`) — the QBridge lesson (persistent editor, seconds-long
   iteration, live state reads) is the FIRST thing stood up, not the last. The Unity rig's
   checks port as concepts: layout audit, seat/pose live-reads, gesture proofs, POV
   walkthrough captures.
4. **Verification language**: "verified under these checks" — never "fixed" without the
   photo/live-read that proves it.

## Machine prerequisites (as of 2026-07-02, since met)

Both were met. UE 5.8 is installed at `C:\Program Files\Epic Games\UE_5.8`, the project is at
`C:\Users\Alejandro\FerryInn`, and the tavern map is `/Game/Medieval_Tavern/Map/Demo_level`. All of
that is on the owner's PC only, and no run instructions for the client exist.

- Epic Games Launcher + Unreal Engine 5.x installed (~40–70 GB). Not present on this
  machine as of branch creation. Install requires the user's Epic account.
- A FAB environment choice (agent can shortlist free candidates in the browser; acquiring
  may need the user's Epic session, same as Mixamo).

## Definition of done for the first Unreal milestone

The ferry-inn night runs in Unreal: prebuilt tavern, 4 MetaHumans driven by the SAME mind
server sessions, talk/react/move/sit working, voice in, thought sidebar in, storm outside —
and the live verification loop demonstrably catching a planted error before the user does.

**Outcome**, from commits and source rather than a re-run. Met: the tavern, 4 MetaHumans
(`5be279a`), talk, react, move (`0049b5c`), voice in (`e80ed22`), and storm ambience (`0049b5c`).
Not met: sit and the thought sidebar, neither of which has code in `unreal/Source/FerryInn`. The
planted-error check couldn't be confirmed either way.
