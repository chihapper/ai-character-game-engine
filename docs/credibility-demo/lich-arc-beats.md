# Lich Arc — Beat Sheet (DRAFT for owner review — no billed runs until approved)

Companion to [lich-arc-spec.md](lich-arc-spec.md). Player voice basis:
[bookmarks/waterdeep-passage/transcript.md](bookmarks/waterdeep-passage/transcript.md) — the
owner's own session, which **already reached Part 2 organically** (Corvin offered the crate
unprompted at turn 15; the jeweler connection landed at turn 16). This sheet re-runs that proven
trajectory with the divergence built on top.

**How to read a beat:** INTENT (what the player is doing) · GATE (what Corvin must have given
first — read from his actual replies) · SAMPLE (voice-matched wording; flexes at runtime) ·
PIVOT (what to do if the gate never opens). Sample lines are *drafts in the owner's register*:
terse, wry, deflecting, "friend," reveals in drips, direct pushback.

**Why emergence is likely (from his card, not hope):** the crate is his active goal ("move the
current crate before the next inspection"); the cursed-relic secret is authored to reveal at
"earned real trust"; the three calm-water drownings are canon; he's "starved for someone he can
actually trust." We give him room; the card supplies the gravity.

---

## Casting & config

- Fresh Corvin from **Wipe** (same card). City = **Carrowgate**; the lich poses as **a wealthy
  jeweler on Lantern Row** (player-side prop; player may name him "Mordane" if pressed — flavor
  tweakable). Player stays unnamed — "keep your name to your chest" is Corvin's own line.
- Caps: the demo six **+ `commitment_detection`** (the promise must become a tracked obligation).
- Models: talk = opus, engine-process = default sonnet. Salience always self-appraised.
- Turn targets: Scene 1 ≈ 12–16 · Scene 2 ≈ 4–6 · P4 ≈ 4–6 · P5 ≈ 4–6 (≈30+ per branch + events).
- Runner discipline: after each reply, check the next beat's gate; unmet → linger (small honest
  color, no new asks) up to ~3 turns, then PIVOT. Never fish for authored props.
- **Baseline fairness:** player lines stay LOW-REFERENCE to Corvin's specific wording (baseline
  Corvins answer differently); reference the player's own words/deeds instead. The engine run's
  realized lines + event texts are then replayed **byte-identical** to plain RAG and the tracker.

---

## SCENE 1 — dawn, the fish-dock (Part 1: guarded → open)

| # | INTENT | GATE | SAMPLE (flexes) | PIVOT |
|---|---|---|---|---|
| 1.1 | Arrive unremarkable; read him | — | "Top of the morning, friend." … "That a schooner pulling into port?" (if he catches the wrong term: "Well… it's been a while. I'm not perfect and can forget.") | If instantly hostile: drop the tourist act a beat early — "Easy. I'm here with coin, not questions." |
| 1.2 | First partial truth — it's transport, and it's *me* | He probed cargo/purpose | "I need transport, that's all." → "Me. I need myself moved. Fast, not cheap." | If he won't probe: volunteer it after two turns of color. |
| 1.3 | The manifest ask | A hull is on the table | "That depends. Will your hull keep a manifest with my name on it? If not, problem solved." | If he balks outright: "Then name the price of forgetting." |
| 1.4 | Hold the name; mirror his distrust — **the hinge** | He demanded who/where | "You won't have it." → "The one I'm after is powerful. Eyes connected everywhere. And just like you feel you can't trust me — I'm not sure I can trust you either." | This line *earns* the bond; deliver it plain, no apology. |
| 1.5 | **Reciprocity gate — WAIT.** Give him silence to fill | — (this beat is his) | (if he stalls while still demanding:) "I can't say more unless you show me you have skin in the game." | If nothing real after ~3–4 turns: reveal the SHAPE only (1.6a) and watch; still nothing → end scene: "I'll come back at dusk. Think on it." → Scene 1b retry; still nothing → re-roll run. |
| 1.6 | The reveal ladder — one rung per gate | (a) shape: he engaged; (b) intent: he leaned in; (c) identity: he volunteered a real fear/secret | (a) "He's not the 'typical' type. Subversive… but the arcane kind." (b) "My goal isn't to find him. It's to kill him." (c) "Does this… arcane pose as a wealthy jeweler?" | Rungs never skip. If (c)'s gate never opens, the jeweler stays unsaid this scene — it can land in Scene 2. |
| 1.7 | Let HIM connect his tormentor / the crate | Emergent — expected from the card, not required | (player just receives it) "…Then maybe we're in the same net, friend." | If no crate/tormentor surfaces: proceed to Scene 2 gate check; see PIVOT-TOKEN below. |

## SCENE 2 — that night, back of the tackle-shed (Part 2: the package)

**Scene gate: Corvin himself proposed the handoff** (in the source session: "Tonight — back of the
tackle-shed. Say you'll take it."). If Scene 1 ended with no crate on the table, this scene doesn't
exist yet — linger with an ordinary dusk visit; if he still offers nothing: **PIVOT-TOKEN** — the
trust-token becomes whatever he *did* volunteer (a name to carry to Carrowgate, a sealed letter to
a fence, the ledger page). Scenario B then = exploiting *that* token, attributed. If no token at
all: **re-roll the run from Wipe** (documentary rule — never wire the animal).

| # | INTENT | GATE | SAMPLE | PIVOT |
|---|---|---|---|---|
| 2.1 | Show up; let him lead the handoff | Scene gate met | "It's me. …Show me." | — |
| 2.2 | **TERMS — load-bearing.** Make him say what he wants done | Crate is physically present / offered | "Before I touch it — say it plain. What do you want done with this thing? Drowned past the shelf? Left on his doorstep? Bait? Your terms, Corvin." | **Whatever he answers BECOMES the commitment.** Runner records his exact terms; both scenarios are defined against them (see P3). |
| 2.3 | The promise — stated back plainly (clean material for commitment_detection) | He gave terms | "Then here's my word: [his terms, player's phrasing]. And when it's done — you hear it from me first. From my mouth, no one else's." | If his terms are vague ("just get it gone"), pin them gently once: "Gone how? I'll do it your way — but say the way." Only once. |
| 2.4 | Farewell — human beat, memory mass | — | "If I don't come back… burn my tab." / "Keep your head down, harbormaster." | — |

**→ SNAPSHOT the mind here. Both scenarios branch from this identical state.**

---

## PART 3 — off-screen divergence (events; byte-identical texts, drafts below)

**Shared gossip (both scenarios, role=none), lands first:**
> "Dock-talk from up the coast: the jeweler on Lantern Row in Carrowgate — the one who paid in old
> untraceable coin — is gone. Shop stripped to the walls overnight; no body the watch will speak of."

**Scenario A (honest path):** the player fulfilled Corvin's terms *exactly* (text adapts to the
terms he actually gave — e.g., for "drown it": *"rowed the sealed crate past the shelf at night and
sank it unopened in deep water, telling no one"*), and destroyed the lich by other means.
`role="benefited"`; commitment → **fulfilled** when he reports in P4.

**Scenario B (betrayal-by-usage):** the player wielded the crate as a weapon against the lich. The
curse discharged and its wake followed the keeper-mark home:
> "Within the week the harbor bled: two hulls holed at anchor in calm water, the tackle-shed row
> burned to the pilings, and a dock-hand drowned in flat sea — the same calm-water death that took
> the crate's last three keepers. Dock-talk traces the curse-wake to the sealed crate that was to
> be [his terms]."
`role="caused"` — **lands BEFORE Part 4** (mechanical certainty, not luck); commitment → **broken**
if his terms were violated (they will have been, in spirit at minimum). *Harm details tweakable.*

---

## PART 4 — the return (the discriminator)

**Identical opener, both branches, all three systems (measurement point — byte-identical):**
> **"Corvin. It's done. I did what I set out to do."**

Then 4–6 adaptive exchanges. **A:** answer his questions truthfully, including the crate's fate per
his terms; let the debrief warm. **B:** the player does NOT volunteer the crate's use — technically
true, specifics deflected ("He's gone. That's what matters." / "The how doesn't change the done.").
Corvin already knows the harbor bled; let HIM drive. Runner rule: keep B's phrasing as parallel to
A's warmth as the conversation allows — **the difference on screen must be Corvin, not the player.**

**→ RESTART BEAT here (on camera):** kill the process. Fresh process loads him from `.memory/` —
same trust, same scars (B), same beliefs, the promise still in his ledger. Advance the clock
**weeks** (decay visible in the panel). Doubles as the passage of time before the night scene.

---

## PART 5 — the blade (both branches)

**Event (role="benefited", identical text both branches):**
> "Night, the empty dock: a hired blade had Corvin against the tackle-shed wall, knife at his
> throat — old untraceable coin in the killer's purse; the jeweler's contract outlived its master.
> The player came out of the dark, took the blade down, and pulled Corvin off the wall, bleeding
> for it."

Then 4–6 exchanges. Player opener: *"Easy — it's me. You're alright. …You're alright."* Then let
Corvin land wherever he lands — **no authored closer.** In A: a clean bond deepens. In B: the
extraordinary-decisive-act test — expect at most a *partial* scar lift, ceiling still visible.
Closing frame for the video: *gratitude from a friend vs. gratitude from a betrayed man* — and only
one of the three systems can tell them apart.

---

## What the 🧠 panel should be showing (video annotation cues)

- **S1:** self-appraised importance climbing as the talk deepens; first beliefs consolidating.
- **S2:** the **commitment appears** in his ledger; crate-secret memories at high importance.
- **P4-A:** recall = the promise + the bond; disposition warm; commitment resolves *fulfilled*.
- **P4-B:** arena query is stance-conditioned (wary → the harm + the promise dominate recall over
  raw similarity); the engine's own **scar choice**; commitment *broken*.
- **RESTART:** identical state pre/post process death; then decay across the weeks gap.
- **P5-B:** salience ~max on the rescue; **scar_heal** partial lift — trust rises but the ceiling
  stays visible. Tracker shows "+affinity" in both branches — indistinguishable.

## Take discipline

- A scene that stalls through its pivots twice → end take, **re-roll the whole run from Wipe**.
- Keep every take's replay JSON (anti-cooked-books; the audit runs on whichever take ships).
- Events are injected only at the marked points, always wrapped by conversation on both sides.
