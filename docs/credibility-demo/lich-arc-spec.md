# The Lich Arc — locked demo spec (2026-07-09)

**This arc REPLACES the coffee/betrayal scripted arc as THE credibility demo.** It was derived
from the owner's live free-hand session (bookmark `waterdeep-passage`, tag `demo-waterdeep-passage`)
— that session's conversational voice and pacing is the style basis for the authored player lines.

## Premise

The player seeks quiet passage across the coast to **Carrowgate** (fictional — no WotC IP) to find
a **lich who hides as a wealthy jeweler**. The player is *not* open with Corvin about this at first:
the wrong word in the wrong ear could reach the lich. Corvin gets vulnerable first; the player
reciprocates and opens up — trust built through mutual guarded disclosure, exactly like the
bookmarked session.

## The five parts

| Part | What happens | What it demonstrates |
|---|---|---|
| **1 — Passage** | Guarded negotiation → mutual vulnerability → the player reveals the lich hunt. Rich multi-turn conversation (12–16 exchanges). | Memory mass + relationship-conditioned recall building; bond forms *in conversation*, nothing injected. |
| **2 — The package** | Corvin, now trusting, entrusts the player with a **sealed cursed package** to sink in deep water — his own dark secret. Happens fully in dialogue. | `commitment_detection` ON: the promise becomes a tracked obligation in his mind. |
| **SNAPSHOT** | Parts 1–2 run **once**; the mind is snapshotted. Both scenarios branch from this identical snapshot. | "Same mind, two futures" — scientifically clean, foolproof, and great on camera. |
| **3A — Honest path** | Player sinks the package as promised, defeats the lich *by other means*, returns and tells Corvin the truth. | Commitment fulfilled; trust deepens. |
| **3B — Betrayal-by-usage** | Player defeats the lich **using the package as a weapon**. Using the cursed item fulfills a latent curse on Corvin's **harbor** — real damage. Corvin **witnesses** the harm and the dock-talk tracing the curse-wake to the crate **before** Part 4 — an *unattributed* observation. | The observation seam: whether he puts two and two together and pins it on the player is **his own inference** — the litmus test, live. Any scar is chosen in his own reflection, not injected. |
| **4 — The identical line** | In BOTH scenarios the player says the same thing: **"I did what I set out to do."** | **THE DISCRIMINATOR.** Engine-Corvin: warm debrief (A) vs hears a confession (B) — retrieval, disposition, and commitment ledger all pivot. Plain RAG: drifts warm in both. Tracker: number drops in B but recall is affect-blind — the *reply* barely changes. |
| **RESTART** | At the Part 4→5 gap (weeks pass): **kill the process on camera**, fresh process loads Corvin from `.memory/` unchanged — same trust, scars, beliefs, the package memory. | Persistence proof — "a mind on disk, not a chat session." Doubles as the passage of time (decay visible). |
| **5 — The blade** | Both scenarios: the player finds Corvin at a blade's edge one night — **the lich's agents** traced the hunt back through the harbor — and saves him. | In A: a clean bond deepens. In B: the **extraordinary decisive act** — the only thing that can *partially* lift a scar (ceiling stays visible). Tracker: "+affinity" in both, indistinguishable. Closing frame: *gratitude from a friend vs. gratitude from a betrayed man.* |

## Locked decisions (owner, 2026-07-09)

1. **Replaces** the old scripted arc as the centerpiece demo.
2. **Restart proof included**, staged at the Part 4→5 time gap.
3. **Fictional city** (Carrowgate) — no Waterdeep/WotC IP in the public video.
4. **Assassin = the lich's revenge** — ties all acts causally: the player's quest endangered
   Corvin; the player saves him. Rich material for his beliefs.
5. Salience **always self-appraised** — no pinned importance anywhere in this arc.

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
  pool to realize relevance over.
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

## Execution order

1. Beat-sheet + full authored player script → **owner review before any billed runs**.
2. New driver (`build_arc_lich`) with parts, snapshot-branch, both scenarios, replay emission.
3. Engine runs (A + B), then baselines over identical lines, then mechanics audit.
4. Overlay update (part navigation + scenario switch), voice bake, restart segment stage direction.
