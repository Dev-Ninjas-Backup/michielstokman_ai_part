"""Contracts for the publications dashboard.

A publication is one record made of three assets — written content, story card
and voice. These tests pin the rules the dashboard depends on: how the overall
status is derived, when publishing is allowed, and that the author's contact
details stay out of every public response.
"""
from datetime import datetime, timezone

# Relationships are declared by class name, so every model has to be imported
# before the mappers can be configured and a Story instantiated. Same list as
# alembic/env.py.
from app.model.billing import (  # noqa: F401
    PaymentTransaction,
    SubscriptionPlan,
    UserSubscription,
)
from app.model.cover_image import CoverImage  # noqa: F401
from app.model.credit import UserCredit  # noqa: F401
from app.model.feedback import StoryFeedback  # noqa: F401
from app.model.guest_session import GuestSession  # noqa: F401
from app.model.liberation import UserJourney, UserJourneyStep  # noqa: F401
from app.model.profile import UserProfile  # noqa: F401
from app.model.user import User, UserOAuthAccount  # noqa: F401

from app.data import story as story_data
from app.model.story import AssetReviewStatus, ModerationStatus, Story
from app.schemas.schema_story import (
    StoryDetailResponse,
    StoryDetailUserResponse,
    StoryListItemResponse,
)


def make_story(**overrides) -> Story:
    """A story with every asset approved, so each test can spoil one thing."""
    story = Story()
    story.moderation_status = ModerationStatus.pending
    story.content_status = AssetReviewStatus.approved
    story.cover_status = AssetReviewStatus.approved
    story.voice_status = AssetReviewStatus.approved
    story.voice_not_required = False
    story.published_at = None
    for key, value in overrides.items():
        setattr(story, key, value)
    return story


# ---------------------------------------------------------------------------
# Overall status
# ---------------------------------------------------------------------------

def test_all_assets_approved_is_ready_for_review():
    assert story_data.publication_status(make_story()) == "ready_for_review"


def test_voice_is_skipped_when_not_required():
    story = make_story(
        voice_status=AssetReviewStatus.missing,
        voice_not_required=True,
    )
    assert story_data.publication_status(story) == "ready_for_review"


def test_a_missing_asset_wins_over_in_progress():
    story = make_story(
        cover_status=AssetReviewStatus.missing,
        voice_status=AssetReviewStatus.in_progress,
    )
    assert story_data.publication_status(story) == "missing"


def test_partial_progress_reads_as_in_progress():
    story = make_story(voice_status=AssetReviewStatus.ready_for_review)
    assert story_data.publication_status(story) == "in_progress"


def test_published_at_wins_over_asset_statuses():
    story = make_story(
        content_status=AssetReviewStatus.pending,
        published_at=datetime.now(timezone.utc),
    )
    assert story_data.publication_status(story) == "published"


def test_rejection_wins_over_everything():
    story = make_story(
        moderation_status=ModerationStatus.rejected,
        published_at=datetime.now(timezone.utc),
    )
    assert story_data.publication_status(story) == "rejected"


# ---------------------------------------------------------------------------
# Publish gating
# ---------------------------------------------------------------------------

def test_fully_approved_story_has_no_blockers():
    assert story_data.publish_blockers(make_story()) == []


def test_each_unapproved_asset_is_named_as_a_blocker():
    story = make_story(
        content_status=AssetReviewStatus.ready_for_review,
        cover_status=AssetReviewStatus.missing,
        voice_status=AssetReviewStatus.pending,
    )
    blockers = story_data.publish_blockers(story)
    assert len(blockers) == 3
    joined = " ".join(blockers).lower()
    assert "written content" in joined
    assert "story card" in joined
    assert "voice" in joined


def test_missing_voice_does_not_block_when_not_required():
    story = make_story(
        voice_status=AssetReviewStatus.missing,
        voice_not_required=True,
    )
    assert story_data.publish_blockers(story) == []


def test_already_published_story_cannot_be_published_again():
    story = make_story(published_at=datetime.now(timezone.utc))
    assert story_data.publish_blockers(story) == ["Already published"]


# ---------------------------------------------------------------------------
# The SQL twin must agree with the Python derivation
# ---------------------------------------------------------------------------

def test_sql_status_expression_covers_every_rung():
    rendered = str(
        story_data.publication_status_expr().compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    for rung in (
        "rejected",
        "published",
        "ready_for_review",
        "missing",
        "in_progress",
        "pending",
    ):
        assert rung in rendered


def test_missing_filter_maps_to_real_columns():
    for field in story_data.ASSET_FIELDS.values():
        assert field in Story.__table__.columns


# ---------------------------------------------------------------------------
# Contact details are admin-only
# ---------------------------------------------------------------------------

def test_admin_detail_carries_contact_and_city_country():
    fields = StoryDetailResponse.model_fields
    assert "contact" in fields
    assert "city" in fields
    assert "country" in fields
    assert "publish_blockers" in fields


def test_public_story_response_exposes_no_contact_details():
    fields = set(StoryDetailUserResponse.model_fields)
    assert "contact" not in fields
    assert "email" not in fields
    assert "true_name" not in fields


def test_queue_row_describes_the_whole_publication():
    fields = StoryListItemResponse.model_fields
    for field in (
        "first_name",
        "content_status",
        "cover_status",
        "voice_status",
        "voice_not_required",
        "publication_status",
        "has_text",
        "audio_path",
        "submitted_at",
        "updated_at",
    ):
        assert field in fields


def test_story_model_declares_city_and_country():
    assert "city" in Story.__table__.columns
    assert "country" in Story.__table__.columns


def test_split_location_uses_the_last_comma():
    from app.utils.location import join_location, split_location

    assert split_location("Amsterdam, Netherlands") == ("Amsterdam", "Netherlands")
    assert split_location("Brooklyn, New York, USA") == ("Brooklyn, New York", "USA")
    assert split_location("Lisbon") == ("Lisbon", None)
    assert split_location("  ") == (None, None)
    assert join_location("Amsterdam", "Netherlands") == "Amsterdam, Netherlands"
    assert join_location("Lisbon", None) == "Lisbon"
    assert join_location("", "") is None
