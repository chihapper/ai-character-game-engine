# Visual polish roadmap — Graywater / The Hollow Accord

Direction for the town-look + talk-screen threads the owner flagged 2026-07-09. Three tracks,
sequenced. Campaign *mechanics* (letter reaction → faction pressure → the Accord) run in
parallel and are tracked separately (task #34 body); this doc is the LOOK.

---

## Track 1 — Ambient life (townsfolk that read as purposeful)

**Now (done):** villagers no longer clump — farthest-point spawn spread, each anchored to a
home spot, longer/varied pauses. They amble their patch and return instead of migrating into
one corner.

**Next (polish, low effort):** give them *stations* — a market stall, the well, a bench, a
shop door — and have them path between a home station and the well/street so it reads as
"fetching water / minding a stall / crossing the square," not aimless drift. Optional: a couple
carry a prop (basket, tools). Client-only; no engine change.

**Effort:** S. **Depends on:** Track 3 stations (stalls/benches) landing first for them to use.

---

## Track 2 — AI character portraits (the big new capability)

**Goal:** when you talk to someone, the talk screen shows a painted portrait of *that* person
(Lira-style), generated from their character sheet. The talk screen ALREADY loads
`assets/portraits/<slug>.png` at runtime and flaps a `<slug>_mouth_open.png` on the voice — so
**integration is free**; the work is generating + reviewing the images.

### Pipeline (`tools/gen_portrait.py <slug>`)
1. **Prompt authoring (Claude — our own stack):** read the character's name/role/concept/age/
   backstory and write a tight, consistent visual prompt — painted fantasy-illustration style,
   head-and-shoulders bust, characterful but neutral expression, explicitly SFW + clothed +
   period-appropriate. One fixed style preamble so the whole cast matches.
2. **Render (image model):** call the image API with that prompt → PNG.
3. **Review gate (mandatory, per the AssetSmithy incident):** save to
   `assets/portraits/review/<slug>.png` (gitignored). Owner eyeballs each; approved images move
   to `assets/portraits/<slug>.png`. Nothing lands sight-unseen.
4. **Optional variants:** `--mouth` (a mouth-open frame, base image passed as reference so the
   face matches → the Civ-5 lip flap), `--emotions` (neutral/smile/sad/angry/… → the
   engine-chosen expression slot that already exists). Consistency via reference-image + fixed seed.

### Provider — the one decision that blocks this track
| Option | Ease | SFW safety | Painted quality | Consistency | Cost/img | Notes |
|---|---|---|---|---|---|---|
| **OpenAI gpt-image-1** | high | **built-in moderation** | strong | good (reference image) | ~$0.02–0.19 | Easiest + safest after the past incident; needs `OPENAI_API_KEY` |
| **Flux (BFL via fal.ai/Replicate)** | med | filter varies | **best painterly** | seed + reference | ~$0.03–0.05 | Highest art quality; a bit more setup |
| **Stability SD3.5** | med | weaker | good, tunable | seed/LoRA | cheap / self-host | Most control, least guardrail — riskiest on SFW |

**DECIDED (owner, 2026-07-09): fal.ai Flux, permissive.** Flux's painterly quality is the better
match for the Lira look, and fal exposes `enable_safety_checker` (turned OFF) so scarred villains
/ charred undead / hard faces aren't over-blocked — the strict gpt-image-1 filter was the concern.
Safety is carried by three layers regardless of the model: Claude authors an SFW-but-mature prompt,
the owner reviews every face, and (as a floor) the provider's own moderation. Provider lives behind
`_render()` in `tools/gen_portrait.py` (`PORTRAIT_PROVIDER` swaps it).

**No-filter escape hatch** if hosted Flux still blocks a legit character: local **ComfyUI + Flux
GGUF** (no filter; slow on the Pascal 1080 Ti), or rent a modern GPU on **RunPod/vast.ai** (~$0.40/hr)
for a fast uncensored batch (~$1 total, one-time) — `PORTRAIT_PROVIDER=comfy` seam TODO.

**STATUS:** tool built + prompt-authoring proven live (Claude writes a rich on-style prompt from
each sheet). **BLOCKED only on a `FAL_KEY`** (fal.ai signup) + `pip install fal-client`; then the
first cast renders into `review/` for approval.

**Effort:** M. **Depends on:** FAL_KEY.

---

## Track 3 — Quaternius village kit (bespoke buildings)

**Now:** buildings are procedural cottages (box body + prism roof + door). They read as a town
but not the market stalls / storefronts / chapel the DM keeps describing.

**Plan:** assemble a small set of **building templates** from the Quaternius medieval-village
megakit (already in `asset_library`, modular: walls, corners, doors, windows, roofs, overhangs)
and place the right template per footprint by role:
- **Mine office (Maren)** — sturdy timber-and-brick, a sign/board, ore cart out front.
- **Chapel (Ilo)** — taller, a modest spire/bell, arched door.
- **Fence's shop (Sable)** — shuttered storefront, awning down.
- **Bakery (Joren)** — chimney smoking, a bread stall/counter facing the square.
- **The well + market** — real stalls (vegetable stall, cart) ringing the well — the stations
  Track 1's villagers use.
Plus a **mine entrance** (dark timbered mouth) on one edge, since the whole town is about the
vault below.

**Approach:** a data-driven `building_kit.gd` that stamps a template (list of piece + offset +
rotation) onto a footprint, oriented so the door faces the square. Reusable for future town
slices. Slightly fiddly (piece alignment) but one-time.

**Effort:** L. **Biggest visual payoff** of the three. **Depends on:** nothing new (assets in hand).

---

## Suggested sequence

1. **Track 2 provider decision** (unblocks portraits — the thing you most want to "get down").
2. **Track 3 village kit** in parallel (biggest look win; independent of the portrait decision).
3. **Track 1 stations** once stalls/benches exist for villagers to use.
4. Portrait review pass once the tool + provider are wired.

Then back to campaign mechanics (letter → factions → Accord), now against a town that looks and
feels alive.

---

## Owner purchases that would slot in (optional, all CC0-after-buy → committable)
- **Kenney All-in-1** ($19.95) — whole prebuilt buildings + market props, could shortcut Track 3.
- Portrait art packs stay OFF the table (AI pipeline covers portraits; the CrimsonDelight vendor
  is flagged risky).
