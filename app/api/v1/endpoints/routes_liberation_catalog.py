"""
app/api/v1/endpoints/routes_liberation_catalog.py

User-facing endpoints for browsing and submitting liberation definitions.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.model.user import User
from app.utils.slug import generate_slug
from app.utils.media import format_media_url
from app.data import liberation_catalog as catalog_data
from app.data.billing import check_user_has_plan_code
from app.data.cover_image import get_latest_active_image_url
from app.model.cover_image import CoverImageType
from app.schemas.schema_system import PaginationMeta
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
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Returns every active + approved liberation definition.
    Used by the frontend to render the journey storefront cards.
    """
    definitions = catalog_data.list_approved_definitions(db, limit=limit, offset=offset)
    
    # Get latest active cover image for transformation to use as fallback
    fallback_cover = get_latest_active_image_url(db, CoverImageType.transformation)
    
    items = []
    for d in definitions:
        first_day_img = next((dd.image_url for dd in (d.day_definitions or []) if dd.image_url), None)
        cover_img = d.cover_image_url or first_day_img or fallback_cover
        status_val = d.moderation_status.value if hasattr(d.moderation_status, "value") else str(d.moderation_status or "approved")
        price_val = (d.price_cents / 100.0) if d.price_cents is not None else 0.0
        
        items.append(
            LiberationDefinitionResponse(
                id=d.id,
                journey_code=d.journey_code,
                title=d.title,
                description=d.description,
                total_days=d.total_days or 7,
                price_cents=d.price_cents or 0,
                price=price_val,
                currency=d.currency or "EUR",
                is_admin_created=bool(d.is_admin_created),
                moderation_status=status_val,
                moderation_notes=d.moderation_notes,
                is_active=bool(d.is_active),
                created_at=d.created_at,
                cover_image_url=format_media_url(cover_img),
                rating=d.rating,
                what_to_expect=d.what_to_expect if isinstance(d.what_to_expect, list) else [],
                setup_instructions=d.setup_instructions if isinstance(d.setup_instructions, list) else [],
                has_access=check_user_has_plan_code(db, current_user.id, f"journey_{d.journey_code}") if current_user else False,
                days=[
                    DayThemeItem(
                        day_number=dd.day_number, 
                        day_theme=dd.day_theme,
                        exercise_text=dd.exercise_text,
                        why_text=dd.why_text,
                        image_url=format_media_url(dd.image_url),
                    )
                    for dd in (d.day_definitions or [])
                ],
            )
        )
    
    page = (offset // limit) + 1 if limit > 0 else 1
    total_count = len(items)
    total_pages = (total_count + limit - 1) // limit if limit > 0 else 1
    meta = PaginationMeta(
        total=total_count,
        page=page,
        limit=limit,
        totalPages=total_pages,
    )
    result = LiberationCatalogListResponse(definitions=items, total=total_count, meta=meta)
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
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    definition = catalog_data.get_definition_by_code(db, journey_code)
    if not definition:
        raise HTTPException(status_code=404, detail="Liberation journey not found.")
    
    # Get latest active cover image for transformation to use as fallback
    fallback_cover = get_latest_active_image_url(db, CoverImageType.transformation)
    first_day_img = next((dd.image_url for dd in (definition.day_definitions or []) if dd.image_url), None)
    cover_img = definition.cover_image_url or first_day_img or fallback_cover
    status_val = definition.moderation_status.value if hasattr(definition.moderation_status, "value") else str(definition.moderation_status or "approved")
    price_val = (definition.price_cents / 100.0) if definition.price_cents is not None else 0.0
    
    result = LiberationDefinitionResponse(
        id=definition.id,
        journey_code=definition.journey_code,
        title=definition.title,
        description=definition.description,
        total_days=definition.total_days or 7,
        price_cents=definition.price_cents or 0,
        price=price_val,
        currency=definition.currency or "EUR",
        is_admin_created=bool(definition.is_admin_created),
        moderation_status=status_val,
        moderation_notes=definition.moderation_notes,
        is_active=bool(definition.is_active),
        created_at=definition.created_at,
        cover_image_url=format_media_url(cover_img),
        rating=definition.rating,
        what_to_expect=definition.what_to_expect if isinstance(definition.what_to_expect, list) else [],
        setup_instructions=definition.setup_instructions if isinstance(definition.setup_instructions, list) else [],
        has_access=check_user_has_plan_code(db, current_user.id, f"journey_{definition.journey_code}") if current_user else False,
        days=[
            DayThemeItem(
                day_number=dd.day_number, 
                day_theme=dd.day_theme,
                exercise_text=dd.exercise_text,
                why_text=dd.why_text,
                image_url=format_media_url(dd.image_url),
            )
            for dd in (definition.day_definitions or [])
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
