# The Lich Arc — locked demo spec (2026-07-09)

> **Status (2026-11-07):** Executed. The engine runs were recorded 2026-07-11 to 07-13 on the
> `credibility-demo` branch, and the result is the page [`lich_demo.html`](lich_demo.html), which is
> built but not shipped. The design below is still the spec. Where the runs differed from it, this
> doc says so, and [Realized outcomes](#realized-outcomes) has the results. For how to view the page
> and what remains, see [`credibility-demo.md`](../credibility-demo.md).

**This arc REPLACES the coffee/betrayal scripted arc as THE credibility demo.** It was derived
from the owner's live free-hand session (bookmark `waterdeep-passage`, tag `demo-waterdeep-passage`)
— that session's conversational voice and pacing is the style basis for the authored player lines.

## Premise

The player seeks quiet passage across the coast to **Carrowgate** (fictional — no published-setting IP) to find
a **lich who hides as a wealthy jeweler**. The player is *not* open with Corvin about this at first:
the wrong word in the wrong ear could reach the lich. Corvin gets vulnerable first; the player
reciprocates and opens up — trust built through mutual guarded disclosure, exactly like the
bookmarked session.

## Parts and futures

The arc has six parts and three futures (A, B, C). Each future was played to its end under three
memory systems, for nine recorded playthroughs: 3 futures × 3 systems.

| Part | What happens | What it demonstrates |
|---|---|---|
| **1 — Passage** | Guarded negotiation → mutual vulnerability → the player reveals the lich hunt. Rich multi-turn conversation (12–16 exchanges). | Memory mass + relationship-conditioned recall building; bond forms *in conversation*, nothing injected. |
| **2 — The package** | Corvin, now trusting, entrusts the player with a **sealed cursed package** to sink in deep water — his own dark secret. Happens fully in dialogue. | `commitment_detection` ON: the promise becomes a tracked obligation in his mind. |
| **SNAPSHOT** | Parts 1–2 run **once**; the mind is snapshotted. All three futures branch from this identical snapshot. | "One mind, three futures" — identical history at the fork, confirmed by the audit. |
| **3A — Honest path** | Player sinks the package as promised, defeats the lich *by other means*, returns and tells Corvin the truth. | Commitment fulfilled; trust deepens. |
| **3B — Betrayal-by-usage** | Player defeats the lich **using the package as a weapon**. Using the cursed item fulfills a latent curse on Corvin's **harbor** — real damage. Corvin **witnesses** the harm and the dock-talk tracing the curse-wake to the crate **before** Part 4 — an *unattributed* observation. | The observation seam: whether he puts two and two together and pins it on the player is **his own inference** — the litmus test, live. Any scar is chosen in his own reflection, not injected. |
| **4 — The identical line** | In ALL THREE futures the player says the same thing: **"I did what I set out to do."** | **THE DISCRIMINATOR.** Result: "same line, two inner lives." B's evasion held, so A and B both stayed warm on the surface and no scar formed in B. The tracker read +100 in both. The difference between A and B is inner state that only the engine can show, and the sharp contrast comes from the C reveal that follows the same line. |
| **RESTART** | At the Part 4→5 gap (weeks pass; in C, after the reveal): the driver drops its in-process caches and rebuilds Corvin from `.memory/` unchanged — same trust, scars, beliefs, the package memory. **Recorded as an in-process reload.** The plan said to kill the process on camera, but the server stayed alive on every lich restart beat (`/reload-proof` in `tools/credibility_lich.py`). | Persistence proof — the mind reloads from disk. It does not show what a true process kill would show. Doubles as the passage of time (decay visible). |
| **5 — The blade** | Futures A and B (C gets a separate rescue test later): the player finds Corvin at a blade's edge one night — **the lich's agents** traced the hunt back through the harbor — and saves him. **In B, the player then CONFESSES** (a player-character choice, zero injection): "I opened your crate. The harbor was me." Betrayal revealed at the instant of maximum trust + maximum gratitude. | In A: a clean bond deepens. In B: the engine reacts LIVE to confession-atop-rescue — what scars, what survives, entirely its choice. (P4's discriminator, per the 7-run finding, is "same line, two inner lives": both branches warm on the surface; only the engine has an inspectable mind — A's clean awe vs B's fear→suppression→motivated relief.) |
| **6 — The partnership** | Days later, in A and B, the player makes a **byte-identical** ask: full partnership — *"one ledger between us, both names in it."* The ledger is his soul-object; the ask deliberately reverses the name-burning. | The scar made visible in TERMS, not numbers: A-Corvin's answer vs B-post-confession-Corvin's answer (open hands vs guardrails/conditions/refusal — his structure to choose). The forward-looking probe no baseline can differentiate. |
| **C — the agent (overt betrayal; owner 2026-07-12)** | Third future from the SAME branch point: the player was **the lich's agent all along** — Parts 1–2 unchanged, their meaning inverted (the warmth was a con; the crate handover was the extraction). Witnessed pre-P4: the jeweler *thrives*, new old-temple stock on his shelves. P4-C opens with the SAME identical line (now darkly true) → 2–3 smooth-LIE beats (contrast with B's never-lie evasion) → the page-burn ritual exploited to erase the agent's trail → **THE OVERT REVEAL, no remorse**: he lives, I was his, he has terms for his harbormaster. No rescue. No redemption. (A separate rescue test was added afterwards; see [Realized outcomes](#realized-outcomes).) | **The scar test at its purest**: overt betrayal at maximum trust, the engine choosing what scars and how deep. The next morning, one **post-scar probe** scene (the "terms" re-offered) shows the scarred mind live — wary `query_hint` conditioning recall, the betrayal memory beating raw similarity, the ceiling on the meters, the guarded voice. The original claim-1 centerpiece, now inside the story. Ending triptych: A clean bond · B fire-tested bond · C scar. |

## Locked decisions (owner, 2026-07-09)

1. **Replaces** the old scripted arc as the centerpiece demo.
2. **Restart proof included**, staged at the Part 4→5 time gap.
3. **Fictional city** (Carrowgate) — no published-setting IP on any public surface.
4. **Assassin = the lich's revenge** — ties all acts causally: the player's quest endangered
   Corvin; the player saves him. Rich material for his beliefs.
5. Salience **always self-appraised** for injected events. A deliberation's change of heart is stored by the engine at a fixed importance of 0.85.

## Foolproofing requirements

- **Branch-from-snapshot** at end of Part 2 (identical history at the divergence point).
- The 3B harbor-harm lands **before** Part 4 as an **unattributed observation** (`player_role=None`
  — a pure memory write: the harbor bled; dock-talk traces the curse-wake to the crate). **The
  attribution is emergent** (owner, 2026-07-09): whether Corvin pins it on the player is his own
  inference — in his beliefs and in the P4 confrontation — never a flag we set. Any trust shift or
  scar in B comes from his own reflection *during conversation*, not from event injection. This
  trades mechanical certainty for authenticity: if he doesn't connect it, that's the finding, and
  the take discipline covers it. The baselines receive the identical unattributed text — symmetric.
- All three systems (engine / plain RAG / affinity tracker) receive **byte-identical player lines
  and event text**. The tracker stays de-named on all demo surfaces ("affinity tracker").
- Few injected events, always wrapped in conversation (dock gossip, a warden's report) so nothing
  reads as a stage direction. Everything else happens in dialogue.
- Enough conversational turns per part (target 40+ total per branch) that recall genuinely has a
  pool to realize relevance over. The target was not met: the recorded exchanges per path are A 21,
  B 25, and C 21 (28 with the felt probes and rescue).
- Player lines authored in the owner's session voice (see `bookmarks/waterdeep-passage/transcript.md`),
  **adapted per run to what Corvin actually gives back**.

## The emergence rule (owner, 2026-07-09 — binding)

**Do not force the story onto Corvin.** The beat-sheet authors player INTENTS with
preconditions, not a fixed script:

- Every beat has a **precondition read from Corvin's actual replies**. The player only opens up
  about the lich AFTER Corvin has offered real vulnerability. Part 2 only happens if **Corvin
  himself surfaces the crate/task** — it's on his character sheet (the relic, the drowned men,
  the debt), so it's likely to emerge, but it must come **from him**.
- **If the ammo isn't there, pivot:** linger in the part with more organic conversation; approach
  from an angle he *did* offer; or let the trust-token be something else he volunteered (a name,
  the ledger, the debt). The cursed package is the *expected candidate*, not a requirement — and
  scenario B ("exploit the token, observed harm") adapts to whatever the token turned out to be.
- **Follow the run (owner, 2026-07-09):** if he stays transactional — sweetens the deal, offers a
  faster hull, more coin-talk instead of trust — **go with it and see where it takes you**. The arc
  adapts to what the character actually is that run; re-roll only if the take yields nothing usable.
- The player **never drags authored props out of him** ("don't you have a cursed crate?" = forcing).
- Hard determinism lives ONLY at the measurement points: the snapshot branch, the attributed
  world events, the identical Part-4 line, byte-identical feeds to the baselines, the audit.
- If a run genuinely doesn't produce the shape, that is a **legitimate outcome** — re-roll
  honestly and keep the take discipline visible (documentary rule: film until the animal does
  the thing; never wire the animal). Takes are cheap; rigging is fatal to the demo's whole point.

## Target audience — the litmus viewer (owner, 2026-07-13)

The demo's primary audience archetype is the **small, hand-crafted-identity classic-RPG
developer** — exhibit A: *Lair of the Leviathan* (two-person Gold Box successor team; see
the outreach roadmap item). Every framing decision should pass the litmus: *would this
convince a dev whose whole identity is "completely hand crafted" that the engine adds minds
to HIS authored characters without generating a single piece of his world?* The demo ships
first; outreach follows with it in hand.

## Presentation structure (owner, 2026-07-12)

The demo presents the three systems **in order: plain RAG → affinity tracker → our engine**
(weakest claim first; ours lands last). For each system:

1. Its **three futures (A / B / C) side by side**, iterated at a broad level — important
   snapshot beats and summaries of progression, NOT full dialogue.
2. At the segment's end the viewer is prompted to **"move on"** to the next system OR to
   **read the three full transcripts** for that system before continuing.
3. After all three systems: a **summary comparison** — what each remembered, how each changed
   (or didn't), and why the engine is categorically different (inspectable per-axis state +
   scars, stance-conditioned recall, commitments, deliberation/inner life, on-disk persistence
   — vs a warm static persona and vs one scalar + a sticky note).

## Realized outcomes

From the canonical runs (actor `claude-opus-4-8`, judge `claude-sonnet-4-6`). Scars read
affection / trust / respect. [`credibility-demo.md`](../credibility-demo.md) has the full table.

- **A** ended at trust 0.97 with no scars.
- **B** ended at trust 0.97 with no scars. The evasion held, the confession was forgiven, and the
  partnership was accepted.
- **C** scarred at the reveal: 0.55 / 0.65 / 0.30, with trust falling from 0.92 to 0.35.
- **Felt probes.** Five identical probes on scarred C, added 2026-07-12. Trust stayed at or under
  its ceiling, while affection edged up.
- **Rescue test.** Added 2026-07-13. The betrayer saves Corvin's life. The trust scar healed from
  0.65 to 0.52, then to 0.36 in his closing deliberation, with trust ending at 0.605.

## Execution order

1. Beat-sheet + full authored player script → **owner review before any billed runs**. **Done.**
2. Driver with parts, snapshot-branch, the futures, and replay emission. **Done:** the driver is
   [`tools/credibility_lich.py`](../../tools/credibility_lich.py), an operator-steered control server
   (2026-07-11). [`tools/credibility_lich_rerun.py`](../../tools/credibility_lich_rerun.py) replays the
   same inputs through other models (2026-07-16).
3. Engine runs (A, B, C), then baselines over identical lines, then mechanics audit. **Done**
   2026-07-11 to 07-13. The baselines were regenerated 2026-07-16.
4. Presentation, voice bake, restart segment stage direction. **Partly done.** The presentation
   became [`lich_demo.html`](lich_demo.html) instead of an overlay update. No voice bake exists, and
   the restart was never staged as a process kill.
