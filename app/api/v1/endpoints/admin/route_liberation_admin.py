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
from app.core.responses import ApiResponse, success_response
from app.model.user import User
from app.data import liberation_catalog as catalog_data
from app.schemas.schema_liberation_catalog import (
    CreateLiberationRequest,
    UpdateLiberationRequest,
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
        cover_image_url=d.cover_image_url,
        rating=d.rating,
        what_to_expect=d.what_to_expect or [],
        setup_instructions=d.setup_instructions or [],
        days=[
            DayThemeItem(
                day_number=dd.day_number, 
                day_theme=dd.day_theme,
                exercise_text=dd.exercise_text,
                why_text=dd.why_text
            )
            for dd in d.day_definitions
        ],
    )


# ── Admin: single creation (auto-approved) ─────────────────────────────────

@router.post(
    "/admin/liberation/create",
    response_model=ApiResponse[LiberationDefinitionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Admin: create a single liberation (auto-approved)",
)
def admin_create_liberation(
    payload: CreateLiberationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    if len(payload.days) != payload.total_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"days length ({len(payload.days)}) must equal total_days ({payload.total_days}).",
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
        days=payload.days,
        rating=payload.rating,
        what_to_expect=payload.what_to_expect,
        setup_instructions=payload.setup_instructions,
    )
    result = _definition_to_response(definition)
    return success_response("Liberation created successfully", status.HTTP_201_CREATED, result)


# ── Admin: bulk creation (auto-approved) ────────────────────────────────────

@router.post(
    "/admin/liberation/bulk-create",
    response_model=ApiResponse[list[LiberationDefinitionResponse]],
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
        if len(item.days) != item.total_days:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"[{item.journey_code}] days length ({len(item.days)}) must equal total_days ({item.total_days}).",
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
            days=item.days,
            rating=item.rating,
            what_to_expect=item.what_to_expect,
            setup_instructions=item.setup_instructions,
        )
        results.append(_definition_to_response(definition))

    return success_response(
        f"{len(results)} liberation(s) created successfully",
        status.HTTP_201_CREATED,
        results,
    )


# ── Admin: review queue ─────────────────────────────────────────────────────

@router.get(
    "/admin/liberation/pending",
    response_model=ApiResponse[LiberationCatalogListResponse],
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
    result = LiberationCatalogListResponse(definitions=items, total=total)
    return success_response("Pending liberations fetched", status.HTTP_200_OK, result)


# ── Admin: approve or reject ────────────────────────────────────────────────

@router.post(
    "/admin/liberation/{definition_id}/review",
    response_model=ApiResponse[LiberationReviewResponse],
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
        result = LiberationReviewResponse(
            message="Liberation approved and is now live.",
            definition_id=definition.id,
            status="approved",
        )
        return success_response("Liberation approved", status.HTTP_200_OK, result)
    else:
        catalog_data.reject_definition(db, definition, reviewer_id=current_user.id, notes=payload.notes)
        result = LiberationReviewResponse(
            message="Liberation rejected.",
            definition_id=definition.id,
            status="rejected",
        )
        return success_response("Liberation rejected", status.HTTP_200_OK, result)


# ── Admin: deactivate ──────────────────────────────────────────────────────

@router.post(
    "/admin/liberation/{definition_id}/deactivate",
    response_model=ApiResponse[LiberationReviewResponse],
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
    result = LiberationReviewResponse(
        message="Liberation deactivated.",
        definition_id=definition.id,
        status="deactivated",
    )
    return success_response("Liberation deactivated", status.HTTP_200_OK, result)


@router.patch(
    "/admin/liberation/{definition_id}",
    response_model=ApiResponse[LiberationDefinitionResponse],
    summary="Admin: update an existing liberation journey",
)
def admin_update_liberation(
    definition_id: str,
    payload: UpdateLiberationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    definition = catalog_data.get_definition_by_id(db, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Liberation definition not found.")

    # 1. Update basic fields
    if payload.title is not None: definition.title = payload.title
    if payload.description is not None: definition.description = payload.description
    if payload.price_cents is not None: definition.price_cents = payload.price_cents
    if payload.currency is not None: definition.currency = payload.currency
    if payload.cover_image_url is not None: definition.cover_image_url = payload.cover_image_url
    if payload.is_active is not None: definition.is_active = payload.is_active
    if payload.rating is not None: definition.rating = payload.rating
    if payload.what_to_expect is not None: definition.what_to_expect = payload.what_to_expect
    if payload.setup_instructions is not None: definition.setup_instructions = payload.setup_instructions

    # 2. Update day themes if provided
    if payload.days is not None:
        if len(payload.days) != definition.total_days:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"days length ({len(payload.days)}) must equal total_days ({definition.total_days}).",
            )
        
        # Delete old days and insert new ones
        from app.model.liberation import LiberationDayDefinition
        db.query(LiberationDayDefinition).filter(LiberationDayDefinition.definition_id == definition.id).delete()
        for i, day_def_input in enumerate(payload.days):
            db.add(LiberationDayDefinition(
                definition_id=definition.id,
                day_number=i+1,
                day_theme=day_def_input.title,
                exercise_text=day_def_input.exercise_text,
                why_text=day_def_input.why_text
            ))

    db.commit()
    db.refresh(definition)
    
    return success_response("Liberation updated successfully", status.HTTP_200_OK, _definition_to_response(definition))
