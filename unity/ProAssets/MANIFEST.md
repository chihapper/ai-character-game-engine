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

| KayKit_Adventurers_2.0_FREE.zip | 6 CLOTHED rigged characters (Barbarian/Knight/Mage/Ranger/Rogue/Rogue_Hooded) + animations | the cast's CLOTHES — the UBC Standard bodies are underwear bases; Quaternius clothed packs are Patreon-gated (CC-BY-4.0? see License.txt) |

## Unity Asset Store (added to the signed-in Unity account; import via Package Manager → My Assets)

| pack | use |
| --- | --- |
| AllSky Free — 10 Sky/Skybox Set (rpgwhitelock) | storm-night + dawn skyboxes for the windows/arc |
| Cartoon FX Remaster Free (Jean Moreno) | stylized particles — fire, smoke, rain-adjacent FX |

Standard Unity Asset Store EULA accepted at add-time (standard flow, per delegated acquisition).

## Build status (sandbox branch, unity/pro/ junctioned into the FerryCrossingPro project)

ALL FIVE PHASES LANDED (2026-07-02, headless-compiled; awaiting first human playtest):
1. DONE - project (URP cloned config), packs imported, humanoid pipeline, animator baked from
   exact UAL clips (Idle/Walk/Sit/Talk/Lean/FoldArms).
2. DONE - the inn from MegaKit modules + props; runtime NavMesh; URP mood (fog/bloom/vignette,
   flickering hearth+candles with visible procedural flame); TRANSPARENT windows onto a built
   exterior: rain sheets tracking the storm arc, the flooded crossing + drowned jetty, marsh
   silhouettes; lightning through the glass.
3. DONE - cast on UBC bodies (per-character skin/hair/build/palette), UAL locomotion, seats
   they actually sit on, head look-at, speech bubbles in space.
4. DONE - full systems port (percepts, react recipe, warrant-as-parchment, storm-in-percepts,
   nameplates) + NPC-to-NPC cross-talk (#31 lite: engine-chosen, /observe-heard, loop-safe).
5. DONE - the arc: title card in; dawn breaks (light warms, door opens, crown men on the
   threshold, the room appraises it); epilogue card from what ACTUALLY happened; [R] replays.
