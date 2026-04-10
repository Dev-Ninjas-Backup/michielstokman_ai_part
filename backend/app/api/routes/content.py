from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import ContentItem, ContentType
from app.schemas.dto import ContentCard, DiscoverResponse


router = APIRouter(prefix="/content", tags=["Content"])


@router.get("/discover", response_model=DiscoverResponse)
def discover(
    db: Session = Depends(get_db),
    kind: ContentType | None = Query(default=None),
    q: str | None = Query(default=None),
):
    query = db.query(ContentItem)
    if kind:
        query = query.filter(ContentItem.content_type == kind)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter((ContentItem.title.ilike(like)) | (ContentItem.subtitle.ilike(like)))
    items = query.order_by(ContentItem.rating.desc()).limit(30).all()
    return DiscoverResponse(items=[ContentCard.model_validate(item, from_attributes=True) for item in items])


@router.get("/{item_id}", response_model=ContentCard)
def get_content(item_id: str, db: Session = Depends(get_db)):
    item = db.query(ContentItem).filter(ContentItem.id == item_id).first()
    return ContentCard.model_validate(item, from_attributes=True)
