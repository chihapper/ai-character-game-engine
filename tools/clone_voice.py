"""CLI fallback for voice cloning.

The primary path for cloning is the in-app "Create Character" view. This script
exists for headless/automation use: clone a voice from an audio file and (optionally)
write a character profile, without the browser.

Usage:
    python -m tools.clone_voice --sample me.wav --name "Nova" \
        --provider inworld --prompt "You are Nova, a calm narrator." \
        --greeting "There you are." --save

Run from the repo root so the `orchestrator` package is importable.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from orchestrator.adapters.tts_cartesia import CartesiaTTS
from orchestrator.adapters.tts_inworld import InworldTTS
from orchestrator.character_store import Character, save_character, slugify


def make_tts(provider: str):
    return CartesiaTTS() if provider == "cartesia" else InworldTTS()


async def run(args: argparse.Namespace) -> int:
    sample_path = Path(args.sample)
    if not sample_path.exists():
        print(f"error: sample file not found: {sample_path}", file=sys.stderr)
        return 1

    sample_bytes = sample_path.read_bytes()
    tts = make_tts(args.provider)
    print(f"Cloning '{args.name}' via {args.provider} ({len(sample_bytes)} bytes)...")
    voice_id = await tts.clone_voice(sample_bytes, args.name)
    print(f"voice_id = {voice_id}")

    if args.save:
        slug = slugify(args.name)
        character = Character(
            slug=slug,
            name=args.name,
            system_prompt=args.prompt or f"You are {args.name}.",
            voice_id=voice_id,
            tts_provider=args.provider,
            greeting=args.greeting or "",
            memory_namespace=slug,
        )
        save_character(character)
        print(f"Saved character profile: characters/{slug}.yaml")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Clone a voice and optionally save a character.")
    parser.add_argument("--sample", required=True, help="Path to a ~10-15s voice sample (wav/mp3/webm).")
    parser.add_argument("--name", required=True, help="Character / voice display name.")
    parser.add_argument("--provider", default="inworld", choices=["inworld", "cartesia"])
    parser.add_argument("--prompt", default="", help="System prompt (personality).")
    parser.add_argument("--greeting", default="", help="Opening line spoken on connect.")
    parser.add_argument("--save", action="store_true", help="Write a character YAML profile.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
