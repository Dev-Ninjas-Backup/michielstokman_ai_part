"""Admin user list / patch / hard-delete cascade wipe."""
from __future__ import annotations

import logging
import math
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.data import story as story_data
from app.data import user as user_data
from app.model.billing import SubscriptionStatus, UserSubscription
from app.model.cover_image import CoverImage
from app.model.credit import UserCredit
from app.model.liberation import LiberationDefinition, UserJourney
from app.model.profile import UserProfile
from app.model.story import Story
from app.model.user import User
from app.schemas.schema_admin_users import (
    AdminUserDetail,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserProfileSummary,
)
from app.schemas.schema_system import PaginationMeta

logger = logging.getLogger(__name__)


class AdminUserError(HTTPException):
    """Domain error already shaped as an HTTPException."""


def _display_name(user: User) -> Optional[str]:
    profile = getattr(user, "profile", None)
    if profile and profile.true_name and str(profile.true_name).strip():
        return profile.true_name.strip()
    return None


def _story_count_subquery(db: Session):
    return (
        db.query(Story.user_id, func.count(Story.id).label("story_count"))
        .group_by(Story.user_id)
        .subquery()
    )


def count_admins(db: Session) -> int:
    return db.query(User).filter(User.is_admin.is_(True)).count()


def list_users(
    db: Session,
    *,
    q: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_admin: Optional[bool] = None,
    page: int = 1,
    limit: int = 20,
) -> AdminUserListResponse:
    page = max(1, page)
    limit = min(max(1, limit), 100)
    offset = (page - 1) * limit

    counts = _story_count_subquery(db)
    query = (
        db.query(User, func.coalesce(counts.c.story_count, 0).label("story_count"))
        .outerjoin(counts, counts.c.user_id == User.id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .options(joinedload(User.profile))
    )

    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                User.email.ilike(term),
                UserProfile.true_name.ilike(term),
            )
        )
    if is_active is not None:
        query = query.filter(User.is_active.is_(is_active))
    if is_admin is not None:
        query = query.filter(User.is_admin.is_(is_admin))

    total = query.order_by(None).count()
    rows = (
        query.order_by(User.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    users = [
        AdminUserListItem(
            id=user.id,
            email=user.email,
            display_name=_display_name(user),
            is_active=user.is_active,
            is_admin=user.is_admin,
            is_verified=user.is_verified,
            story_count=int(story_count or 0),
            created_at=user.created_at,
            last_login=user.last_login,
        )
        for user, story_count in rows
    ]
    total_pages = math.ceil(total / limit) if limit else 1
    return AdminUserListResponse(
        users=users,
        meta=PaginationMeta(
            total=total,
            page=page,
            limit=limit,
            totalPages=total_pages,
        ),
    )


def get_user_detail(db: Session, user_id: UUID) -> AdminUserDetail:
    user = (
        db.query(User)
        .options(joinedload(User.profile))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        raise AdminUserError(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    story_count = (
        db.query(func.count(Story.id)).filter(Story.user_id == user.id).scalar() or 0
    )
    credits = (
        db.query(UserCredit).filter(UserCredit.user_id == user.id).first()
    )
    has_sub = (
        db.query(UserSubscription.id)
        .filter(
            UserSubscription.user_id == user.id,
            UserSubscription.status == SubscriptionStatus.active,
        )
        .first()
        is not None
    )
    profile = None
    if user.profile:
        profile = AdminUserProfileSummary(
            true_name=user.profile.true_name,
            city=user.profile.city,
            country=user.profile.country,
            gender=user.profile.gender,
            profile_image_url=user.profile.profile_image_url,
        )

    return AdminUserDetail(
        id=user.id,
        email=user.email,
        display_name=_display_name(user),
        is_active=user.is_active,
        is_admin=user.is_admin,
        is_verified=user.is_verified,
        is_profile_setup=user.is_profile_setup,
        token_version=user.token_version,
        created_at=user.created_at,
        last_login=user.last_login,
        story_count=int(story_count),
        profile=profile,
        credits_remaining=credits.daily_credits_remaining if credits else None,
        has_active_subscription=has_sub,
    )


def patch_user(
    db: Session,
    *,
    actor: User,
    user_id: UUID,
    is_active: Optional[bool] = None,
    is_admin: Optional[bool] = None,
) -> AdminUserDetail:
    if is_active is None and is_admin is None:
        raise AdminUserError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide is_active and/or is_admin",
        )

    user = user_data.get_user_by_id(db, str(user_id))
    if not user:
        raise AdminUserError(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.id == actor.id:
        if is_active is False:
            raise AdminUserError(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot ban yourself",
            )
        if is_admin is False:
            raise AdminUserError(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot demote yourself",
            )

    if is_admin is False and user.is_admin and count_admins(db) <= 1:
        raise AdminUserError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot demote the last remaining admin",
        )

    changed = False
    if is_active is not None and user.is_active != is_active:
        user.is_active = is_active
        changed = True
    if is_admin is not None and user.is_admin != is_admin:
        user.is_admin = is_admin
        changed = True

    if changed:
        user.token_version = (user.token_version or 1) + 1
        db.commit()
        db.refresh(user)

    return get_user_detail(db, user.id)


def delete_user(db: Session, *, actor: User, user_id: UUID) -> tuple[UUID, int]:
    """Hard-delete a user and wipe their owned stories + related rows."""
    if actor.id == user_id:
        raise AdminUserError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete yourself",
        )

    user = user_data.get_user_by_id(db, str(user_id))
    if not user:
        raise AdminUserError(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.is_admin and count_admins(db) <= 1:
        raise AdminUserError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete the last remaining admin",
        )

    # 1. Wipe owned stories (media + feedback via delete_story)
    owned_ids = [
        row[0]
        for row in db.query(Story.id).filter(Story.user_id == user.id).all()
    ]
    stories_deleted = 0
    for story_id in owned_ids:
        story = db.query(Story).filter(Story.id == story_id).first()
        if story is None:
            continue
        story_data.delete_story(db, story)
        stories_deleted += 1

    # Re-load after nested commits inside delete_story
    user = user_data.get_user_by_id(db, str(user_id))
    if not user:
        return user_id, stories_deleted

    # Clear moderation pointers on other users' stories
    db.query(Story).filter(Story.admin_id == user.id).update(
        {Story.admin_id: None}, synchronize_session=False
    )
    db.query(Story).filter(Story.moderation_reviewed_by == user.id).update(
        {Story.moderation_reviewed_by: None}, synchronize_session=False
    )

    # 2. Journeys (steps cascade via ORM orphan)
    journeys = db.query(UserJourney).filter(UserJourney.user_id == user.id).all()
    for journey in journeys:
        db.delete(journey)

    # 3. Shared catalog refs — keep products, clear pointers
    db.query(LiberationDefinition).filter(
        LiberationDefinition.created_by == user.id
    ).update({LiberationDefinition.created_by: None}, synchronize_session=False)
    db.query(LiberationDefinition).filter(
        LiberationDefinition.reviewed_by == user.id
    ).update({LiberationDefinition.reviewed_by: None}, synchronize_session=False)
    db.query(CoverImage).filter(CoverImage.uploaded_by == user.id).update(
        {CoverImage.uploaded_by: None}, synchronize_session=False
    )

    # 4. Avatar best-effort (profile row cascades with the user)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile and profile.profile_image_url:
        try:
            from app.utils.s3 import delete_s3_object
            from urllib.parse import urlparse

            key = urlparse(profile.profile_image_url).path.lstrip("/")
            if key:
                delete_s3_object(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not delete avatar for user %s: %s", user.id, exc)

    deleted_id = user.id
    db.delete(user)
    db.commit()
    return deleted_id, stories_deleted
