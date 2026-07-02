# Unity gray-box client (#35)

The ferry inn in real 3D space, driving the unchanged Python engine as a **mind server**.
Everything is runtime-generated — no scene authoring, no prefabs, no packages. See
[docs/unity-client-architecture.md](../docs/unity-client-architecture.md).

## One-time setup (~3 minutes)

1. **Unity Hub → New project** — any 3D template works (Built-In or the default Universal 3D/URP);
   name it `FerryCrossing`. If you used a URP template, set Edit → Project Settings → Player →
   Active Input Handling to **Both** (the scripts use the classic input API).
2. Copy this folder's `Assets/Scripts` into the new project's `Assets/`.
   Better (edits stay in the repo): make a junction instead —
   ```
   mklink /J "<project>\Assets\Scripts" "<repo>\unity\Assets\Scripts"
   ```
   (run in an ordinary `cmd` — no admin needed for junctions)

## Play

1. Start the mind server from the repo root: `python -m game.server_lan` (port 8001).
2. Press **Play** in Unity on the default empty scene — `Bootstrap` self-spawns, builds the
   gray-box inn, creates the session (`POST /api/mind/session`), and spawns the cast.
3. **WASD + mouse** to move/look · **E** facing someone to talk · **Esc** to close dialogue.

What to watch for (the point of the exercise):
- **Occlusion**: whoever can't raycast-see you doesn't perceive you — cross the room behind the
  bar and only the NPCs with a sightline appraise it (the react recipe runs on real witnesses).
- **Gaze**: "looking your way" in an NPC's percept is geometry now, not narration.
- **Introductions**: nameplates (the dialogue feed's names) flip only when a first name or
  nickname is actually spoken aloud (`name_spoken` from the bridge).
- Runs log as `TREAT-EMBODIED-3D` in docs/embodiment-experiment.md.
