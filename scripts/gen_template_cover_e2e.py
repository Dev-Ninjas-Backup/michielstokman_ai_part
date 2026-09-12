#!/usr/bin/env python3
"""End-to-end: portrait-only DALL-E → cover_template Playwright composite.

Safe: no Story DB writes. Saves under scratch/template_cover_e2e/.

  COVER_GENERATION_METHOD is not required — this script always uses the
  portrait+template path for the three fixture stories.

  python scripts/gen_template_cover_e2e.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.cover_template.render import render_cover_png_sync  # noqa: E402
from app.model.story import StoryType  # noqa: E402
from app.utils.confession_style_preview import SAMPLES  # noqa: E402
from app.utils.image_generator import generate_ai_cover_image  # noqa: E402
from app.utils.s3 import delete_s3_object  # noqa: E402
from app.utils.story_cover import story_to_cover_template_payload  # noqa: E402
from app.utils.story_image_prompt import build_portrait_only_prompt  # noqa: E402

OUT = ROOT / "scratch" / "template_cover_e2e"

# Distinct subtitle shapes to verify pink underline tracks content height:
# Liam = 2 lines, Amara = 1 line, Jonas = empty (underline under title block).
_SUBTITLES = {
    "01_liam_maine": "A Night That\nLiberated My Essence",
    "02_amara_lagos": "Choosing Myself",
    "03_jonas_berlin": "",
}

_MOODS = {
    "01_liam_maine": (
        "Standing alone on a cold harbour dock at dusk, looking out over the water "
        "after finally telling the truth."
    ),
    "02_amara_lagos": (
        "On a Lagos balcony at night with city lights behind her, eyes closed in a "
        "quiet moment of choosing herself."
    ),
    "03_jonas_berlin": (
        "On a winter Berlin U-Bahn platform holding a letter, breath visible in the "
        "cold air after a hard goodbye."
    ),
}

# Production-length fixture matching the reported "Geometry of Fog" overflow case.
_FOG = {
    "slug": "04_geometry_of_fog",
    "title": "Geometry of Fog",
    "author_name": "Maya",
    "gender": "female",
    "age": 32,
    "location": "San Francisco, USA",
    "subtitle": "The memory stirred but my boundaries held",
    "hook": (
        "I paused at the door. The memory stirred but my boundaries held as fog "
        "pressed against the glass and someone waited in the hallway behind me."
    ),
    "situation": (
        "Standing in a foggy San Francisco doorway at night, hand on the frame, "
        "choosing not to go back inside."
    ),
}


def _story_from_sample(sample: dict) -> SimpleNamespace:
    loc = sample["location"]
    city, country = (loc.split(",", 1) + [""])[:2] if "," in loc else (loc, "")
    mood = sample.get("situation") or _MOODS.get(
        sample["slug"], f"A candid emotional moment in {loc}."
    )
    hook = sample.get("hook") or mood
    tag = sample["subtitle"] if "subtitle" in sample else _SUBTITLES.get(
        sample["slug"], "A Night That\nLiberated My Essence"
    )
    return SimpleNamespace(
        id=f"e2e-{sample['slug']}",
        story_type=StoryType.confession,
        title=sample["title"],
        member_title=sample["title"],
        ai_generated_title=None,
        first_name=sample["author_name"],
        gender=sample["gender"],
        age=sample["age"],
        sexual_orientation="bisexual",
        city=city.strip(),
        country=country.strip(),
        location=loc,
        high_intensity=True,
        # Raw long copy — production path truncates via story_to_cover_template_payload.
        hero_hook=hook,
        hero_tagline=tag,
        situation=mood,
        background=f"Lives in {loc}.",
        story_text=hook,
        story_input=None,
    )


def _run_one(sample: dict, *, has_key: bool) -> dict:
    story = _story_from_sample(sample)
    prompt = build_portrait_only_prompt(story)
    prompt_path = OUT / f"{sample['slug']}_portrait_prompt.txt"
    prompt_path.write_text(prompt + "\n", encoding="utf-8")

    portrait_url = None
    portrait_key = None
    if has_key:
        print(f"DALL-E portrait for {sample['slug']}…", flush=True)
        portrait_url, portrait_key = generate_ai_cover_image(
            title=sample["title"],
            story_type="confession",
            author_name=sample["author_name"],
            image_prompt=prompt,
            gender=sample["gender"],
        )
        print(f"  portrait -> {portrait_url or 'FAILED'}", flush=True)
    else:
        print(
            f"No OPENAI_API_KEY — compositing {sample['slug']} with template sample photo",
            flush=True,
        )

    payload = story_to_cover_template_payload(story, photo_url=portrait_url)
    print(
        f"Playwright composite for {sample['slug']} "
        f"(subtitle={payload['subtitle']!r} desc={payload['description']!r})…",
        flush=True,
    )
    png = render_cover_png_sync(payload)
    out_png = OUT / f"{sample['slug']}_composite.png"
    out_png.write_bytes(png)
    print(f"  wrote {out_png} ({len(png)} bytes)", flush=True)

    from app.cover_template.render import measure_cover_geometry_sync

    geom = measure_cover_geometry_sync(payload)
    print(
        f"  geometry subtitle_bottom={geom.get('subtitle_bottom')} "
        f"underline_top={geom.get('underline_top')} gap={geom.get('underline_gap')} "
        f"confession_bottom={geom.get('confession', {}).get('bottom')} "
        f"location_top≈1417",
        flush=True,
    )

    if portrait_key:
        delete_s3_object(portrait_key)

    conf = geom.get("confession") or {}
    loc_top = 1417
    return {
        "slug": sample["slug"],
        "title": sample["title"],
        "subtitle": payload["subtitle"],
        "subtitle_line_lens": [len(x) for x in payload["subtitle"].split("\n") if x],
        "description": payload["description"],
        "description_len": len(payload["description"]),
        "used_dalle_portrait": bool(portrait_url),
        "prompt_file": str(prompt_path),
        "composite_file": str(out_png),
        "prompt_words": len(prompt.split()),
        "pose_in_prompt": "Pose / body language (required, story-specific)" in prompt,
        "framing_in_prompt": "full head and shoulders" in prompt,
        "arms_out_default_absent": "arms outstretched" not in prompt,
        "confession_clears_location": (conf.get("bottom") or 0) < loc_top,
        "underline_gap": geom.get("underline_gap"),
        "geometry": geom,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    has_key = bool(settings.OPENAI_API_KEY)

    for sample in list(SAMPLES) + [_FOG]:
        results.append(_run_one(sample, has_key=has_key))

    summary = OUT / "results.json"
    summary.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
