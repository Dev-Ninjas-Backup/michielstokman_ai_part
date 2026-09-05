"""Pure review/readiness calculations for the publications workspace."""
from datetime import datetime, timezone

from app.model.story import AssetReviewStatus, ModerationStatus


def enum_value(value):
    return getattr(value, "value", value)


def _has_text(value) -> bool:
    return bool(value and str(value).strip())


def public_author_name(story) -> str | None:
    name = (story.first_name or "").strip()
    if not name or "@" in name:
        return None
    return name


def _asset_present(story, component: str) -> bool:
    if component == "content":
        return _has_text(story.story_text)
    if component == "cover":
        return _has_text(story.cover_image_url)
    return _has_text(story.audio_path)


def asset_status(story, component: str) -> str:
    if component == "voice" and story.voice_not_required:
        stored = enum_value(getattr(story, "voice_status", None))
        return "rejected" if stored == "rejected" else "approved"

    stored = enum_value(getattr(story, f"{component}_status", None))
    if not _asset_present(story, component):
        if component == "content" and enum_value(story.generation_status) == "processing":
            return "in_progress"
        return "missing"
    if stored in {
        "pending",
        "in_progress",
        "ready_for_review",
        "approved",
        "rejected",
    }:
        return stored
    return "ready_for_review"


def publish_blockers(story) -> list[str]:
    blockers = []
    if asset_status(story, "content") != "approved":
        blockers.append("content")
    if asset_status(story, "cover") != "approved":
        blockers.append("cover")
    if asset_status(story, "voice") != "approved" and not story.voice_not_required:
        blockers.append("voice")
    return blockers


def can_publish(story) -> bool:
    return not publish_blockers(story) and story.published_at is None


def overall_publication_status(story) -> str:
    if story.published_at is not None:
        return "published"
    content = asset_status(story, "content")
    cover = asset_status(story, "cover")
    voice = asset_status(story, "voice")
    states = [content, cover, voice]
    if "rejected" in states:
        return "rejected"
    if can_publish(story):
        return "ready_to_publish"
    if "in_progress" in states:
        return "in_progress"
    if "missing" in states:
        return "missing"
    if "ready_for_review" in states:
        return "ready_for_review"
    return "pending"


def _unpublish(story) -> None:
    if story.published_at is None:
        return
    story.published_at = None
    if enum_value(story.moderation_status) == "approved":
        story.moderation_status = ModerationStatus.pending


def refresh_asset_statuses(
    story,
    force_content: bool = False,
    force_cover: bool = False,
    force_voice: bool = False,
) -> None:
    """Reset review state when an asset actually changed. Live items drop until Publish."""
    changed = False
    if force_content:
        if enum_value(story.generation_status) == "processing":
            story.content_status = AssetReviewStatus.in_progress
        elif _has_text(story.story_text):
            story.content_status = AssetReviewStatus.ready_for_review
        else:
            story.content_status = AssetReviewStatus.missing
        changed = True
    if force_cover:
        story.cover_status = (
            AssetReviewStatus.ready_for_review
            if _has_text(story.cover_image_url)
            else AssetReviewStatus.missing
        )
        changed = True
    if force_voice:
        story.voice_not_required = False
        story.voice_status = (
            AssetReviewStatus.ready_for_review
            if _has_text(story.audio_path)
            else AssetReviewStatus.missing
        )
        changed = True
    if changed:
        _unpublish(story)


def utcnow():
    return datetime.now(timezone.utc)
