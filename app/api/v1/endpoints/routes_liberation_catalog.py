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
from app.data import liberation_catalog as catalog_data
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
    items = [
        LiberationDefinitionResponse(
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
        for d in definitions
    ]
    result = LiberationCatalogListResponse(definitions=items, total=len(items))
    return success_response("Liberation catalog fetched", status.HTTP_200_OK, result)


# ── Get single definition detail ────────────────────────────────────────────

@router.get(
    "/liberation/catalog/{journey_code}",
    response_model=ApiResponse[LiberationDefinitionResponse],
    summary="Get a single liberation definition by code",
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
        currency=definition.currency,
        is_admin_created=definition.is_admin_created,
        moderation_status=definition.moderation_status.value,
        moderation_notes=definition.moderation_notes,
        is_active=definition.is_active,
        created_at=definition.created_at,
        day_themes=[
            DayThemeItem(day_number=dd.day_number, day_theme=dd.day_theme)
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
)
def submit_liberation(
    payload: CreateLiberationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Allows a premium user to submit their own liberation journey.
    The submission goes into 'pending' review status and will be
    reviewed by an admin before going live on the storefront.
    """
    # Validate day_themes length matches total_days
    if len(payload.day_themes) != payload.total_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"day_themes length ({len(payload.day_themes)}) must equal total_days ({payload.total_days}).",
        )

    # Check uniqueness
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
        is_admin_created=False,
        day_themes=payload.day_themes,
    )

    result = LiberationDefinitionResponse(
        id=definition.id,
        journey_code=definition.journey_code,
        title=definition.title,
        description=definition.description,
        total_days=definition.total_days,
        price_cents=definition.price_cents,
        currency=definition.currency,
        is_admin_created=definition.is_admin_created,
        moderation_status=definition.moderation_status.value,
        moderation_notes=definition.moderation_notes,
        is_active=definition.is_active,
        created_at=definition.created_at,
        day_themes=[
            DayThemeItem(day_number=dd.day_number, day_theme=dd.day_theme)
            for dd in definition.day_definitions
        ],
    )
    return success_response("Liberation journey submitted for review", status.HTTP_201_CREATED, result)
