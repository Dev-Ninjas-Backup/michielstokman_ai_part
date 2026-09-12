"""Admin cover regen must commit new URL before refresh (avoid 404)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.api.v1.endpoints.admin import route_moderation as mod
from app.model.story import AssetReviewStatus, ImageSource


def test_regenerate_cover_worker_commits_new_url_before_refresh():
    """Regression: refresh-before-commit discarded the new cover and 404'd the old file."""
    story = SimpleNamespace(
        id="story-1",
        cover_image_url="media/images/old.png",
        cover_image_key="local/old.png",
        cover_status=AssetReviewStatus.in_progress,
        image_source=ImageSource.ai_generated,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = story

    persisted = {"url": story.cover_image_url, "key": story.cover_image_key}
    call_order: list[str] = []

    def _generate(_db, s, **_kwargs):
        s.cover_image_url = "media/images/new.png"
        s.cover_image_key = "local/new.png"
        s.image_source = ImageSource.template_v1

    def _commit():
        call_order.append("commit")
        persisted["url"] = story.cover_image_url
        persisted["key"] = story.cover_image_key

    def _refresh(_story):
        call_order.append("refresh")
        # After a real commit, refresh reloads the saved row — not the pre-regen URL.
        _story.cover_image_url = persisted["url"]
        _story.cover_image_key = persisted["key"]

    db.commit.side_effect = _commit
    db.refresh.side_effect = _refresh

    with patch("app.core.db.SessionLocal", return_value=db):
        with patch(
            "app.utils.story_cover.try_generate_story_cover",
            side_effect=_generate,
        ):
            mod._regenerate_cover_worker("story-1")

    assert call_order == ["commit", "refresh"]
    assert story.cover_image_url == "media/images/new.png"
    assert story.cover_status == AssetReviewStatus.ready_for_review
    assert persisted["url"] == "media/images/new.png"
