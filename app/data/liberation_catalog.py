"""
app/data/liberation_catalog.py

Data-access layer for the Liberation Journey product catalog.
Pure DB operations — no business logic or HTTP concerns.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.model.liberation import (
    DefinitionStatus,
    LiberationDefinition,
    LiberationDayDefinition,
)
from app.schemas.schema_liberation_catalog import DayDefinitionInput


# ── Definition CRUD ─────────────────────────────────────────────────────────

def get_definition_by_code(db: Session, journey_code: str) -> Optional[LiberationDefinition]:
    return (
        db.query(LiberationDefinition)
        .filter(LiberationDefinition.journey_code == journey_code)
        .first()
    )


def get_definition_by_id(db: Session, definition_id: UUID) -> Optional[LiberationDefinition]:
    return db.query(LiberationDefinition).filter(LiberationDefinition.id == definition_id).first()


def list_approved_definitions(db: Session, limit: int = 50, offset: int = 0) -> list[LiberationDefinition]:
    """Return all active & approved definitions (the public storefront)."""
    return (
        db.query(LiberationDefinition)
        .filter(
            LiberationDefinition.moderation_status == DefinitionStatus.approved,
            LiberationDefinition.is_active.is_(True),
        )
        .order_by(LiberationDefinition.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def list_pending_definitions(db: Session, limit: int = 50, offset: int = 0) -> list[LiberationDefinition]:
    """Return definitions waiting for admin review."""
    return (
        db.query(LiberationDefinition)
        .filter(LiberationDefinition.moderation_status == DefinitionStatus.pending)
        .order_by(LiberationDefinition.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def list_all_definitions(db: Session, limit: int = 50, offset: int = 0) -> list[LiberationDefinition]:
    """Return ALL definitions for the admin dashboard."""
    return (
        db.query(LiberationDefinition)
        .order_by(LiberationDefinition.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_all_definitions(db: Session) -> int:
    return db.query(LiberationDefinition).count()


def count_pending_definitions(db: Session) -> int:
    return (
        db.query(LiberationDefinition)
        .filter(LiberationDefinition.moderation_status == DefinitionStatus.pending)
        .count()
    )


def create_definition(
    db: Session,
    journey_code: str,
    title: str,
    description: str,
    total_days: int,
    price_cents: int,
    currency: str,
    created_by: UUID,
    is_admin_created: bool,
    days: list[DayDefinitionInput],
    rating: Optional[float] = None,
    what_to_expect: Optional[list] = None,
    setup_instructions: Optional[list] = None,
) -> LiberationDefinition:
    """
    Create a new liberation definition together with its day-theme rows.
    Admin-created definitions are auto-approved; user submissions start as pending.
    """
    definition = LiberationDefinition(
        journey_code=journey_code,
        title=title,
        description=description,
        total_days=total_days,
        price_cents=price_cents,
        currency=currency,
        created_by=created_by,
        is_admin_created=is_admin_created,
        moderation_status=(
            DefinitionStatus.approved if is_admin_created else DefinitionStatus.pending
        ),
        rating=rating,
        what_to_expect=what_to_expect,
        setup_instructions=setup_instructions,
    )
    db.add(definition)
    db.flush()  # get definition.id

    for day_def_input in days:
        day_def = LiberationDayDefinition(
            definition_id=definition.id,
            day_number=day_def_input.day,
            day_theme=day_def_input.title,
            exercise_text=day_def_input.exercise_text,
            why_text=day_def_input.why_text,
        )
        db.add(day_def)

    db.commit()
    db.refresh(definition)
    return definition


# ── Moderation ──────────────────────────────────────────────────────────────

def approve_definition(
    db: Session,
    definition: LiberationDefinition,
    reviewer_id: UUID,
) -> LiberationDefinition:
    definition.moderation_status = DefinitionStatus.approved
    definition.reviewed_by = reviewer_id
    definition.reviewed_at = datetime.now(timezone.utc)
    definition.moderation_notes = None
    db.commit()
    db.refresh(definition)
    return definition


def reject_definition(
    db: Session,
    definition: LiberationDefinition,
    reviewer_id: UUID,
    notes: Optional[str] = None,
) -> LiberationDefinition:
    definition.moderation_status = DefinitionStatus.rejected
    definition.reviewed_by = reviewer_id
    definition.reviewed_at = datetime.now(timezone.utc)
    definition.moderation_notes = notes
    db.commit()
    db.refresh(definition)
    return definition


def deactivate_definition(db: Session, definition: LiberationDefinition) -> LiberationDefinition:
    definition.is_active = False
    db.commit()
    db.refresh(definition)
    return definition
