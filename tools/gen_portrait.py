"""Generate a painted talk-screen PORTRAIT for a game character, from that character's own sheet.

Pipeline (roadmap Track 2, docs/visual-polish-roadmap.md):
  1. Claude (our own stack) writes a consistent painted-fantasy image PROMPT from the character's
     name/role/concept/age/backstory + a fixed style preamble.
  2. A hosted image model renders it (default: fal.ai Flux, permissive — enable_safety_checker off,
     so scarred villains / charred undead / hard faces aren't over-blocked). Provider lives behind
     _render(); swap via PORTRAIT_PROVIDER (fal | comfy | openai).
  3. Every result lands in godot/assets/portraits/review/ — the owner REVIEWS each face and moves
     the keepers to godot/assets/portraits/<slug>.png (the talk screen loads that at runtime).
Variants (--mouth, --emotions) are rendered image-to-image FROM the approved base so the face
stays consistent — the base's mouth-open frame drives the talk-screen lip flap, the emotion frames
feed the engine-chosen expression slot.

Usage:
  python tools/gen_portrait.py <slug> [--prompt-only] [--mouth] [--emotions] [--base PATH]
  python tools/gen_portrait.py rpg-maren            # base portrait -> review/
  python tools/gen_portrait.py rpg-maren --prompt-only   # just print Claude's prompt (no image key)
  python tools/gen_portrait.py rpg-maren --mouth --emotions --base godot/assets/portraits/rpg-maren.png

Keys: ANTHROPIC_API_KEY (prompt authoring, already in .env) + FAL_KEY (rendering — see README).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REVIEW = ROOT / "godot" / "assets" / "portraits" / "review"
FINAL = ROOT / "godot" / "assets" / "portraits"
EMOTIONS = ["neutral", "smile", "sad", "angry", "surprised", "thoughtful"]

STYLE_SYSTEM = """You write ONE image-generation prompt for a painted fantasy CHARACTER PORTRAIT \
for a cohesive game cast (they must all look like the same illustrated set).

Always bake in this style, in your own words: hand-painted digital fantasy illustration, \
semi-realistic, in the vein of Pillars of Eternity / Baldur's Gate portrait art; head-and-shoulders \
bust, three-quarter view, the character looking toward the viewer; soft directional lighting; a \
muted, painterly background that suggests the setting (never a flat colour); rich visible brushwork. \
NOT anime, NOT photoreal, NOT a 3D render, NOT cartoon.

Framing for later animation: mouth CLOSED and relaxed, whole face visible and unobstructed, centred \
(the portrait gets animated to speak).

Content: describe face, age, build, hair, expression, clothing and gear from the brief. Grounded \
medieval fantasy. Mature where the character calls for it — scars, grime, a hard or menacing look, \
weathered age, a charred/undead cast, worn armour — but always TASTEFUL, CLOTHED, non-sexualised, \
portfolio-presentable. No nudity, no sexual content, no gratuitous gore.

Output ONLY the prompt text: one rich paragraph, ~60-90 words. No preamble, no quotes."""


def _all_cast() -> dict:
    """{slug: Character} across every slice's cast."""
    from game.rpg import content
    cast: dict = {}
    for builder in content.SLICES.values():
        try:
            _, chars = builder()
            cast.update(chars)
        except Exception as exc:  # noqa: BLE001 — one bad slice shouldn't hide the rest
            print(f"  (skipped a slice: {exc})")
    return cast


def _brief(c) -> str:
    g = lambda k: (getattr(c, k, "") or "")
    parts = [f"Name: {g('name')}", f"Role: {g('role')}", f"Concept: {g('concept')}",
             f"Age: {g('age')}", f"Backstory: {g('backstory')}"]
    return "\n".join(p for p in parts if p.split(": ", 1)[1].strip())


def author_prompt(c, *, extra: str = "") -> str:
    """Claude writes the image prompt from the character sheet."""
    import anthropic
    from orchestrator.config import get_settings
    key = get_settings().anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY not set (it's already in .env for the DM).")
    client = anthropic.Anthropic(api_key=key)
    user = _brief(c) + (f"\n\nAlso: {extra}" if extra else "")
    msg = client.messages.create(model="claude-opus-4-8", max_tokens=500,
                                 system=STYLE_SYSTEM, messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


# ------------------------------------------------------------------ render seam

def _render(prompt: str, out: Path, ref_path: Path | None = None) -> None:
    provider = os.environ.get("PORTRAIT_PROVIDER", "fal")
    if provider == "fal":
        _render_fal(prompt, out, ref_path)
    else:
        raise SystemExit(f"PORTRAIT_PROVIDER={provider} not wired yet (fal only for now). "
                         "comfy/openai seams are documented in the README.")


def _render_fal(prompt: str, out: Path, ref_path: Path | None) -> None:
    if not os.environ.get("FAL_KEY"):
        raise SystemExit("FAL_KEY not set — get one at fal.ai (see godot/assets/portraits/README.md) "
                         "and add FAL_KEY=... to .env, then re-run.")
    try:
        import fal_client
    except ImportError:
        raise SystemExit("fal-client not installed: .venv\\Scripts\\pip install fal-client")
    if ref_path is not None:
        ref_url = fal_client.upload_file(str(ref_path))     # base -> hosted url for consistency
        result = fal_client.subscribe("fal-ai/flux/dev/image-to-image", arguments={
            "prompt": prompt, "image_url": ref_url, "strength": 0.55,
            "num_images": 1, "enable_safety_checker": False})
    else:
        result = fal_client.subscribe("fal-ai/flux/dev", arguments={
            "prompt": prompt, "image_size": "portrait_4_3", "num_images": 1,
            "num_inference_steps": 30, "guidance_scale": 3.5, "enable_safety_checker": False})
    url = result["images"][0]["url"]
    import urllib.request
    out.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out)
    print(f"  -> {out.relative_to(ROOT)}")


# ------------------------------------------------------------------ main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--prompt-only", action="store_true", help="print Claude's prompt; render nothing")
    ap.add_argument("--mouth", action="store_true", help="also render a mouth-open frame (lip flap)")
    ap.add_argument("--emotions", action="store_true", help="also render the emotion variants")
    ap.add_argument("--base", help="approved base PNG to derive variants from (default: review/<slug>.png)")
    args = ap.parse_args()

    cast = _all_cast()
    c = cast.get(args.slug)
    if c is None:
        raise SystemExit(f"unknown slug {args.slug!r}; known: {', '.join(sorted(cast))}")

    prompt = author_prompt(c)
    print(f"\n[{args.slug}] Claude's portrait prompt:\n{prompt}\n")
    if args.prompt_only:
        return

    base = Path(args.base) if args.base else (REVIEW / f"{args.slug}.png")
    if not args.base:                                        # render the base into review/
        _render(prompt, base)
    elif not base.exists():
        raise SystemExit(f"--base {base} not found")

    if args.mouth:
        mp = author_prompt(c, extra="Same person, same framing, but MOUTH OPEN mid-word as if "
                                    "speaking. Identical face, hair, clothing, lighting.")
        _render(mp, REVIEW / f"{args.slug}_mouth_open.png", ref_path=base)
    if args.emotions:
        for emo in EMOTIONS:
            ep = author_prompt(c, extra=f"Same person, same framing, but a clearly {emo} expression. "
                                        "Identical face, hair, clothing, lighting.")
            _render(ep, REVIEW / f"{args.slug}_{emo}.png", ref_path=base)

    print(f"\nReview godot/assets/portraits/review/ — move the keepers up to "
          f"godot/assets/portraits/ and the talk screen shows them automatically.")


if __name__ == "__main__":
    main()
