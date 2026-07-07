# Asset library (bulk CC0 store — NOT committed)

Everything in this directory except this README is **gitignored for SIZE, not license** — it is
all CC0, but bulk packs run to hundreds of MB. The workflow: browse here, pick what the game
needs, promote the specific files into `godot/assets/` (which IS committed) alongside a README
crediting the source, then wire them in `world3d.gd`.

Re-fetch any itch pack with:

    .venv/Scripts/python.exe tools/fetch_itch_asset.py <itch_url> <subdir>

## Contents & sources (all CC0, fetched 2026-07-08)

| Subdir | Source | What's inside |
|---|---|---|
| `kaykit-character-animations/` | kaylousberg.itch.io/kaykit-character-animations | **161 humanoid animations** for KayKit Rig_Medium/Rig_Large — the EXACT rigs of our Adventurers/Skeletons casts (movement, melee 1h/2h/dual, ranged, spellcasting, lockpicking, emotes, skeleton-specific). glTF + FBX + mannequin. |
| `quaternius-universal-animation-library-2/` + `quaternius-ual1/` | quaternius.itch.io | 250+ clips on a universal humanoid rig, Godot-retarget-ready (SkeletonProfileHumanoid), root-motion + in-place variants. |
| `quaternius-lowpoly-animated-monsters/` | quaternius.itch.io/lowpoly-animated-monsters | 4 animated monsters (Bee/Crab/Skull/Slime — the small pack). **Ultimate Monsters (~50 animated creatures: orc, yeti, demons, dragon, goleling, blobs, ghosts…) is NOT on itch** — per-model GLBs via poly.pizza (Cloudflare-gated: fetch through the Chrome extension, see how Goblin.glb was pulled) or the Drive folder at quaternius.com/packs/ultimatemonsters.html. |
| `quaternius-animated-easy-enemies/` | quaternius.itch.io/animated-easy-enemies | Frog, Rat, Snake, Spider, Wasp (animated). |
| `quaternius-lowpoly-animated-animals/` | quaternius.itch.io/lowpoly-animated-animals | 12 animals × 12+ clips incl. Attack/Death (wolf, fox, deer, stag, horses…). |
| `quaternius-universal-base-characters/` | quaternius.itch.io/universal-base-characters | Rigged base humanoids for the outfit system. |
| `quaternius-modular-character-outfits-fantasy/` | quaternius.itch.io | Fantasy outfit modules for the base characters. |
| `quaternius-lowpoly-modular-dungeon-pack/` | quaternius.itch.io | A second modular dungeon tileset (variety vs KayKit's). |
| `quaternius-stylized-nature-megakit/`, `quaternius-150-lowpoly-nature-models/` | quaternius.itch.io | Outdoor/overworld vegetation + terrain dressing. |
| `quaternius-lowpoly-medieval-weapons/` | quaternius.itch.io | Weapon props (loot visuals). |
| `quaternius-lowpoly-animated-knight/` | quaternius.itch.io | Animated knight (alt player/NPC body). |
| `quaternius-animated-lowpoly-dinosaurs/` | quaternius.itch.io | 6 dinos — lizardfolk/drake stand-ins. |
| `quaternius-fantasy-props-megakit/`, `quaternius-medieval-village-megakit/` | quaternius.itch.io | Fantasy props + village megakits (if the fetch found free tiers). |
| `fsp-temple-modular-collection/` (213 models), `fsp-modular-village-pack/`, `fsp-modular-terrain-pack/`, `fsp-nature-props/`, `fsp-modular-house-collection/` | fertile-soil-productions.itch.io | Modular environment shells (.obj, flat-color) — temples, villages, terrain, nature props. |
| `rgsdev-modular-dungeon/` | rgsdev.itch.io/free-modular-low-poly-dungeon-pack-by-rgsdev | Modular dungeon: walls/doors/floors/stairs/traps/chests, material-split for recoloring. |

## Owner purchases that slot in here when made (CC0 after purchase → committable)

- **Kenney All-in-1 bundle** ($19.95, kenney.itch.io/kenney-game-assets): Mini Dungeon +
  Mini Characters (25 rigged chibi × 32 anims, designed with Kay Lousberg), Graveyard/Fantasy
  Town/Castle/Nature kits, 1,200+ CC0 audio.
- **KayKit Mystery Series 4 + 6** (~$33, kaylousberg.itch.io): Orc Raider, Werewolf, Orc Brute,
  The Monstrosity, Plant Warrior… — boss-tier roster in our exact style.

Skipped deliberately: Synty (EULA forbids redistribution — can't commit), Zsky (attribution
required), OpenGameArt 3D (incoherent quality; fine for CC0 AUDIO loops).

## Format note

Quaternius's OLDER itch packs (easy enemies, animals, knight, dinosaurs, weapons, dungeon,
monsters) ship FBX/OBJ only — Godot 4 imports FBX natively (ufbx), or grab the specific model
as a GLB from poly.pizza. The newer megakits + UAL + base characters ship glTF directly.
Fertile Soil packs are .obj (untextured flat-color — assign a palette material in Godot).

Fetched totals (2026-07-08): 22 packs, ~2.3 GB, 4,500+ files — including 161 + 250+ humanoid
animation clips, 94 fantasy props, 176 village pieces, 68 nature megakit models, modular
outfit system with rigged base characters.
