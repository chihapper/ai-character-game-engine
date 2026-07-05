# Unreal Demo Port — what carries over, what rebuilds, what changes strategy

> **Status (2026-07-05):** the Unreal client works — NPCs speak (Hume) and the engine drives
> them end-to-end. The **face/lip-sync layer is paused**, and the **front-end direction is under
> review**: a 2D game on **Godot** is being considered. None of that touches the engine or the
> mind server — the whole point below is that the front-end is swappable. Treat this doc as the
> Unreal-specific port record, not a committed roadmap.

Decision (2026-07-02): the demo client moves to Unreal Engine. The prior Unity client
(`unity/pro/`) stays on `sandbox` as a working reference implementation; this branch
(`unreal-demo`) hosts the port. The mind is untouched — that was always the design.

## Ports UNCHANGED (the actual product)

- **The engine** (`orchestrator/`, `engine/`…): the RR-driven character minds. Zero changes.
- **The mind server** (`game/bridge/mind_api.py`): FastAPI over HTTP on :8001. Unreal speaks
  HTTP natively (`FHttpModule` / VaRest). Same endpoints: `/session`, `/respond`, `/choose`,
  `/observe`, `/acted`, `/speak` (PCM + X-Sample-Rate), `/stt`, `/finish`.
- **Scenario + policy + casting** (`game/scenarios/ferry_crossing.yaml`, `game/policy.py`,
  `game/casting.py`): engine-side, engine-owned. The react recipe, salience thresholds,
  name/acquaintance rules — all as-is.
- **The contract** (`docs/engine-game-contract.md`): engine owns the MIND, game owns the
  WORLD. Unreal is just a different WORLD.
- **Voice**: TTS (now **Hume Octave**, chosen after a bake-off) / AssemblyAI STT already flow
  through the mind server, so the voice pipeline ports by doing nothing.
- **Face / lip-sync** *(explored, paused)*: audio→ARKit-blendshape lip-sync (NVIDIA Audio2Face,
  then self-hosted **NeuroSync**) was wired through the mind server's `/speak_anim` and drove a
  MetaHuman face here. It's **currently on pause** — see the note below and the
  [engine/game contract §7.5](engine-game-contract.md). If the front-end pivots to 2D (Godot
  under consideration), the face layer likely won't be resumed.

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

## Machine prerequisites (blocking, needs the user once)

- Epic Games Launcher + Unreal Engine 5.x installed (~40–70 GB). Not present on this
  machine as of branch creation. Install requires the user's Epic account.
- A FAB environment choice (agent can shortlist free candidates in the browser; acquiring
  may need the user's Epic session, same as Mixamo).

## Definition of done for the first Unreal milestone

The ferry-inn night runs in Unreal: prebuilt tavern, 4 MetaHumans driven by the SAME mind
server sessions, talk/react/move/sit working, voice in, thought sidebar in, storm outside —
and the live verification loop demonstrably catching a planted error before the user does.
