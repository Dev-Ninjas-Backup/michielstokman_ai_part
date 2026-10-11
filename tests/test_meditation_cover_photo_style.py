"""Meditation cover photography style is warm, full-color, and safety-safe.

Meditation parity with confession:
- The template portrait path uses a warm amber-olive LOOK_V2 (not the retired sepia).
- The brand-collection line carries the warm full-color language (no stale "sepia").
- The legacy sepia LOOK survives only as a rollback alias.
- The collage IMAGE_PROMPT block is scrubbed of the bare-shoulder / collarbone
  language that OpenAI moderation rejects.
"""
from types import SimpleNamespace

from app.model.story import StoryType
from app.utils.prompts import (
    CONFESSION_COVER_PHOTOGRAPHY_LOOK,
    MEDITATION_COVER_BRAND_COLLECTION,
    MEDITATION_COVER_PHOTOGRAPHY_LOOK,
    MEDITATION_COVER_PHOTOGRAPHY_LOOK_V2,
    MEDITATION_COVER_PHOTOGRAPHY_PORTRAIT_CLOSING_V2,
    STORY_HUMAN_TEMPLATE,
)
from app.utils.story_image_prompt import build_portrait_only_prompt


def _meditation_story(**kwargs):
    defaults = dict(
        id="00000000-0000-0000-0000-000000000009",
        story_type=StoryType.meditation,
        title="Morning Light Settles",
        member_title=None,
        ai_generated_title=None,
        first_name="Mei",
        gender="female",
        age=32,
        sexual_orientation=None,
        city="Kyoto",
        country="Japan",
        location="Kyoto, Japan",
        high_intensity=False,
        hero_hook="A quiet morning of returning to myself.",
        hero_tagline="Breath And\nSoft Light",
        situation="Early light across a wooden floor in a still room.",
        background="Years of rushing finally slowed into presence.",
        story_text="The room held a soft hush while warmth reached the floorboards.",
        story_input=None,
        tags=[],
        growth_areas=[],
        image_source=None,
        cover_image_url=None,
        cover_image_key=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_meditation_look_v2_is_warm_full_color_amber_olive():
    """LOOK_V2 pivots meditation portraits to warm amber-olive contemplative color."""
    look = MEDITATION_COVER_PHOTOGRAPHY_LOOK_V2.lower()
    assert look.startswith("photography style (always apply, non-negotiable):")
    assert "full color" in look
    assert "amber-olive" in look
    assert "golden" in look
    assert "never desaturated or monochrome" in look

    # Realism cues must not be dropped again — they do real anti-AI work.
    assert "skin texture" in look
    assert "depth of field" in look
    assert "readable mid-ground" in look
    assert "fabric folds" in look

    # sepia / black-and-white survive only inside the closing prohibition — the
    # style language itself must carry no monochrome instruction.
    body, sep, prohibition = look.partition("avoid cold tones")
    assert sep, "expected the closing 'Avoid cold tones…' prohibition"
    for banned in ("sepia", "black-and-white", "grayscale", "greyscale"):
        assert banned not in body, f"{banned!r} leaked into meditation LOOK_V2 language"
    assert "desaturated/sepia/black-and-white" in prohibition


def test_meditation_brand_collection_drops_sepia_language():
    """The brand line must read warm and full-color — not the retired sepia."""
    brand = MEDITATION_COVER_BRAND_COLLECTION.lower()
    assert "sepia" not in brand
    assert "full-color" in brand
    assert "amber-olive" in brand
    assert "golden-earth" in brand
    assert "meditation" in brand


def test_meditation_template_path_uses_look_v2_not_retired_sepia():
    prompt = build_portrait_only_prompt(_meditation_story(), use_llm_brief=False)
    assert MEDITATION_COVER_PHOTOGRAPHY_LOOK_V2 in prompt
    assert MEDITATION_COVER_PHOTOGRAPHY_PORTRAIT_CLOSING_V2 in prompt
    assert MEDITATION_COVER_BRAND_COLLECTION in prompt
    # The retired sepia look must not drive the live meditation portrait prompt.
    # ("sepia" legitimately survives once inside LOOK_V2's closing prohibition, so
    #  assert on the retired look's signature phrase rather than the bare word.)
    assert CONFESSION_COVER_PHOTOGRAPHY_LOOK not in prompt
    assert "warm sepia toning" not in prompt.lower()
    assert "confession" not in prompt.lower()


def test_legacy_sepia_look_alias_retained_for_rollback():
    """The pre-pivot LOOK stays byte-identical as a rollback alias only."""
    assert MEDITATION_COVER_PHOTOGRAPHY_LOOK is CONFESSION_COVER_PHOTOGRAPHY_LOOK
    assert "sepia" in MEDITATION_COVER_PHOTOGRAPHY_LOOK.lower()


def test_meditation_collage_block_is_safety_scrubbed():
    """The dalle/collage meditation block must ban the risky bare-skin language."""
    assert (
        "you MUST NOT describe nudity, bare skin, bare shoulders, collarbones"
        in STORY_HUMAN_TEMPLATE
    )
    assert "fully clothed" in STORY_HUMAN_TEMPLATE
    # Old safety-risky phrasings must be gone.
    assert "slips off one bare shoulder" not in STORY_HUMAN_TEMPLATE
    assert "thin-strap top" not in STORY_HUMAN_TEMPLATE
    assert "sternum" not in STORY_HUMAN_TEMPLATE
    # The warm, calm art direction replaces the retired sepia/vintage wording.
    assert "warm amber-toned photograph" in STORY_HUMAN_TEMPLATE
    assert "sepia-toned vintage photo" not in STORY_HUMAN_TEMPLATE
