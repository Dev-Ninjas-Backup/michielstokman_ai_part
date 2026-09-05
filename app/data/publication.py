"""Admin publications overview: one row per Confession or Meditation."""
from sqlalchemy.orm import Session, joinedload

from app.model.story import Story, StoryType, SubmissionStatus
from app.model.user import User
from app.utils.publication_status import (
    asset_status,
    overall_publication_status,
    public_author_name,
)

STATUSES = (
    "missing",
    "pending",
    "in_progress",
    "ready_for_review",
    "ready_to_publish",
    "published",
    "rejected",
)


def list_publications(
    db: Session,
    *,
    search: str | None = None,
    story_type: str | None = None,
    publication_status: str | None = None,
    missing: str | None = None,
    sort: str = "submitted_at",
    limit: int = 10,
    offset: int = 0,
):
    query = (
        db.query(Story)
        .options(joinedload(Story.user).joinedload(User.profile))
        .filter(Story.story_type.in_([StoryType.confession, StoryType.meditation]))
        .filter(Story.submission_status == SubmissionStatus.submitted)
    )
    if story_type in ("confession", "meditation"):
        query = query.filter(Story.story_type == story_type)

    rows = query.all()
    if search and search.strip():
        needle = search.strip().lower()
        rows = [
            story
            for story in rows
            if needle in (story.title or "").lower()
            or needle in (public_author_name(story) or "").lower()
        ]

    stats = {key: 0 for key in ("all", *STATUSES)}
    stats["all"] = len(rows)
    decorated = []
    for story in rows:
        status = overall_publication_status(story)
        stats[status] = stats.get(status, 0) + 1
        decorated.append((story, status))

    filtered = decorated
    if publication_status and publication_status != "all":
        filtered = [(story, status) for story, status in filtered if status == publication_status]

    if missing in ("text", "cover", "voice"):
        component = "content" if missing == "text" else missing
        filtered = [
            (story, status)
            for story, status in filtered
            if asset_status(story, component) == "missing"
        ]

    reverse = True
    if sort == "updated_at":
        filtered.sort(key=lambda pair: pair[0].updated_at or pair[0].created_at, reverse=reverse)
    else:
        filtered.sort(key=lambda pair: pair[0].created_at, reverse=reverse)

    total = len(filtered)
    page_rows = [story for story, _ in filtered[offset : offset + limit]]
    return page_rows, total, stats
