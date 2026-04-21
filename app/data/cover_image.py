"""
app/data/cover_image.py

Raw database queries for the CoverImage table.
No business logic here — only DB read/write operations.
"""
import uuid
from typing import Optional
from sqlalchemy.orm import Session

from app.model.cover_image import CoverImage, CoverImageType


def create_cover_image(
    db: Session,
    story_type: CoverImageType,
    image_url: str,
    s3_key: str,
    uploaded_by: str,
) -> CoverImage:
    """Insert a new cover image record after a successful S3 upload."""
    cover = CoverImage(
        story_type=story_type,
        image_url=image_url,
        s3_key=s3_key,
        uploaded_by=uuid.UUID(uploaded_by),
    )
    db.add(cover)
    db.commit()
    db.refresh(cover)
    return cover


def get_cover_image_by_id(db: Session, cover_id: str) -> Optional[CoverImage]:
    """Fetch a cover image by its UUID primary key."""
    return db.query(CoverImage).filter(CoverImage.id == uuid.UUID(cover_id)).first()


def list_cover_images(
    db: Session,
    story_type: Optional[CoverImageType] = None,
    active_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[CoverImage], int]:
    """
    Returns a paginated list of cover images and the total count.
    Optionally filtered by story_type and/or is_active.
    """
    query = db.query(CoverImage)
    if story_type:
        query = query.filter(CoverImage.story_type == story_type)
    if active_only:
        query = query.filter(CoverImage.is_active.is_(True))

    total = query.count()
    items = query.order_by(CoverImage.created_at.desc()).offset(offset).limit(limit).all()
    return items, total


def update_cover_image(
    db: Session,
    cover: CoverImage,
    story_type: Optional[CoverImageType] = None,
    image_url: Optional[str] = None,
    s3_key: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> CoverImage:
    """Partial update of a cover image record."""
    if story_type is not None:
        cover.story_type = story_type
    if image_url is not None:
        cover.image_url = image_url
    if s3_key is not None:
        cover.s3_key = s3_key
    if is_active is not None:
        cover.is_active = is_active
    db.commit()
    db.refresh(cover)
    return cover


def delete_cover_image(db: Session, cover: CoverImage) -> None:
    """Permanently delete a cover image record from the database."""
    db.delete(cover)
    db.commit()
