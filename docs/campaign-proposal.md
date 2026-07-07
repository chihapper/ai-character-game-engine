# Campaign proposal: **The Hollow Accord** (draft for owner reaction)

The first real campaign on the engine. Design goal, verbatim from the project thesis: NPCs that
**genuinely change because of you** — continuity is table stakes, transformation is the product.
So this is built social-first: combat exists (SRD core is done), but every fight is optional,
avoidable, or triggerable through RELATIONSHIPS, and the campaign's outcome is decided by who
the NPCs have BECOME by the end, not by a boss's HP bar.

## Premise (3–5 sessions of play)

A remote mining town, **Graywater**, sits above the sealed vault the demo slice already
established. The seal is failing. Three factions want the vault opened, kept shut, or quietly
plundered — and none of them can do it without the player, the only outsider all three will
still talk to. The player arrives with no reputation and leaves having REMADE five people.

Why this premise fits the engine:
- **Small cast, deep arcs** (5 named NPCs + Joren-style wildcard) — the engine's memory/RR
  stack shines with repeated contact, not crowds.
- **Factions = pressure on relationships**, not quest gates. Siding "with" someone is never a
  menu pick; it's the accumulated residue of conversations the engine already tracks.
- **The dungeon is the pacing valve**: between town acts, vault expeditions (procgen slices we
  already have) deliver combat/loot/rest beats — and each expedition CHANGES town state
  (what you brought back, who you lost, what you told people about what you saw).

## The cast (each built on a validated engine behavior)

| NPC | Role | The arc the engine must produce (unscripted) |
|---|---|---|
| **Maren** | mine boss, wants it OPEN | Core goal vs growing trust in the player — the settled goal-evolution design (#29): her goal can bend, or she can betray warmly. Either is a win if LEGIBLE. |
| **Father Ilo** | keeper, wants it SEALED | Faith under evidence pressure: what the player SHOWS him from the vault feeds his reflections. |
| **Sable** | fence, wants it QUIET | Trust lost fast / regained slowly (the asymmetric affect curves) — she tests the player early with a small betrayal opportunity. |
| **Lira** | scout (existing cast) | Continuity across slices: she remembers every prior expedition — the returning-companion anchor. |
| **Joren-type wildcard** | ordinary baker | UNCOACHED control character (validation methodology): if the campaign only works for authored arcs, we've studied for the test. |

## Structure (acts are GAME data; the engine never sees them)

1. **Arrival** — open town roam; first impressions seed every mind. One forced vault trip
   (tutorializes combat/rest at the new dungeon scale).
2. **Pressure** — factions ask for incompatible things; expeditions surface evidence each
   faction wants spun. Autonomous agency layer runs between sessions: NPCs act on their own
   (settled: gated + free mode, liveliness-can't-be-vetoed).
3. **The Accord** — a town meeting the DM stages where the player's accumulated relationships
   ARE the outcome: who defends them, who has quietly changed sides, who walks out. No scripted
   endings — the meeting is a RECIPE (situation + everyone deliberates), and we let it land
   where the minds have moved.

## What needs building (engine: NOTHING — all game/content layer)

- **Town slice**: a non-dungeon map (Kenney/KayKit village pieces are in the asset library);
  NPC placements with schedules-lite (morning/evening spots via game-driven cadence).
- **Campaign state**: act tracker + expedition-consequence hooks (what returned from the vault
  becomes `world_frame` facts baked via casting.situate — the proven grounding path).
- **Faction pressure content**: authored asks/evidence per act (slice WorldFlavor data).
- **The Accord scene**: a game-layer staged deliberation using the existing reaction recipe.
- Dungeon variety (#33) lands naturally as the expedition layer improves.

## Success criteria (from the thesis, measurable)

- The litmus: at least one NPC **changes its mind about the player on its own, unscripted** —
  and a blind reader of the transcript can say WHY.
- The wildcard baker develops a real arc without authored pressure.
- Two playthroughs with opposite social styles produce visibly different Accords.

## Open questions for the owner

1. **Tone**: grounded-grim (current vault mood) vs warmer frontier-town? Affects all casting.
2. **Session length target**: 30–60 min acts OK?
3. **Player character**: keep the blank knight, or give them a stated reason to be in Graywater
   (a letter, a debt)? Recommendation: a light hook — total blankness wastes the DM.
4. Names/factions above are placeholders — react freely.
