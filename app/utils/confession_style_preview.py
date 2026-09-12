"""Fixture samples + DALL-E helper for confession photo-style visual checks.

Does not read or write Story rows. Used by scripts/ and the non-prod test route.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import requests

from app.model.story import StoryType
from app.utils.image_generator import generate_ai_cover_image
from app.utils.prompts import CONFESSION_COVER_PHOTOGRAPHY_STYLE
from app.utils.story_image_prompt import (
    ensure_confession_photography_style,
    substitute_cover_placeholders,
)

logger = logging.getLogger(__name__)

SAMPLES: list[dict[str, Any]] = [
    {
        "slug": "01_liam_maine",
        "title": "The Quiet Harbour",
        "author_name": "Liam",
        "gender": "male",
        "age": 34,
        "location": "Deer Isle, Maine",
        "scene": (
            "Scrapbook collage confession cover on warm blush-pink paper with hot pink splatters, "
            "a pink CONFESSION banner, PRIVATE label, 3D cream title 'The Quiet Harbour' with hot pink "
            "shadow, torn tape reading Liam beside a USA flag, anatomical heart stamp. Right side: "
            "vertical taped photo of a solitary 34-year-old man in a wool sweater on a Maine dock at dusk, "
            "looking out over cold harbour water, candid editorial presence, single narrator only."
        ),
    },
    {
        "slug": "02_amara_lagos",
        "title": "Midnight Balcony",
        "author_name": "Amara",
        "gender": "female",
        "age": 27,
        "location": "Lagos, Nigeria",
        "scene": (
            "Scrapbook collage confession cover on warm blush-pink paper with hot pink splatters, "
            "a pink CONFESSION banner, PRIVATE label, 3D cream title 'Midnight Balcony' with hot pink "
            "shadow, torn tape reading Amara beside a Nigeria flag, anatomical heart stamp. Right side: "
            "vertical taped photo of a solitary 27-year-old woman in a simple high-collar blouse on a "
            "Lagos balcony at night, city lights soft behind her, closed eyes, thoughtful mood, "
            "single narrator only."
        ),
    },
    {
        "slug": "03_jonas_berlin",
        "title": "After the Train",
        "author_name": "Jonas",
        "gender": "male",
        "age": 41,
        "location": "Berlin, Germany",
        "scene": (
            "Scrapbook collage confession cover on warm blush-pink paper with hot pink splatters, "
            "a pink CONFESSION banner, PRIVATE label, 3D cream title 'After the Train' with hot pink "
            "shadow, torn tape reading Jonas beside a Germany flag, anatomical heart stamp. Right side: "
            "vertical taped photo of a solitary 41-year-old man in a dark coat on a Berlin U-Bahn "
            "platform, holding a letter, steam of breath in winter air, lonely candid moment, "
            "single narrator only."
        ),
    },
]


def build_sample_prompt(sample: dict[str, Any]) -> str:
    story = SimpleNamespace(story_type=StoryType.confession)
    raw = f"{sample['scene']} {CONFESSION_COVER_PHOTOGRAPHY_STYLE}"
    return ensure_confession_photography_style(
        substitute_cover_placeholders(
            raw, title=sample["title"], author_name=sample["author_name"]
        ),
        story,
    )


def get_sample(index: int) -> dict[str, Any]:
    """1-based sample index."""
    if index < 1 or index > len(SAMPLES):
        raise ValueError(f"sample must be 1..{len(SAMPLES)}")
    return SAMPLES[index - 1]


def generate_sample_cover(index: int) -> dict[str, Any]:
    """Call DALL-E for one fixture sample. No database writes.

    Returns dict with prompt, cover_url, cover_key, image_bytes (if downloadable).
    """
    sample = get_sample(index)
    prompt = build_sample_prompt(sample)
    url, key = generate_ai_cover_image(
        title=sample["title"],
        story_type="confession",
        author_name=sample["author_name"],
        image_prompt=prompt,
        gender=sample["gender"],
    )
    image_bytes: bytes | None = None
    if url and url.startswith(("http://", "https://")):
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            image_bytes = resp.content
        except Exception:
            logger.exception("Failed to download generated cover from %s", url)
    elif url and not url.startswith("http"):
        # Local media fallback path from upload_image_to_s3
        from pathlib import Path

        local = Path(url)
        if not local.is_file():
            local = Path("media") / url
        if local.is_file():
            image_bytes = local.read_bytes()

    return {
        "sample": sample,
        "prompt": prompt,
        "cover_url": url,
        "cover_key": key,
        "image_bytes": image_bytes,
    }
