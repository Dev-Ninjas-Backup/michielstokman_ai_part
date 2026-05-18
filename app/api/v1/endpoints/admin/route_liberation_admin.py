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
from app.utils.slug import generate_slug
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
    SetLiberationActiveRequest,
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
        price=d.price_cents / 100.0,
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
    tags=["Liberation Admin"],
)
def admin_create_liberation(
    payload: CreateLiberationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    # 1. Generate unique journey_code from title
    j_code = generate_slug(payload.title)
    
    # 2. Sync price/price_cents if price is provided
    final_price_cents = payload.price_cents
    if payload.price is not None:
        final_price_cents = int(payload.price * 100)
    
    # Simple uniqueness check & suffix if needed
    base_code = j_code
    counter = 1
    while catalog_data.get_definition_by_code(db, j_code):
        j_code = f"{base_code}-{counter}"
        counter += 1

    definition = catalog_data.create_definition(
        db=db,
        journey_code=j_code,
        title=payload.title,
        description=payload.description,
        total_days=payload.total_days,
        price_cents=final_price_cents,
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
    tags=["Liberation Admin"],
)
def admin_bulk_create_liberations(
    payload: BulkCreateLiberationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    results = []
    for item in payload.definitions:
        # 1. Generate unique journey_code from title
        j_code = generate_slug(item.title)
        
        # 2. Sync price/price_cents
        final_price_cents = item.price_cents
        if item.price is not None:
            final_price_cents = int(item.price * 100)

        base_code = j_code
        counter = 1
        while catalog_data.get_definition_by_code(db, j_code):
            j_code = f"{base_code}-{counter}"
            counter += 1

        definition = catalog_data.create_definition(
            db=db,
            journey_code=j_code,
            title=item.title,
            description=item.description,
            total_days=item.total_days,
            price_cents=final_price_cents,
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


# ── Admin: review queue & full list ─────────────────────────────────────────

import math
from app.schemas.schema_system import PaginationMeta

@router.get(
    "/admin/liberation",
    response_model=ApiResponse[LiberationCatalogListResponse],
    summary="Admin: list ALL liberation journeys (active and inactive, pending and approved)",
    tags=["Liberation Admin"],
)
def admin_list_all(
    limit: int = 50,
    offset: int = 0,
    page: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    if page is not None and page > 0:
        offset = (page - 1) * limit
    else:
        page = (offset // limit) + 1 if limit > 0 else 1

    definitions = catalog_data.list_all_definitions(db, limit=limit, offset=offset)
    total = catalog_data.count_all_definitions(db)
    items = [_definition_to_response(d) for d in definitions]
    
    total_pages = math.ceil(total / limit) if limit > 0 else 1
    if total_pages == 0:
        total_pages = 1

    pagination_meta = PaginationMeta(
        total=total,
        page=page,
        limit=limit,
        totalPages=total_pages
    )

    result = LiberationCatalogListResponse(definitions=items, total=total, meta=pagination_meta)
    return success_response("All liberations fetched", status.HTTP_200_OK, result)


@router.get(
    "/admin/liberation/pending",
    response_model=ApiResponse[LiberationCatalogListResponse],
    summary="Admin: list pending liberation submissions",
    tags=["Liberation Admin"],
    include_in_schema=False,  # Disabled: no user submissions in admin-only model
)
def admin_list_pending(
    limit: int = 50,
    offset: int = 0,
    page: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    if page is not None and page > 0:
        offset = (page - 1) * limit
    else:
        page = (offset // limit) + 1 if limit > 0 else 1

    definitions = catalog_data.list_pending_definitions(db, limit=limit, offset=offset)
    total = catalog_data.count_pending_definitions(db)
    items = [_definition_to_response(d) for d in definitions]
    
    total_pages = math.ceil(total / limit) if limit > 0 else 1
    if total_pages == 0:
        total_pages = 1

    pagination_meta = PaginationMeta(
        total=total,
        page=page,
        limit=limit,
        totalPages=total_pages
    )

    result = LiberationCatalogListResponse(definitions=items, total=total, meta=pagination_meta)
    return success_response("Pending liberations fetched", status.HTTP_200_OK, result)



# ── Admin: get single journey detail ────────────────────────────────────────

@router.get(
    "/admin/liberation/{definition_id}",
    response_model=ApiResponse[LiberationDefinitionResponse],
    summary="Admin: get full details of a specific liberation journey",
    tags=["Liberation Admin"],
)
def admin_get_liberation(
    definition_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Returns the full metadata and all day definitions for a specific liberation journey."""
    definition = catalog_data.get_definition_by_id(db, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Liberation definition not found.")
    return success_response("Liberation fetched", status.HTTP_200_OK, _definition_to_response(definition))


# ── Admin: get single day detail ─────────────────────────────────────────────

@router.get(
    "/admin/liberation/{definition_id}/day/{day_number}",
    response_model=ApiResponse[DayThemeItem],
    summary="Admin: get the content of a specific day in a liberation journey",
    tags=["Liberation Admin"],
)
def admin_get_liberation_day(
    definition_id: str,
    day_number: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Returns the exercise_text and why_text for a specific day in a journey."""
    from app.model.liberation import LiberationDayDefinition
    definition = catalog_data.get_definition_by_id(db, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Liberation definition not found.")
    day = db.query(LiberationDayDefinition).filter(
        LiberationDayDefinition.definition_id == definition.id,
        LiberationDayDefinition.day_number == day_number,
    ).first()
    if not day:
        raise HTTPException(status_code=404, detail=f"Day {day_number} not found in this journey.")
    result = DayThemeItem(
        day_number=day.day_number,
        day_theme=day.day_theme,
        exercise_text=day.exercise_text,
        why_text=day.why_text,
    )
    return success_response(f"Day {day_number} detail fetched", status.HTTP_200_OK, result)


@router.post(
    "/admin/liberation/{definition_id}/review",
    response_model=ApiResponse[LiberationReviewResponse],
    summary="Admin: approve or reject a liberation submission",
    tags=["Liberation Admin"],
    include_in_schema=False,  # Disabled: no user submissions in admin-only model
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

@router.post(
    "/admin/liberation/{definition_id}/set-active",
    response_model=ApiResponse[LiberationReviewResponse],
    summary="Admin: set liberation active/inactive status",
    tags=["Liberation Admin"],
)
def admin_set_liberation_active(
    definition_id: str,
    payload: SetLiberationActiveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    definition = catalog_data.get_definition_by_id(db, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Liberation definition not found.")

    definition.is_active = payload.is_active
    db.commit()
    db.refresh(definition)

    status_str = "activated" if payload.is_active else "deactivated"
    result = LiberationReviewResponse(
        message=f"Liberation {status_str}.",
        definition_id=definition.id,
        status=status_str,
    )
    return success_response(f"Liberation {status_str}", status.HTTP_200_OK, result)


@router.patch(
    "/admin/liberation/{definition_id}",
    response_model=ApiResponse[LiberationDefinitionResponse],
    summary="Admin: update an existing liberation journey",
    tags=["Liberation Admin"],
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
    
    if payload.price is not None:
        definition.price_cents = int(payload.price * 100)
    elif payload.price_cents is not None:
        definition.price_cents = payload.price_cents

    if payload.currency is not None: definition.currency = payload.currency
    if payload.cover_image_url is not None: definition.cover_image_url = payload.cover_image_url
    if payload.is_active is not None: definition.is_active = payload.is_active
    if payload.rating is not None: definition.rating = payload.rating
    if payload.what_to_expect is not None: definition.what_to_expect = payload.what_to_expect
    if payload.setup_instructions is not None: definition.setup_instructions = payload.setup_instructions

    # 2. Update day themes if provided
    if payload.days:
        from app.model.liberation import LiberationDayDefinition
        
        for day_input in payload.days:
            # Update specific day or insert if missing
            existing_day = db.query(LiberationDayDefinition).filter(
                LiberationDayDefinition.definition_id == definition.id,
                LiberationDayDefinition.day_number == day_input.day
            ).first()

            if existing_day:
                existing_day.day_theme = day_input.title
                existing_day.exercise_text = day_input.exercise_text
                existing_day.why_text = day_input.why_text
            else:
                db.add(LiberationDayDefinition(
                    definition_id=definition.id,
                    day_number=day_input.day,
                    day_theme=day_input.title,
                    exercise_text=day_input.exercise_text,
                    why_text=day_input.why_text
                ))

    db.commit()
    db.refresh(definition)
    
    return success_response("Liberation updated successfully", status.HTTP_200_OK, _definition_to_response(definition))
