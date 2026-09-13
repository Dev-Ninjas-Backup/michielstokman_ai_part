"""Tests for COVER_GENERATION_METHOD routing (dalle default vs template)."""
from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.model.story import ImageSource, StoryType
from app.utils import story_cover
from app.utils.prompts import CONFESSION_COVER_PHOTOGRAPHY_LOOK
from app.utils.story_image_prompt import (
    brief_story_mood_scene,
    build_portrait_only_prompt,
    portrait_pose_instruction,
    portrait_scene_detail,
)


def _story(**kwargs):
    defaults = dict(
        id="00000000-0000-0000-0000-000000000001",
        story_type=StoryType.confession,
        title="To Wasteland On My Own",
        member_title=None,
        ai_generated_title=None,
        first_name="Lisa",
        gender="female",
        age=28,
        sexual_orientation="bisexual",
        city="Barcelona",
        country="Spain",
        location="Barcelona, Spain",
        high_intensity=True,
        hero_hook="A confession about shame, desire and finally choosing me.",
        hero_tagline="A Night That\nLiberated My Essence",
        situation="Leaving a relationship that kept her small.",
        background="Grew up between cities.",
        story_text="Longer story body here.",
        story_input=None,
        image_source=None,
        cover_image_url=None,
        cover_image_key=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_cover_generation_method_defaults_to_dalle():
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "dalle"):
        assert story_cover.cover_generation_method() == "dalle"
        assert story_cover.uses_template_pipeline(_story()) is False


def test_template_flag_applies_to_confession_only():
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "template"):
        assert story_cover.uses_template_pipeline(_story()) is True
        assert (
            story_cover.uses_template_pipeline(
                _story(story_type=StoryType.meditation)
            )
            is False
        )


def test_story_to_cover_template_payload_maps_fields():
    payload = story_cover.story_to_cover_template_payload(_story())
    assert payload["author_name"] == "Lisa"
    assert payload["gender"] == "female"
    assert payload["orientation"] == "bisexual"
    assert payload["age"] == "28"
    assert payload["city"] == "Barcelona"
    assert payload["country"] == "Spain"
    assert payload["is_explicit"] is True
    assert "shame" in payload["description"]
    # Title is first two words (complete) so the brush headline stays left of the photo.
    assert payload["title"] == "To\nWasteland"
    assert payload["photo_url"] is None


def test_build_portrait_only_prompt_is_not_collage_and_reuses_style():
    prompt = build_portrait_only_prompt(_story())
    assert CONFESSION_COVER_PHOTOGRAPHY_LOOK in prompt
    assert "arms outstretched" not in prompt
    assert "28-year-old female" in prompt
    assert "Barcelona" in prompt
    assert "no collage" in prompt.lower()
    assert "no text" in prompt.lower()
    assert "Do not default to a generic triumphant arms-out pose" in prompt
    assert "CONFESSION banner" not in prompt
    assert "[INSERT GENERATED TITLE HERE]" not in prompt
    mood = brief_story_mood_scene(_story())
    assert "Leaving a relationship" in mood


def test_portrait_pose_follows_story_physical_action():
    holding = portrait_pose_instruction(
        _story(
            situation="On a winter Berlin U-Bahn platform holding a letter after goodbye."
        )
    )
    assert "holding a letter" in holding.lower()
    assert "Do not default to a generic triumphant arms-out pose" in holding

    dock = portrait_pose_instruction(
        _story(
            situation="Standing alone on a cold harbour dock at dusk, looking out over the water."
        )
    )
    assert "standing" in dock.lower()
    assert "looking out" in dock.lower()

    balcony = portrait_pose_instruction(
        _story(
            situation="On a Lagos balcony at night, eyes closed in a quiet contemplative moment."
        )
    )
    assert "leaning" in balcony.lower() or "balcony" in balcony.lower()
    assert "contemplative" in balcony.lower()


def test_description_truncates_at_last_complete_word():
    long_hook = (
        "Standing alone on a cold harbour dock at dusk, looking out over the water "
        "after finally telling the truth."
    )
    # Old buggy cut landed mid-word on "aft".
    assert long_hook[:77].endswith("aft")
    payload = story_cover.story_to_cover_template_payload(_story(hero_hook=long_hook))
    desc = payload["description"]
    assert len(desc) <= story_cover.CONFESSION_DESCRIPTION_HARD_LIMIT
    assert long_hook.startswith(desc)
    assert not desc.endswith(("aft", "co", "the", "a", "in"))
    dangling = (
        "On a Lagos balcony at night with city lights behind her, eyes closed in a "
        "quiet moment of choosing herself."
    )
    trimmed = story_cover.truncate_at_last_word(dangling)
    assert trimmed.endswith("eyes closed")
    assert not trimmed.endswith(("in a", " in", " a"))


def test_description_prefers_complete_sentence_within_soft_limit():
    hook = (
        "I paused at the door. Everything after that still burns when I remember it now."
    )
    desc = story_cover.truncate_at_sentence(hook)
    assert desc == "I paused at the door."
    assert len(desc) <= story_cover.CONFESSION_DESCRIPTION_SOFT_LIMIT


def test_subtitle_wraps_and_truncates_to_hard_line_limit():
    long = "The memory stirred but my boundaries held"
    payload = story_cover.story_to_cover_template_payload(_story(hero_tagline=long))
    lines = payload["subtitle"].split("\n")
    assert 1 <= len(lines) <= 2
    assert all(len(line) <= story_cover.SUBTITLE_LINE_HARD_LIMIT for line in lines)
    # Soft wrap keeps line1 near the soft width so Edo glyphs do not spill into the photo.
    assert len(lines[0]) <= story_cover.SUBTITLE_LINE_SOFT_LIMIT + 2
    joined = " ".join(lines).lower()
    assert "memory" in joined
    # Never mid-word (e.g. HEL from HELD).
    assert not any(re.search(r"\bHEL$", line, re.I) for line in lines)
    assert not any(re.search(r"\bBOUNDAR$", line, re.I) for line in lines)


def test_build_portrait_only_prompt_requests_headroom_framing():
    prompt = build_portrait_only_prompt(_story())
    assert "full head and shoulders" in prompt
    assert "4:5" in prompt
    assert "adequate headroom" in prompt
    assert "aggressive cropping" in prompt


def test_confession_look_keeps_sepia_bw_and_adds_realism_cues():
    look = CONFESSION_COVER_PHOTOGRAPHY_LOOK.lower()
    assert "sepia" in look
    assert "black-and-white" in look
    assert "film grain" in look
    assert "skin texture" in look
    assert "depth of field" in look
    assert "fabric folds" in look


def test_build_portrait_only_prompt_always_requires_rich_environment():
    quiet = build_portrait_only_prompt(
        _story(
            situation="Sitting alone by a window at night in a quiet contemplative moment.",
            title="Second Draft",
        )
    )
    assert "rich environmental detail" in quiet
    assert "never a flat, plain, or empty background" in quiet
    assert "at least two concrete background anchors" in quiet
    assert "Do not default to a generic triumphant arms-out pose" in quiet
    assert "arms outstretched" not in quiet
    assert "Physically ground the subject" in quiet
    assert "Scene detail:" in quiet


def test_quiet_lisbon_window_prompt_has_scene_richness_not_arms_out():
    """Quiet Lisbon confession: environmental richness, grounded pose, no arms-out."""
    story = _story(
        first_name="Elena",
        city="Lisbon",
        country="Portugal",
        location="Lisbon, Portugal",
        title="Second Draft",
        situation=(
            "Sitting by a rain-streaked apartment window at dusk in Lisbon, "
            "coat on the chair, notebook open, quiet contemplative moment."
        ),
        background="A writer rewriting the ending of her own life.",
        story_text=(
            "Rain on the window. The harbor lights below. She held the notebook "
            "and did not look at the camera."
        ),
        high_intensity=False,
    )
    detail = portrait_scene_detail(story)
    assert "Scene detail:" in detail
    assert "window" in detail.lower()
    assert "Lisbon" in detail

    prompt = build_portrait_only_prompt(story)
    assert "Scene detail:" in prompt
    assert "window" in prompt.lower()
    assert "rain" in prompt.lower() or "dusk" in prompt.lower()
    assert "at least two concrete background anchors" in prompt
    assert "practical light" in prompt
    assert "skin texture" in prompt
    assert "Physically ground the subject" in prompt
    assert "Do not default to a generic triumphant arms-out pose" in prompt
    assert "arms outstretched" not in prompt
    assert "triumphant arms-out / face-skyward pose is allowed" not in prompt


def test_subtitle_stays_within_torn_border_column():
    """Long taglines wrap/truncate to complete words that fit left of the photo."""
    long = "The hands that once trembled now rested"
    payload = story_cover.story_to_cover_template_payload(_story(hero_tagline=long))
    lines = [ln for ln in payload["subtitle"].split("\n") if ln]
    assert all(len(ln) <= story_cover.SUBTITLE_LINE_HARD_LIMIT for ln in lines)
    joined = " ".join(lines).lower()
    assert "hands" in joined
    assert "trembled" in joined
    # "now rested" may drop when the column is full — never mid-word.
    assert "trembl" not in joined.replace("trembled", "")


def test_dalle_flag_delegates_to_unchanged_dalle_path():
    story = _story()
    db = MagicMock()
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "dalle"):
        with patch("app.utils.story_image_prompt.try_generate_story_cover") as dalle:
            story_cover.try_generate_story_cover(
                db, story, image_prompt="prompt-x", force_rebuild=True
            )
            dalle.assert_called_once()
            kwargs = dalle.call_args.kwargs
            assert kwargs["image_prompt"] == "prompt-x"
            assert kwargs["force_rebuild"] is True


def test_template_flag_uses_portrait_then_playwright():
    story = _story()
    db = MagicMock()
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "template"):
        with patch.object(story_cover.settings, "OPENAI_API_KEY", "sk-test"):
            with patch(
                "app.utils.story_image_prompt.build_portrait_only_prompt",
                return_value="portrait only prompt",
            ) as build_p:
                with patch(
                    "app.utils.image_generator.generate_ai_cover_image",
                    return_value=("https://cdn/portrait.jpg", "images/portrait.jpg"),
                ) as dalle:
                    with patch(
                        "app.cover_template.render.render_cover_png_sync",
                        return_value=b"fake-png",
                    ) as render:
                        with patch(
                            "app.utils.s3.upload_image_to_s3",
                            return_value=("https://cdn/cover.png", "images/cover.png"),
                        ):
                            with patch("app.utils.s3.delete_s3_object") as delete_obj:
                                with patch(
                                    "app.utils.story_image_prompt.try_generate_story_cover"
                                ) as collage:
                                    story_cover.try_generate_story_cover(
                                        db, story, image_prompt="ignored-collage"
                                    )
                                    build_p.assert_called_once()
                                    dalle.assert_called_once()
                                    assert (
                                        dalle.call_args.kwargs["image_prompt"]
                                        == "portrait only prompt"
                                    )
                                    render.assert_called_once()
                                    payload = render.call_args.args[0]
                                    assert (
                                        payload["photo_url"]
                                        == "https://cdn/portrait.jpg"
                                    )
                                    collage.assert_not_called()
                                    assert story.image_source == ImageSource.template_v1
                                    assert any(
                                        c.args and c.args[0] == "images/portrait.jpg"
                                        for c in delete_obj.call_args_list
                                    )


def test_template_flag_meditation_falls_back_to_dalle():
    story = _story(story_type=StoryType.meditation)
    db = MagicMock()
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "template"):
        with patch("app.utils.story_image_prompt.try_generate_story_cover") as dalle:
            story_cover.try_generate_story_cover(db, story, image_prompt=None)
            dalle.assert_called_once()


def test_member_upload_guard_skips_both_pipelines():
    story = _story(
        image_source=ImageSource.user_uploaded,
        cover_image_url="https://cdn/member.jpg",
    )
    db = MagicMock()
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "template"):
        with patch(
            "app.cover_template.render.render_cover_png_sync"
        ) as render:
            with patch("app.utils.story_image_prompt.try_generate_story_cover") as dalle:
                story_cover.try_generate_story_cover(
                    db, story, image_prompt=None, replace_member_cover=False
                )
                render.assert_not_called()
                dalle.assert_not_called()
