"""
app/api/v1/endpoints/routes_liberation_catalog.py

User-facing endpoints for browsing and submitting liberation definitions.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.model.user import User
from app.utils.slug import generate_slug
from app.data import liberation_catalog as catalog_data
from app.data.billing import check_user_has_plan_code
from app.schemas.schema_liberation_catalog import (
    CreateLiberationRequest,
    LiberationDefinitionResponse,
    LiberationCatalogListResponse,
    DayThemeItem,
)

router = APIRouter()


# ── Browse approved liberations (public storefront) ─────────────────────────

@router.get(
    "/liberation/catalog",
    response_model=ApiResponse[LiberationCatalogListResponse],
    summary="List all approved liberation journeys",
    tags=["Liberation Journey"],
)
def list_catalog(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns every active + approved liberation definition.
    Used by the frontend to render the journey storefront cards.
    """
    definitions = catalog_data.list_approved_definitions(db, limit=limit, offset=offset)
    items = []
    for d in definitions:
        items.append(
            LiberationDefinitionResponse(
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
                what_to_expect=d.what_to_expect or [],
                setup_instructions=d.setup_instructions or [],
                has_access=check_user_has_plan_code(db, current_user.id, f"journey_{d.journey_code}"),
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
        )
    result = LiberationCatalogListResponse(definitions=items, total=len(items))
    return success_response("Liberation catalog fetched", status.HTTP_200_OK, result)


# ── Get single definition detail ────────────────────────────────────────────

@router.get(
    "/liberation/catalog/{journey_code}",
    response_model=ApiResponse[LiberationDefinitionResponse],
    summary="Get a single liberation definition by code",
    tags=["Liberation Journey"],
)
def get_catalog_item(
    journey_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    definition = catalog_data.get_definition_by_code(db, journey_code)
    if not definition:
        raise HTTPException(status_code=404, detail="Liberation journey not found.")
    
    result = LiberationDefinitionResponse(
        id=definition.id,
        journey_code=definition.journey_code,
        title=definition.title,
        description=definition.description,
        total_days=definition.total_days,
        price_cents=definition.price_cents,
        price=definition.price_cents / 100.0,
        currency=definition.currency,
        is_admin_created=definition.is_admin_created,
        moderation_status=definition.moderation_status.value,
        moderation_notes=definition.moderation_notes,
        is_active=definition.is_active,
        created_at=definition.created_at,
        what_to_expect=definition.what_to_expect or [],
        setup_instructions=definition.setup_instructions or [],
        has_access=check_user_has_plan_code(db, current_user.id, f"journey_{definition.journey_code}"),
        days=[
            DayThemeItem(
                day_number=dd.day_number, 
                day_theme=dd.day_theme,
                exercise_text=dd.exercise_text,
                why_text=dd.why_text
            )
            for dd in definition.day_definitions
        ],
    )
    return success_response("Liberation definition fetched", status.HTTP_200_OK, result)


# ── Premium user: submit a new liberation (single creation, pending review) ─

@router.post(
    "/liberation/catalog/submit",
    response_model=ApiResponse[LiberationDefinitionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new liberation journey for review",
    tags=["Liberation Journey"],
    include_in_schema=False,  # Disabled: user submissions no longer accepted
)
def submit_liberation(
    payload: CreateLiberationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    [DISABLED] User journey submissions are no longer accepted.
    All journeys are created exclusively by admins.
    """
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User journey submissions are currently disabled. All journeys are admin-created.",
    )
    # Validate days length matches total_days
    if len(payload.days) != payload.total_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"days length ({len(payload.days)}) must equal total_days ({payload.total_days}).",
        )

    # Check uniqueness
    existing = catalog_data.get_definition_by_code(db, generate_slug(payload.title))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A liberation with a similar title already exists.",
        )

    definition = catalog_data.create_definition(
        db=db,
        journey_code=generate_slug(payload.title),
        title=payload.title,
        description=payload.description,
        total_days=payload.total_days,
        price_cents=payload.price_cents,
        currency=payload.currency,
        created_by=current_user.id,
        is_admin_created=False,
        days=payload.days,
        what_to_expect=payload.what_to_expect,
        setup_instructions=payload.setup_instructions,
    )

    result = LiberationDefinitionResponse(
        id=definition.id,
        journey_code=definition.journey_code,
        title=definition.title,
        description=definition.description,
        total_days=definition.total_days,
        price_cents=definition.price_cents,
        price=definition.price_cents / 100.0,
        currency=definition.currency,
        is_admin_created=definition.is_admin_created,
        moderation_status=definition.moderation_status.value,
        moderation_notes=definition.moderation_notes,
        is_active=definition.is_active,
        created_at=definition.created_at,
        has_access=False, # Just created
        days=[
            DayThemeItem(
                day_number=dd.day_number, 
                day_theme=dd.day_theme,
                exercise_text=dd.exercise_text,
                why_text=dd.why_text
            )
            for dd in definition.day_definitions
        ],
    )
    return success_response("Liberation journey submitted for review", status.HTTP_201_CREATED, result)
