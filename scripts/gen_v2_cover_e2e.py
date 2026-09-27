#!/usr/bin/env python3
"""End-to-end test script for V2 cover generation.

Safe: no Story DB writes.
Inspects the built V2 prompt and (if OpenAI API key is present) tests generation.

Usage:
  python scripts/gen_v2_cover_e2e.py [--generate]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.model.story import StoryType  # noqa: E402
from app.utils.image_generator import generate_ai_cover_image  # noqa: E402
from app.utils.story_cover import cover_generation_method, uses_v2_pipeline  # noqa: E402
from app.utils.story_image_prompt import (  # noqa: E402
    build_v2_cover_prompt,
    extract_v2_visual_art_direction,
    refine_story_visual_art_direction,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Test V2 2-step AI visual art direction and cover prompt generation.")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Actually call OpenAI API to generate image (requires OPENAI_API_KEY).",
    )
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help="Use real LLM API for visual refinement and art direction extraction.",
    )
    args = parser.parse_args()

    # Story fixture matching reference
    story = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000002",
        story_type=StoryType.confession,
        title="Two Men and Nia",
        member_title=None,
        ai_generated_title=None,
        first_name="Lars",
        gender="male",
        age=44,
        sexual_orientation=None,
        location="Ibiza, Spain",
        city="Ibiza",
        country="Spain",
        high_intensity=True,
        hero_hook="They took a little GHB in Bacardi cola.",
        hero_tagline=None,
        situation="Intimate outdoor terrace setting in Ibiza at night, inspired by the atmosphere of Cova Santa.",
        background="One 44-year-old Swedish man, one 38-year-old Black man from Brooklyn, and one adult Black woman from Ghana who lives in Berlin.",
        story_text="They took a little GHB in Bacardi cola. The terrace was warm with pine and stone under the Ibiza night.",
        story_input=None,
        cover_image_url=None,
        cover_image_key=None,
        image_source=None,
    )

    print("=" * 80)
    print("V2 EDITORIAL COVER GENERATION PIPELINE")
    print(f"Current COVER_GENERATION_METHOD: {cover_generation_method()}")
    print(f"Uses V2 pipeline for confession story: {uses_v2_pipeline(story)}")
    print("=" * 80)

    # Step 1: Story-to-Visual-Art-Direction Refinement
    print("\n[STEP 1] Story-to-Visual-Art-Direction Refinement (Editorial Visual Brief):")
    visual_brief = refine_story_visual_art_direction(story, use_llm=args.live_llm)
    print(visual_brief)

    # Step 2: Structured Visual Art Direction Extraction
    print("\n[STEP 2] Structured Visual Art Direction JSON:")
    art_dir = extract_v2_visual_art_direction(story, visual_brief=visual_brief, use_llm=args.live_llm)
    print(json.dumps(art_dir, indent=2))

    # Step 3: Assembled Cover Prompt Builder
    print("\n[STEP 3] Assembled V2 Cover Prompt (Image Prompt Builder):")
    prompt = build_v2_cover_prompt(story, art_direction=art_dir, use_llm_scene=args.live_llm)
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

