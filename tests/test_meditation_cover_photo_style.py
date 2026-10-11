"""Meditation cover photography style is warm sunrise-gold, solo, and safety-safe.

Meditation parity with confession (but deliberately distinct):
- The template portrait path uses a soft sunrise-gold LOOK_V2 (not the retired sepia,
  and not confession's bright golden-hour lifestyle look).
- Meditation covers are ALWAYS a single person — never a couple or group.
- The brand-collection line carries the sunrise-gold language (no stale "sepia").
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
from app.utils.story_image_prompt import (
    _cast_mode,
    build_portrait_only_prompt,
    portrait_cast_instruction,
)


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


def test_meditation_look_v2_is_soft_sunrise_gold_and_distinct_from_confession():
    """LOOK_V2 pivots meditation portraits to a serene sunrise-gold dawn palette."""
    look = MEDITATION_COVER_PHOTOGRAPHY_LOOK_V2.lower()
    assert look.startswith("photography style (always apply, non-negotiable):")
    assert "full color" in look
    assert "sunrise-gold" in look
    assert "sage" in look
    assert "never desaturated or monochrome" in look

    # Distinct from the confession golden-hour lifestyle look — quiet dawn, not
    # bright sun-flared celebration.
    assert "golden-hour" in look  # only inside the "never bright golden-hour" negation
    assert "sun flare" in look  # likewise inside the negation
    assert "single person" in look
    assert "never a couple or group" in look

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
    """The brand line must read sunrise-gold and solo — not the retired sepia."""
    brand = MEDITATION_COVER_BRAND_COLLECTION.lower()
    assert "sepia" not in brand
    assert "sunrise-gold" in brand
    assert "sage" in brand
    assert "single person" in brand
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


def test_meditation_cover_is_always_solo_even_with_partner_wording():
    """A meditation that mentions a partner/friend must still render a single person."""
    coupled = _meditation_story(
        situation="My partner and I sit together breathing slowly in the morning.",
        background="We started meditating together after a hard year.",
        story_text="We breathe in, we breathe out, holding hands on the floor.",
    )
    assert _cast_mode(coupled) == "solo"
    cast = portrait_cast_instruction(coupled)
    assert "ALONE" in cast
    assert "Never a couple" in cast

    prompt = build_portrait_only_prompt(coupled, use_llm_brief=False)
    # No couple / second-person casting instructions may leak into the meditation prompt.
    assert "second person" not in prompt.lower()
    assert "EXACTLY TWO PEOPLE" not in prompt
    assert "small group" not in prompt.lower()


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
    # The sunrise-gold, solo art direction replaces the retired sepia/vintage wording.
    assert "soft sunrise-gold toned photograph" in STORY_HUMAN_TEMPLATE
    assert "sepia-toned vintage photo" not in STORY_HUMAN_TEMPLATE
