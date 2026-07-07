# Dialogue-card portraits (non-CC0 tier — NOT committed)

This directory holds the realistic painted portraits the speech card prefers over the pixel
sprites. **Everything here except this README is gitignored**, because these packs are
royalty-free for use but **forbid redistribution** — they must never ride along if this repo
goes public. (The two-tier policy: CC0 assets are committed; everything else lives here with a
documented re-fetch path.)

## Naming convention (what speech.gd looks for)

- `<slug>.png` — the base portrait for an engine character (e.g. `rpg-lira.png`).
- `<slug>_<emotion>.png` — expression variants for the emotion-sync stage
  (`neutral | smile | sad | angry | surprised | thoughtful`).

PNG, square-ish, ~512px+. Loaded at runtime (`Image.load_from_file`) — no Godot import pass
needed; linear-filtered automatically. Missing file = the card falls back to the pixel-sprite
portrait, so this whole directory is optional.

## Current contents & licenses

| Source | Files | License | Notes |
|---|---|---|---|
| AssetSmithy — "3 Free Fantasy Characters (6 expressions)" sampler | `sampler/`, cast copies `rpg-lira*`, `rpg-vael*` | Royalty-free, commercial OK, no redistribution | PROTOTYPE art. Disclosed by the author as AI-assisted + Photoshop-finished — fine for trials, replace before any public/commercial release. Re-fetch: https://assetsmithy.itch.io/3-free-fantasy-characters-with-6-expressions-each-visual-novel-rpg-sprites-sa |

## Planned headline art (owner purchase)

CrimsonDelightGames — "300+ Medieval & Fantasy Portraits" (hand-painted, explicit **no-AI**
declaration; ~$2.49–$15): https://crimsondelightgames.itch.io/crimsondelightgames-medieval-and-fantasy-portrait-packs
Commercial OK, no redistribution → buy, drop the chosen faces here under the naming convention
above, archive the license text alongside (itch pages vanish).
