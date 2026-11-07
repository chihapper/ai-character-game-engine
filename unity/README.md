# Unity gray-box client (#35)

> **Status (2026-11-07):** Frozen history, not active work. This gray-box client was last changed on
> 2026-07-02 (`e53b27c`; the repo's Unity work is frozen at `7c15d40`, tag `archive/sandbox`) and has not been run since 2026-07-05. A static read
> on 2026-11-07 shows its API calls still match the mind server, but it hasn't been tested against
> today's server. The project moved on to the fuller `unity/pro/` client, then to Unreal
> ([docs/unreal-port.md](../docs/unreal-port.md)), then to the Godot client on `game-rpg`. For the
> current picture, read [docs/project-status.md](../docs/project-status.md).
>
> Two Unity clients live here. This page covers the gray-box one in `unity/Assets/Scripts`. The
> fuller one in `unity/pro/` (22 scripts, 8 editor tools) has no setup doc. It ran in a local URP
> project, `FerryCrossingPro`, with `Assets/Scripts` and `Assets/Editor` linked to `unity/pro/`,
> using the asset packs in [ProAssets/MANIFEST.md](ProAssets/MANIFEST.md). Neither client can be
> rebuilt from this repo alone, because the repo holds scripts, not a Unity project. The gray-box
> scripts need a new Unity project (the steps below), and `unity/pro/` also needs those packs.

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

**Warning: pressing Play has side effects.** Creating a session deletes the `.memory/` files of all
four cast characters, including `corvin-ashgrave-inworld`, the credibility demo's default mind. It
also adds a row to the tracked file `docs/embodiment-experiment.md`, and every reply bills your
Anthropic key.

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
