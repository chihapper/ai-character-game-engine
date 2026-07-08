# Dialogue-card portraits (non-CC0 tier — NOT committed)

This directory holds the realistic painted portraits the speech card prefers over the pixel
sprites. **Everything here except this README is gitignored** (`review/` included), because these
are either no-redistribution art or generated images we review before use. (The two-tier policy:
CC0 assets are committed; everything else lives here with a documented re-fetch/re-gen path.)

## AI portrait generation — `tools/gen_portrait.py` (roadmap Track 2)

The primary way we make portraits now: Claude authors a painted-style prompt from each
character's own sheet, a hosted image model renders it, and **you review every face before it's
used**.

```
.venv\Scripts\pip install fal-client                      # one-time
# get a key at https://fal.ai  ->  Dashboard -> Keys, then add to .env:
#   FAL_KEY=xxxxxxxx
.venv\Scripts\python tools\gen_portrait.py rpg-maren           # base -> review\rpg-maren.png
.venv\Scripts\python tools\gen_portrait.py rpg-maren --prompt-only   # just print the prompt (no FAL_KEY)
# review godot\assets\portraits\review\ , then MOVE keepers up to godot\assets\portraits\
.venv\Scripts\python tools\gen_portrait.py rpg-maren --mouth --emotions --base godot\assets\portraits\rpg-maren.png
```

- **Renderer = fal.ai Flux**, `enable_safety_checker` OFF (permissive — scarred villains, charred
  undead, hard faces aren't over-blocked; owner decision 2026-07-09). Provider is behind
  `_render()`; `PORTRAIT_PROVIDER` env can point at other seams later.
- **No-filter escape hatch** (if even Flux's hosted moderation blocks a legit character): run
  Flux locally in **ComfyUI** (GGUF quant, no filter) — or, since the 1080 Ti is slow (Pascal),
  rent a modern GPU on **RunPod/vast.ai** (~$0.40/hr), generate the batch uncensored in under an
  hour for ~$1, shut it down. Point `PORTRAIT_PROVIDER=comfy` at its endpoint (seam TODO).
- **Review gate is mandatory** regardless of provider: every face lands in `review/`; SFW-but-
  mature, clothed, portfolio-presentable bar (the discipline that caught the AssetSmithy vendor).
- **Variants** (`--mouth`, `--emotions`) render image-to-image FROM the approved base so the face
  stays consistent — the mouth-open frame drives the talk-screen lip flap.

## Naming convention (what speech.gd looks for)

- `<slug>.png` — the base portrait for an engine character (e.g. `rpg-lira.png`).
- `<slug>_mouth_open.png` — OPTIONAL mouth-open layer (same canvas/framing as the base): when
  present, the talk scene (talk_scene.gd) flaps it over the base in sync with the live voice
  amplitude — the Civ 5 "their mouth moves" effect. Without it the portrait breathes/glows on
  speech; characters without any painted art get a live 3D bust of their in-world model instead.
- `<slug>_<emotion>.png` — expression variants for the emotion-sync stage
  (`neutral | smile | sad | angry | surprised | thoughtful`).

PNG, square-ish, ~512px+. Loaded at runtime (`Image.load_from_file`) — no Godot import pass
needed; linear-filtered automatically. Missing file = the card falls back to the pixel-sprite
portrait, so this whole directory is optional.

## Current contents & licenses

| Source | Files | License | Notes |
|---|---|---|---|
| AssetSmithy sampler (two individually-reviewed images only) | `rpg-lira.png`, `rpg-vael.png` | Royalty-free, commercial OK, no redistribution | Interim placeholders ONLY. **The rest of that pack was removed — it contained content unsuitable for this project (owner-flagged 2026-07-08). Do not re-download this vendor's packs.** Replace these two the moment better art lands. |
| "Young knight portrait" by **David Revoy** (davidrevoy.com), via OpenGameArt | `player.png` | **CC-BY 3.0** — attribution required (keep this row!) | Hand-painted knight, individually reviewed 2026-07-08. Re-fetch: https://opengameart.org/content/young-knight-portrait (resized from the 2400x3263 original). Attribution line for credits screens: “Young knight portrait” by David Revoy, CC-BY 3.0, via OpenGameArt.org. |

## Content policy for this directory

Every image dropped here must be INDIVIDUALLY REVIEWED before use — never bulk-import a pack
sight-unseen. SFW, fantasy-appropriate, portfolio-presentable.

## Planned headline art (owner purchase) — ⚠ vendor caution added 2026-07-08

CrimsonDelightGames — "300+ Medieval & Fantasy Portraits" (hand-painted, explicit **no-AI**
declaration; ~$2.49–$15): https://crimsondelightgames.itch.io/crimsondelightgames-medieval-and-fantasy-portrait-packs
**CAUTION:** this vendor's catalog is otherwise ADULT games ("Tales of Legendary Lust…").
The portrait pack itself may be fine, but after the AssetSmithy incident treat it as
high-risk: if purchased, EVERY image gets individually reviewed before any lands here, and
suggestive ones are discarded. Consider safer-catalog alternatives first (OpenGameArt's
classic painted portrait sets, e.g. Justin Nichol's CC portraits, are SFW-curated).
Commercial OK, no redistribution → buy, review each face, drop the chosen ones here under the
naming convention above, archive the license text alongside (itch pages vanish).

## Owner north star (circle back): Civ 5-style diplomacy presentation

When you TALK to someone, their large/full portrait takes the scene and speaks to you — mouth
movement synced to the voice. Implementation path when we return: layered portrait (base +
2-3 mouth states) flapped by live audio amplitude from the voice stream (v1, cheap, reads
great), upgradeable to a NeuroSync-driven 2D rig later (the blendshape pipeline already exists
in the engine, currently paused).
