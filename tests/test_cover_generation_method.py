"""Tests for COVER_GENERATION_METHOD routing (dalle default vs template)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.model.story import ImageSource, StoryType
from app.utils import story_cover


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
    assert payload["title"] == "To Wasteland On My Own"


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


def test_template_flag_renders_and_sets_template_v1_source():
    story = _story()
    db = MagicMock()
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "template"):
        with patch(
            "app.cover_template.render.render_cover_png_sync",
            return_value=b"fake-png",
        ) as render:
            with patch(
                "app.utils.s3.upload_image_to_s3",
                return_value=("https://cdn/x.png", "images/x.png"),
            ):
                with patch("app.utils.s3.delete_s3_object"):
                    with patch(
                        "app.utils.story_image_prompt.try_generate_story_cover"
                    ) as dalle:
                        story_cover.try_generate_story_cover(
                            db, story, image_prompt="ignored"
                        )
                        render.assert_called_once()
                        dalle.assert_not_called()
                        assert story.image_source == ImageSource.template_v1
                        assert story.cover_image_url == "https://cdn/x.png"


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
