# SRD 5.1 attribution

This game's rules system is an **original implementation** of tabletop RPG mechanics (ability
scores, d20 resolution, turn-based action economy). Game *systems and mechanics are not
copyrightable* — only their expression (text) is — so the code here is our own.

This game **uses SRD-derived content**, drawn from and adapted from the **System Reference
Document 5.1 ("SRD 5.1")** under the Creative Commons Attribution 4.0 International License.
Specifically:

- `game/rpg/srd/data/bestiary.json` — creature stat **numbers** (AC, HP/hit dice, ability scores,
  speeds, CRs, damage) for SRD-included creatures are adapted from the SRD 5.1; all creature
  *prose* (blurbs) is original, and two creatures (cinder-husk, vault-drowned) are wholly original.
- `game/rpg/srd/progression.py` — the character-advancement XP thresholds and the XP-per-CR
  values are SRD 5.1 material.
- `game/rpg/srd/encounters.py` — the CR cost anchors reuse the SRD 5.1 XP-per-CR values; the
  difficulty budgets and pack multipliers are our own (the published encounter-threshold tables
  are NOT in the SRD and are NOT reproduced — the constants were deliberately tuned away from
  every published row).
- `game/rpg/srd/data/loot.json` — the loot tables are **original** (structure, item names,
  trinket prose); a few generic equipment names and the healing-draught dice tiers are adapted
  from SRD 5.1 items.

Attribution, as required:

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
- **Loot tables are original** — the published random-treasure tables are not in the SRD; the
  difficulty-banded tables in `game/rpg/srd/data/loot.json` are our own design and prose.
- **No published difficulty tables** — encounter budgets/multipliers are our own constants
  (verified distinct from every published threshold row).

*This is not legal advice. Have an IP attorney review before any commercial release.*
