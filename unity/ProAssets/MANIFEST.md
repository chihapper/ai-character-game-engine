# ProAssets manifest — the sandbox demo's art kit (acquired 2026-07-02)

Art direction: **consistent stylized** (Quaternius family) with mood carried by lighting/post —
photoreal was deliberately rejected (uncanny characters undermine believable minds; consistency
reads as "finished product", mixed fidelity reads as asset soup).

## Local packs (`packs/`, CC0 — Quaternius, downloaded via itch.io; zips gitignored, re-fetchable)

| pack | contents | use |
| --- | --- | --- |
| Universal Base Characters[Standard].zip (123MB) | 6 rigged humanoid bases (m/f × 3 builds), 20 hairstyles, 26 FBX | the cast — Della, Corvin, Edwin, Bri + player |
| Universal Animation Library[Standard].zip (15MB) | 120+ humanoid animations, retarget-ready | locomotion, idles, gestures |
| Universal Animation Library 2[Standard].zip (18MB) | second animation set (incl. root motion) | more idles/actions |
| Medieval Village MegaKit[Standard].zip (154MB) | 176 modular building pieces (walls, roofs, doors, windows, interiors) | the ferry inn, built properly |
| Fantasy Props MegaKit[Standard].zip (143MB) | 94 props (furniture, tankards, candles, barrels, crates) | set dressing |

License: CC0 1.0 (verified on quaternius.com per pack). Import notes: use FBX; UAL retargets onto
the UBC humanoid rig via Unity's Humanoid avatar system.

## Unity Asset Store (added to the signed-in Unity account; import via Package Manager → My Assets)

| pack | use |
| --- | --- |
| AllSky Free — 10 Sky/Skybox Set (rpgwhitelock) | storm-night + dawn skyboxes for the windows/arc |
| Cartoon FX Remaster Free (Jean Moreno) | stylized particles — fire, smoke, rain-adjacent FX |

Standard Unity Asset Store EULA accepted at add-time (standard flow, per delegated acquisition).

## Build plan (next session, on this `sandbox` branch)

1. New Unity 6 URP project `FerryCrossingPro`; import packs; junction a new Scripts dir.
2. The inn from MegaKit modules (real walls/windows/beams) + props pass; URP lighting redone
   (hearth, lamps, lightning through real windows) + post (fog, vignette, grading).
3. Cast: UBC bases styled per character (hair/build/palette) + UAL animator (locomotion, idles,
   sit/lean, look-at) replacing capsule stances.
4. Systems port from unity/Assets/Scripts (percept composer, react recipe, warrant, storm arc,
   nameplates) — the mind server is unchanged.
5. Polish: audio mix (keep procedural storm), title beat, the 16-minute night tuned end-to-end.
