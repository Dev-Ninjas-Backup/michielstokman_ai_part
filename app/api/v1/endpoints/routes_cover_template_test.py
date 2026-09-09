"""Test-only HTML cover screenshot. Not used by story generation."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, HttpUrl

from app.core.config import settings
from app.cover_template.render import SAMPLE_DATA, render_cover_png

router = APIRouter()


class CoverTemplatePreviewRequest(BaseModel):
    title: str = Field(SAMPLE_DATA["title"], description="Cover title (newlines allowed)")
    subtitle: str = Field(SAMPLE_DATA["subtitle"])
    description: str = Field(SAMPLE_DATA["description"])
    author_name: str = Field(SAMPLE_DATA["author_name"])
    age: str = Field(SAMPLE_DATA["age"])
    gender: str = Field(SAMPLE_DATA["gender"])
    orientation: str = Field(SAMPLE_DATA["orientation"])
    city: str = Field(SAMPLE_DATA["city"])
    country: str = Field(SAMPLE_DATA["country"])
    is_explicit: bool = Field(True)
    photo_url: Optional[HttpUrl] = Field(
        None,
        description="Portrait URL. Omit to use the sample Figma photo.",
    )


def _reject_production() -> None:
    if settings.APP_ENV in ("production", "prod"):
        raise HTTPException(status_code=404, detail="Not found")


def _payload_from_model(body: CoverTemplatePreviewRequest) -> dict:
    data = body.model_dump()
    if data.get("photo_url") is not None:
        data["photo_url"] = str(data["photo_url"])
    return data


@router.get("/test/cover-template-preview")
async def cover_template_preview_get(
    title: str = Query(SAMPLE_DATA["title"]),
    subtitle: str = Query(SAMPLE_DATA["subtitle"]),
    description: str = Query(SAMPLE_DATA["description"]),
    author_name: str = Query(SAMPLE_DATA["author_name"]),
    age: str = Query(SAMPLE_DATA["age"]),
    gender: str = Query(SAMPLE_DATA["gender"]),
    orientation: str = Query(SAMPLE_DATA["orientation"]),
    city: str = Query(SAMPLE_DATA["city"]),
    country: str = Query(SAMPLE_DATA["country"]),
    is_explicit: bool = Query(True),
    photo_url: Optional[str] = Query(None),
):
    """Return a 2160×2160 PNG of the HTML cover template. Test-only."""
    _reject_production()
    png = await render_cover_png(
        {
            "title": title,
            "subtitle": subtitle,
            "description": description,
            "author_name": author_name,
            "age": age,
            "gender": gender,
            "orientation": orientation,
            "city": city,
            "country": country,
            "is_explicit": is_explicit,
            "photo_url": photo_url,
        }
    )
    return Response(content=png, media_type="image/png")


@router.post("/test/cover-template-preview")
async def cover_template_preview_post(body: CoverTemplatePreviewRequest):
    """Same as GET, with a JSON body for Postman."""
    _reject_production()
    png = await render_cover_png(_payload_from_model(body))
    return Response(content=png, media_type="image/png")
