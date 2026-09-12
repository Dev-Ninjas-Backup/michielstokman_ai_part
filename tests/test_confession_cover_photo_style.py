"""Confession cover photography style is fixed across P1 and P2."""
from types import SimpleNamespace

from app.model.story import StoryType
from app.utils.prompts import (
    CONFESSION_COVER_PHOTOGRAPHY_STYLE,
    STORY_HUMAN_TEMPLATE,
    cover_identity_template_vars,
)
from app.utils.story_image_prompt import (
    ensure_confession_photography_style,
    resolve_image_prompt,
)


def test_confession_style_constant_is_verbatim():
    assert CONFESSION_COVER_PHOTOGRAPHY_STYLE.startswith(
        "Photography style (always apply, non-negotiable):"
    )
    assert "warm sepia toning" in CONFESSION_COVER_PHOTOGRAPHY_STYLE
    assert "visible film grain" in CONFESSION_COVER_PHOTOGRAPHY_STYLE
    assert "reminiscent of vintage analog documentary photography" in CONFESSION_COVER_PHOTOGRAPHY_STYLE
    assert "arms outstretched" in CONFESSION_COVER_PHOTOGRAPHY_STYLE
    assert "never looking directly at camera unless laughing candidly" in CONFESSION_COVER_PHOTOGRAPHY_STYLE


def test_p1_template_includes_fixed_confession_style():
    assert CONFESSION_COVER_PHOTOGRAPHY_STYLE in STORY_HUMAN_TEMPLATE
    assert "PHOTOGRAPHY STYLE (CONFESSIONS ONLY — NON-NEGOTIABLE)" in STORY_HUMAN_TEMPLATE
    assert "moody pink duotone" not in STORY_HUMAN_TEMPLATE
    filled = STORY_HUMAN_TEMPLATE.format(
        story_type="confession",
        **cover_identity_template_vars("Lisa", "female", "Barcelona"),
    )
    assert CONFESSION_COVER_PHOTOGRAPHY_STYLE in filled


def test_ensure_appends_style_once_for_confession():
    story = SimpleNamespace(story_type=StoryType.confession)
    once = ensure_confession_photography_style("Harbour scene with Liam.", story)
    assert once.endswith(CONFESSION_COVER_PHOTOGRAPHY_STYLE) or (
        CONFESSION_COVER_PHOTOGRAPHY_STYLE in once
    )
    twice = ensure_confession_photography_style(once, story)
    assert twice.count("Photography style (always apply, non-negotiable)") == 1


def test_ensure_skips_non_confession():
    story = SimpleNamespace(story_type=StoryType.meditation)
    text = "Meditation collage scene."
    assert ensure_confession_photography_style(text, story) == text


def test_resolve_injects_style_on_p1_generated_prompt():
    story = SimpleNamespace(
        story_type=StoryType.confession,
        title="The Harbour",
        member_title=None,
        first_name="Liam",
        image_prompt=None,
        story_text="I walked the shore.",
        id="x",
    )
    resolved = resolve_image_prompt(
        story,
        "Collage with title [INSERT GENERATED TITLE HERE] and tape [INSERT AUTHOR NAME HERE].",
    )
    assert resolved is not None
    assert "Liam" in resolved
    assert "The Harbour" in resolved
    assert CONFESSION_COVER_PHOTOGRAPHY_STYLE in resolved
