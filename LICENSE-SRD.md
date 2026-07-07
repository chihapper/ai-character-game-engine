# SRD 5.1 attribution

This game's rules system is an **original implementation** of tabletop RPG mechanics (ability
scores, d20 resolution, turn-based action economy). Game *systems and mechanics are not
copyrightable* — only their expression (text) is — so the code here is our own.

If/when specific **game content** (monster stat blocks, item descriptions, spell text) is added as
data under `game/rpg/srd/data/` (no SRD-derived data files exist or are loaded yet), it will be
drawn from and adapted from the **System Reference Document 5.1 ("SRD 5.1")** and used under the
Creative Commons Attribution 4.0 International License:

> This work includes material from the System Reference Document 5.1 ("SRD 5.1") by Wizards of the
> Coast LLC, available at https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1
> is licensed under the Creative Commons Attribution 4.0 International License, available at
> https://creativecommons.org/licenses/by/4.0/legalcode. Material from the SRD 5.1 has been modified
> and adapted.

## Hard constraints baked into this codebase

- **No Product Identity / trademarks.** The strings "Dungeons & Dragons", "D&D", and "Dungeon
  Master" appear nowhere in the game, its data, or its marketing ("Dungeon Master" is a Wizards of
  the Coast trademark not covered by the SRD's CC-BY-4.0 grant — the SRD itself says "Game
  Master"/"GM"). This ruleset is referred to generically (e.g. "the d20 system", "SRD-based") and
  the narrator as the "Game Master"/"GM".
- **No SRD-excluded creatures** (Beholder, Mind Flayer/Illithid, Displacer Beast, Yuan-ti, etc.) or
  **excluded species/classes** (Aasimar, Artificer). Use SRD-included creatures or original ones.
- **No published settings/lore** (Forgotten Realms, named published NPCs, adventure text).
- **Loot tables, if added, will be original** — the published random-treasure tables are not in the
  SRD; any difficulty-keyed tables we build will be our own, populated with SRD-licensed items.
  (None exist yet — today's loot is narrator-described plus authored quest keys.)

*This is not legal advice. Have an IP attorney review before any commercial release.*
