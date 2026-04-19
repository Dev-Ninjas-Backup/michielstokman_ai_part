"""
app/api/v1/endpoints/admin/route_liberation_admin.py

Admin endpoints for managing liberation definitions:
  - Bulk creation (auto-approved)
  - Review queue (approve / reject user submissions)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.model.user import User
from app.data import liberation_catalog as catalog_data
from app.schemas.schema_liberation_catalog import (
    CreateLiberationRequest,
    BulkCreateLiberationRequest,
    ReviewLiberationRequest,
    LiberationDefinitionResponse,
    LiberationCatalogListResponse,
    LiberationReviewResponse,
    DayThemeItem,
)

router = APIRouter()


# ── Helper ──────────────────────────────────────────────────────────────────

def _definition_to_response(d) -> LiberationDefinitionResponse:
    return LiberationDefinitionResponse(
        id=d.id,
        journey_code=d.journey_code,
        title=d.title,
        description=d.description,
        total_days=d.total_days,
        price_cents=d.price_cents,
        currency=d.currency,
        is_admin_created=d.is_admin_created,
        moderation_status=d.moderation_status.value,
        moderation_notes=d.moderation_notes,
        is_active=d.is_active,
        created_at=d.created_at,
        day_themes=[
            DayThemeItem(day_number=dd.day_number, day_theme=dd.day_theme)
            for dd in d.day_definitions
        ],
    )


# ── Admin: single creation (auto-approved) ─────────────────────────────────

@router.post(
    "/admin/liberation/create",
    response_model=LiberationDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: create a single liberation (auto-approved)",
)
def admin_create_liberation(
    payload: CreateLiberationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    if len(payload.day_themes) != payload.total_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"day_themes length ({len(payload.day_themes)}) must equal total_days ({payload.total_days}).",
        )

    existing = catalog_data.get_definition_by_code(db, payload.journey_code)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A liberation with code '{payload.journey_code}' already exists.",
        )

    definition = catalog_data.create_definition(
        db=db,
        journey_code=payload.journey_code,
        title=payload.title,
        description=payload.description,
        total_days=payload.total_days,
        price_cents=payload.price_cents,
        currency=payload.currency,
        created_by=current_user.id,
        is_admin_created=True,
        day_themes=payload.day_themes,
    )
    return _definition_to_response(definition)


# ── Admin: bulk creation (auto-approved) ────────────────────────────────────

@router.post(
    "/admin/liberation/bulk-create",
    response_model=list[LiberationDefinitionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Admin: create multiple liberations at once",
)
def admin_bulk_create_liberations(
    payload: BulkCreateLiberationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    results = []
    for item in payload.definitions:
        if len(item.day_themes) != item.total_days:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"[{item.journey_code}] day_themes length ({len(item.day_themes)}) must equal total_days ({item.total_days}).",
            )
        existing = catalog_data.get_definition_by_code(db, item.journey_code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A liberation with code '{item.journey_code}' already exists.",
            )

        definition = catalog_data.create_definition(
            db=db,
            journey_code=item.journey_code,
            title=item.title,
            description=item.description,
            total_days=item.total_days,
            price_cents=item.price_cents,
            currency=item.currency,
            created_by=current_user.id,
            is_admin_created=True,
            day_themes=item.day_themes,
        )
        results.append(_definition_to_response(definition))

    return results


# ── Admin: review queue ─────────────────────────────────────────────────────

@router.get(
    "/admin/liberation/pending",
    response_model=LiberationCatalogListResponse,
    summary="Admin: list pending liberation submissions",
)
def admin_list_pending(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    definitions = catalog_data.list_pending_definitions(db, limit=limit, offset=offset)
    total = catalog_data.count_pending_definitions(db)
    items = [_definition_to_response(d) for d in definitions]
    return LiberationCatalogListResponse(definitions=items, total=total)


# ── Admin: approve or reject ────────────────────────────────────────────────

@router.post(
    "/admin/liberation/{definition_id}/review",
    response_model=LiberationReviewResponse,
    summary="Admin: approve or reject a liberation submission",
)
def admin_review_liberation(
    definition_id: str,
    payload: ReviewLiberationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    definition = catalog_data.get_definition_by_id(db, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Liberation definition not found.")

    if payload.action == "approve":
        catalog_data.approve_definition(db, definition, reviewer_id=current_user.id)
        return LiberationReviewResponse(
            message="Liberation approved and is now live.",
            definition_id=definition.id,
            status="approved",
        )
    else:
        catalog_data.reject_definition(db, definition, reviewer_id=current_user.id, notes=payload.notes)
        return LiberationReviewResponse(
            message="Liberation rejected.",
            definition_id=definition.id,
            status="rejected",
        )


# ── Admin: deactivate ──────────────────────────────────────────────────────

@router.post(
    "/admin/liberation/{definition_id}/deactivate",
    response_model=LiberationReviewResponse,
    summary="Admin: deactivate a liberation (remove from storefront)",
)
def admin_deactivate_liberation(
    definition_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    definition = catalog_data.get_definition_by_id(db, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Liberation definition not found.")

    catalog_data.deactivate_definition(db, definition)
    return LiberationReviewResponse(
        message="Liberation deactivated.",
        definition_id=definition.id,
        status="deactivated",
    )
