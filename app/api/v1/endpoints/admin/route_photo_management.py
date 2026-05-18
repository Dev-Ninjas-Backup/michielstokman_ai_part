"""
app/api/v1/endpoints/admin/route_photo_management.py

Photo Management — Admin endpoints for story cover images.

Cover images are stored on AWS S3 (no local fallback).
The S3 URL is saved in the cover_images table and can be linked
to stories via stories.cover_image_url.

Endpoints:
    POST   /v1/admin/photos          — Upload a new cover image
    GET    /v1/admin/photos          — List all cover images (paginated, filterable)
    GET    /v1/admin/photos/{id}     — Get details of a single cover image
    PATCH  /v1/admin/photos/{id}     — Update type, active status, or replace image
    DELETE /v1/admin/photos/{id}     — Remove from S3 and delete DB record
"""
import os
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.model.cover_image import CoverImageType
from app.model.user import User
from app.schemas.schema_cover_image import (
    CoverImageListResponse,
    CoverImageResponse,
    CoverImageUpdateRequest,
    APICoverImageType,
)
import app.data.cover_image as cover_image_data
from app.utils.s3 import delete_s3_object, upload_image_to_s3

router = APIRouter()

# Allowed image MIME types
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


from app.utils.media import format_media_url

def _serialize(cover) -> dict:
    """Convert a CoverImage ORM row to a dict for the response."""
    # Map story_type to Figma display names
    display_type = str(cover.story_type).replace("CoverImageType.", "").capitalize()
    if display_type == "Confession":
        display_type = "Confessions"
    elif display_type == "Meditation":
        display_type = "Meditation"  # stays Meditation
    elif display_type == "Transformation":
        display_type = "Journey"

    return {
        "id": str(cover.id),
        "story_type": display_type,
        "image_url": format_media_url(cover.image_url),
        "is_active": cover.is_active,
        "uploaded_by": str(cover.uploaded_by) if cover.uploaded_by else None,
        "created_at": cover.created_at,
        "updated_at": cover.updated_at,
    }


# ---------------------------------------------------------------------------
# POST /admin/photos — Upload new cover image
# ---------------------------------------------------------------------------

@router.post("/admin/photos", response_model=ApiResponse[CoverImageResponse])
async def upload_cover_image(
    story_type: APICoverImageType = Form(..., description="Story type: confession | meditation | journey"),
    file: UploadFile = File(..., description="Image file (JPEG, PNG, WEBP, GIF — max 10 MB)"),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Upload a new cover image for a story type.
    Image is stored on AWS S3 — S3 must be configured.
    """
    # Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: JPEG, PNG, WEBP, GIF.",
        )

    image_bytes = await file.read()

    # Validate file size
    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Image exceeds the 10 MB size limit.",
        )

    # Derive file extension from content type
    ext = file.content_type.split("/")[-1].replace("jpeg", "jpg")

    image_url, s3_key = upload_image_to_s3(image_bytes, file_extension=ext)
    if not image_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="S3 upload failed. Ensure AWS credentials are configured correctly.",
        )

    db_story_type = CoverImageType.transformation if story_type == APICoverImageType.journey else CoverImageType(story_type.value)

    cover = cover_image_data.create_cover_image(
        db=db,
        story_type=db_story_type,
        image_url=image_url,
        s3_key=s3_key,
        uploaded_by=str(current_user.id),
    )
    return success_response("Cover image uploaded successfully", status.HTTP_201_CREATED, _serialize(cover))


# ---------------------------------------------------------------------------
# GET /admin/photos — List cover images
# ---------------------------------------------------------------------------

@router.get("/admin/photos", response_model=ApiResponse[CoverImageListResponse])
def list_cover_images(
    story_type: APICoverImageType | None = Query(None, description="Filter by story type"),
    search: str | None = Query(None, description="Search by type"),
    active_only: bool = Query(False, description="Return only active images"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """List all cover images with optional filtering by story type and active status."""
    db_story_type = None
    if story_type:
        db_story_type = CoverImageType.transformation if story_type == APICoverImageType.journey else CoverImageType(story_type.value)

    db_search = search
    if search:
        if search.lower() == "journey":
            db_search = "transformation"

    items, total = cover_image_data.list_cover_images(
        db=db,
        story_type=db_story_type,
        search=db_search,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    return success_response(
        "Cover images fetched",
        status.HTTP_200_OK,
        {
            "items": [_serialize(c) for c in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


# ---------------------------------------------------------------------------
# GET /admin/photos/{cover_id} — Details
# ---------------------------------------------------------------------------

@router.get("/admin/photos/{cover_id}", response_model=ApiResponse[CoverImageResponse])
def get_cover_image(
    cover_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Get details of a single cover image by ID."""
    cover = cover_image_data.get_cover_image_by_id(db, cover_id)
    if not cover:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover image not found.")
    return success_response("Cover image fetched", status.HTTP_200_OK, _serialize(cover))


# ---------------------------------------------------------------------------
# PATCH /admin/photos/{cover_id} — Update type / active status / replace image
# ---------------------------------------------------------------------------

@router.patch("/admin/photos/{cover_id}", response_model=ApiResponse[CoverImageResponse])
async def update_cover_image(
    cover_id: str,
    story_type: APICoverImageType | None = Form(None),
    is_active: bool | None = Form(None),
    file: UploadFile | None = File(None, description="Optional new image to replace the existing one"),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Partially update a cover image.
    - Provide story_type and/or is_active to update metadata.
    - Provide a new file to replace the image (old S3 object is deleted).
    """
    cover = cover_image_data.get_cover_image_by_id(db, cover_id)
    if not cover:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover image not found.")

    new_image_url = None
    new_s3_key = None

    if file is not None:
        # Validate and replace image
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported file type '{file.content_type}'.",
            )
        image_bytes = await file.read()
        if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Image exceeds the 10 MB size limit.",
            )
        ext = file.content_type.split("/")[-1].replace("jpeg", "jpg")
        new_image_url, new_s3_key = upload_image_to_s3(image_bytes, file_extension=ext)
        if not new_image_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="S3 upload failed. Ensure AWS credentials are configured.",
            )
        # Delete the old S3 object
        delete_s3_object(cover.s3_key)

    db_story_type = None
    if story_type is not None:
        db_story_type = CoverImageType.transformation if story_type == APICoverImageType.journey else CoverImageType(story_type.value)

    cover = cover_image_data.update_cover_image(
        db=db,
        cover=cover,
        story_type=db_story_type,
        image_url=new_image_url,
        s3_key=new_s3_key,
        is_active=is_active,
    )
    return success_response("Cover image updated", status.HTTP_200_OK, _serialize(cover))


# ---------------------------------------------------------------------------
# DELETE /admin/photos/{cover_id} — Remove from S3 + DB
# ---------------------------------------------------------------------------

@router.delete("/admin/photos/{cover_id}", response_model=ApiResponse[None])
def delete_cover_image(
    cover_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Permanently delete a cover image.
    Removes the file from S3 first, then deletes the DB record.
    """
    cover = cover_image_data.get_cover_image_by_id(db, cover_id)
    if not cover:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover image not found.")

    delete_s3_object(cover.s3_key)
    cover_image_data.delete_cover_image(db, cover)

    return success_response("Cover image deleted successfully", status.HTTP_200_OK, None)
