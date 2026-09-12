"""Test-only DALL-E confession style preview. Does not touch Story rows.

Disabled when APP_ENV is production/prod (same gate as cover-template-preview).
Use locally or on a non-prod host that has OPENAI_API_KEY.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from app.core.config import settings
from app.utils.confession_style_preview import SAMPLES, generate_sample_cover

router = APIRouter()


def _reject_production() -> None:
    if settings.APP_ENV in ("production", "prod"):
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/test/confession-cover-style-preview")
async def confession_cover_style_preview(
    sample: int = Query(1, ge=1, le=len(SAMPLES), description="1=Liam, 2=Amara, 3=Jonas"),
    format: str = Query("image", pattern="^(image|json)$"),
):
    """Generate one fixture confession cover via DALL-E (no DB writes).

    - format=image → JPEG/PNG bytes
    - format=json → url + prompt metadata (no image body)
    """
    _reject_production()
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured on this server.",
        )

    result = generate_sample_cover(sample)
    if not result["cover_url"]:
        raise HTTPException(
            status_code=502,
            detail="DALL-E did not return an image for this sample.",
        )

    if format == "json":
        sample_meta = result["sample"]
        return JSONResponse(
            {
                "slug": sample_meta["slug"],
                "title": sample_meta["title"],
                "author_name": sample_meta["author_name"],
                "gender": sample_meta["gender"],
                "age": sample_meta["age"],
                "location": sample_meta["location"],
                "cover_url": result["cover_url"],
                "cover_key": result["cover_key"],
                "prompt_words": len(result["prompt"].split()),
                "prompt": result["prompt"],
            }
        )

    if not result["image_bytes"]:
        # Fall back to redirect-like JSON if download failed but URL exists
        raise HTTPException(
            status_code=502,
            detail=f"Image generated but could not be downloaded. url={result['cover_url']}",
        )

    media = "image/jpeg"
    if (result["cover_key"] or "").endswith(".png"):
        media = "image/png"
    return Response(content=result["image_bytes"], media_type=media)
