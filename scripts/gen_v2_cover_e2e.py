#!/usr/bin/env python3
"""End-to-end test script for V2 cover generation.

Safe: no Story DB writes.
Inspects the built V2 prompt and (if OpenAI API key is present) tests generation.

Usage:
  python scripts/gen_v2_cover_e2e.py [--generate]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.model.story import StoryType  # noqa: E402
from app.utils.image_generator import generate_ai_cover_image  # noqa: E402
from app.utils.story_cover import cover_generation_method, uses_v2_pipeline  # noqa: E402
from app.utils.story_image_prompt import build_v2_cover_prompt  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Test V2 cover prompt generation.")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Actually call OpenAI API to generate image (requires OPENAI_API_KEY).",
    )
    args = parser.parse_args()

    # Fixture matching the client's reference
    story = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000002",
        story_type=StoryType.confession,
        title="Two Men and Nia",
        member_title=None,
        ai_generated_title=None,
        first_name="Rory",
        gender="male",
        age=23,
        sexual_orientation="heterosexual",
        location="Wales, UK",
        city="Wales",
        country="UK",
        high_intensity=True,
        hero_hook="They took a little GHB in Bacardi cola.",
        hero_tagline=None,
        situation="Enjoying cocktails in an intimate, dimly lit bar.",
        background="Two adult men and one adult Black woman sitting closely together.",
        story_text="They took a little GHB in Bacardi cola. The music drifted through the bar as we talked and laughed.",
        story_input=None,
        cover_image_url=None,
        cover_image_key=None,
        image_source=None,
    )

    print("=" * 70)
    print(f"Current COVER_GENERATION_METHOD: {cover_generation_method()}")
    print(f"Uses V2 pipeline for confession story: {uses_v2_pipeline(story)}")
    print("=" * 70)

    prompt = build_v2_cover_prompt(story, use_llm_scene=False)
    print("\n--- Generated V2 Cover Prompt ---")
    print(prompt)
    print(f"\nPrompt word count: {len(prompt.split())}")
    print(f"Prompt char count: {len(prompt)}")

    if args.generate:
        if not settings.OPENAI_API_KEY:
            print("\nError: OPENAI_API_KEY is not configured.")
            sys.exit(1)
        print("\nCalling OpenAI API with V2 prompt...")
        url, key = generate_ai_cover_image(
            title=story.title,
            story_type=story.story_type.value,
            author_name=story.first_name,
            image_prompt=prompt,
            gender=story.gender,
            lock_identity=False,
        )
        print(f"Generation result: url={url}, key={key}")


if __name__ == "__main__":
    main()
