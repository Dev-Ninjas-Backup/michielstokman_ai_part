"""
Build and resolve DALL-E prompts for per-story cover artwork.

Brand collage chrome is applied here so every cover shares the same layout
language. The LLM only supplies the unique photograph scene for THIS story.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.llm import get_story_llm
from app.model.story import ImageSource, Story

logger = logging.getLogger(__name__)

STORY_EXCERPT_CHARS = 6000
INPUT_EXCERPT_CHARS = 1500
SCENE_MAX_CHARS = 420

BANNED_SCENE_WORDS = (
    "sensual",
    "passionate",
    "passion",
    "erotic",
    "desire",
    "alluring",
    "ecstasy",
    "explicit",
    "nude",
    "nudity",
    "lingerie",
    "bare shoulder",
    "collarbones",
    "thong",
)

COVER_SAFETY = (
    "Only one person in the photograph. Fully clothed, elegant everyday clothing. "
    "No nudity, no lingerie, no couples, no physical touch between people."
)


def _cover_layout(story_type: str, title: str, author_name: str, scene: str) -> str:
    """Fixed brand frame + unique scene. Layout stays consistent; photo does not."""
    kind = (story_type or "confession").lower()
    safe_title = title.strip() or "Untitled"
    safe_author = author_name.strip() or "Anonymous"
    safe_scene = scene.strip() or "a fully clothed narrator in a quiet room, candid expression"

    if "meditation" in kind:
        return (
            f"Vertical portrait scrapbook collage cover. Aged butter-yellow and sage-green cardboard, "
            f"warm paper texture, dark grunge borders. Top left: black tape label MEDITATION in white "
            f"letters next to a sketched green heart. Left: large 3D butter-yellow block letters for "
            f"the title \"{safe_title}\" with a thick black outline and sage drop-shadow. "
            f"Bottom left: small typewriter tags PRESENCE, BREATH, HEALING. "
            f"Right: one vertical vintage sepia photograph of the narrator, taped at the corners. "
            f"Photograph scene unique to this story: {safe_scene}. "
            f"{COVER_SAFETY} Photorealistic mixed-media collage."
        )
    if "transformation" in kind:
        return (
            f"Vertical portrait scrapbook collage cover. Aged dark-purple cardboard, lavender and "
            f"periwinkle tones, grunge borders. Top left: purple tape label TRANSFORMATION in white. "
            f"Center-left: large 3D periwinkle block letters for the title \"{safe_title}\" with a "
            f"deep violet drop-shadow. "
            f"Right: one vertical photograph of the narrator in a deep purple duotone, taped with masking tape. "
            f"Photograph scene unique to this story: {safe_scene}. "
            f"Author name \"{safe_author}\" on torn tape at the bottom. "
            f"{COVER_SAFETY} Photorealistic mixed-media collage."
        )
    return (
        f"Vertical portrait scrapbook collage cover. Warm blush-pink paper with hot-pink splatters. "
        f"Left: pink banner sticker CONFESSION in bold white. Top right: PRIVATE in red handwritten capitals. "
        f"Center: retro magazine 3D block-letter title \"{safe_title}\" in cream-white with a black outline "
        f"and hot-pink offset shadow. Bottom: torn tape with handwritten \"{safe_author}\". "
        f"Bottom left: circular pink stamp of a sketched anatomical heart with a keyhole. "
        f"Right: one vertical photograph of the narrator in a moody pink cinematic duotone, taped with masking tape. "
        f"Photograph scene unique to this story: {safe_scene}. "
        f"{COVER_SAFETY} Photorealistic mixed-media collage."
    )


def substitute_cover_placeholders(
    prompt: str,
    *,
    title: str,
    author_name: str,
) -> str:
    """Replace template tokens the story LLM may leave in the IMAGE_PROMPT."""
    replacements = {
        "[INSERT GENERATED TITLE HERE]": title.strip() or "Untitled",
        "[INSERT AUTHOR NAME HERE]": author_name.strip() or "Anonymous",
        "[INSERT DURATION HERE]": "3 MIN",
    }
    result = prompt
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result.strip()


def sanitize_scene(scene: str) -> str:
    cleaned = scene.strip()
    for word in BANNED_SCENE_WORDS:
        cleaned = re.sub(re.escape(word), "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.-")
    if len(cleaned) > SCENE_MAX_CHARS:
        cleaned = cleaned[:SCENE_MAX_CHARS].rsplit(" ", 1)[0]
    return cleaned


def extract_unique_scene(raw_prompt: str) -> str:
    """
    The story model should return only a photograph scene. Older generations
    dumped a full collage spec; keep the photograph clause if present.
    """
    text = substitute_cover_placeholders(
        raw_prompt,
        title="Untitled",
        author_name="Anonymous",
    )
    match = re.search(
        r"(?:photograph scene|photo(?:graph)?(?: of the narrator)?|right side)\s*[:\-]\s*(.+)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return sanitize_scene(match.group(1))
    return sanitize_scene(text)


def build_scene_from_story(story: Story) -> str:
    """Ask the LLM for a story-specific photograph scene after generation."""
    excerpt = (story.story_text or "")[:STORY_EXCERPT_CHARS]
    input_excerpt = (story.story_input or "")[:INPUT_EXCERPT_CHARS]
    tags = ", ".join(story.tags or [])
    growth = ", ".join(story.growth_areas or [])

    llm = get_story_llm(temperature=0.55)
    response = llm.invoke(
        "Describe the unique cover photograph for this story in two sentences. "
        "Include setting, time of day, clothing, pose, and one object that appears in THIS story. "
        "One fully clothed person only. No collage, no title, no stickers, no banners.\n\n"
        f"Story type: {story.story_type.value}\n"
        f"Title: {story.title or 'Untitled'}\n"
        f"Narrator: {story.first_name or 'Anonymous'}\n"
        f"Themes/tags: {tags or 'none'}\n"
        f"Growth areas: {growth or 'none'}\n\n"
        f"Member's original submission:\n{input_excerpt}\n\n"
        f"Narrated story:\n{excerpt}\n"
    )
    return sanitize_scene(response.content.strip())


def compose_brand_cover_prompt(story: Story, scene: str) -> str:
    return _cover_layout(
        story.story_type.value,
        story.title or story.member_title or "Untitled",
        story.first_name or "Anonymous",
        scene,
    )


def fallback_scene(story: Story) -> str:
    """Safer unique-enough scene when the first DALL-E call is blocked."""
    title = (story.title or story.member_title or "this story").strip()
    tags = ", ".join((story.tags or [])[:3]) or "quiet reflection"
    return (
        f"A fully clothed narrator connected to '{title}', candid thoughtful expression, "
        f"story themes: {tags}, specific interior or landscape from the narrative, "
        f"elegant knit sweater or shirt, cinematic lighting, no other people"
    )


def resolve_image_prompt(story: Story, generated_prompt: Optional[str]) -> Optional[str]:
    """
    Always wrap a unique scene in the brand collage frame so covers look like
    the same product, but the photograph matches this story.
    """
    scene = ""
    generated = (generated_prompt or "").strip()
    if generated:
        scene = extract_unique_scene(generated)

    if not scene and (story.story_text or "").strip():
        logger.info(
            "No usable IMAGE_PROMPT scene for story %s; building from story text.",
            story.id,
        )
        scene = build_scene_from_story(story)

    if not scene:
        return None

    return compose_brand_cover_prompt(story, scene)


def _apply_admin_default_cover(db: Session, story: Story) -> None:
    from app.data import cover_image as cover_data
    from app.model.cover_image import CoverImageType

    if story.cover_image_url:
        return

    c_type = CoverImageType(story.story_type.value)
    fallback_url = cover_data.get_latest_active_image_url(db, c_type)
    if fallback_url:
        story.cover_image_url = fallback_url
        story.image_source = ImageSource.admin_default
        logger.info("Assigned admin default cover for story %s", story.id)


def try_generate_story_cover(
    db: Session,
    story: Story,
    *,
    image_prompt: Optional[str],
    allow_admin_fallback: bool = True,
    replace_member_cover: bool = False,
) -> None:
    """
    Generate a unique AI cover for a story.

    During automatic story generation, member uploads are left untouched.
    When the member explicitly requests artwork generation, set
    ``replace_member_cover=True`` so AI art can replace a prior upload.
    """
    from app.utils.image_generator import generate_ai_cover_image
    from app.utils.s3 import delete_s3_object

    if (
        story.image_source == ImageSource.user_uploaded
        and story.cover_image_url
        and not replace_member_cover
    ):
        return

    if not settings.OPENAI_API_KEY:
        if allow_admin_fallback:
            _apply_admin_default_cover(db, story)
        return

    resolved_prompt = resolve_image_prompt(story, image_prompt)
    if not resolved_prompt:
        if allow_admin_fallback:
            _apply_admin_default_cover(db, story)
        return

    previous_key = story.cover_image_key
    cover_url, cover_key = generate_ai_cover_image(
        title=story.title or story.member_title or "Untitled",
        story_type=story.story_type.value,
        author_name=story.first_name or "Anonymous",
        image_prompt=resolved_prompt,
    )

    if not cover_url:
        retry_prompt = compose_brand_cover_prompt(story, fallback_scene(story))
        logger.warning(
            "First cover attempt failed for story %s; retrying with a safer unique scene.",
            story.id,
        )
        cover_url, cover_key = generate_ai_cover_image(
            title=story.title or story.member_title or "Untitled",
            story_type=story.story_type.value,
            author_name=story.first_name or "Anonymous",
            image_prompt=retry_prompt,
        )

    if cover_url:
        story.cover_image_url = cover_url
        story.cover_image_key = cover_key
        story.image_source = ImageSource.ai_generated
        if previous_key and previous_key != cover_key:
            delete_s3_object(previous_key)
        return

    logger.warning("AI cover generation returned None for story %s", story.id)
    if allow_admin_fallback:
        _apply_admin_default_cover(db, story)


def list_stories_for_cover_regen(
    db: Session,
    *,
    limit: int = 25,
    only_missing_or_default: bool = False,
) -> list[Story]:
    """Completed stories whose covers can be replaced (never member uploads)."""
    from sqlalchemy import or_

    from app.model.story import GenerationStatus

    query = (
        db.query(Story)
        .filter(Story.generation_status == GenerationStatus.completed)
        .filter(Story.story_text.isnot(None))
        .filter(Story.story_text != "")
        .filter(
            or_(
                Story.image_source.is_(None),
                Story.image_source != ImageSource.user_uploaded,
            )
        )
        .order_by(Story.created_at.desc())
    )
    if only_missing_or_default:
        query = query.filter(
            or_(
                Story.cover_image_url.is_(None),
                Story.cover_image_url == "",
                Story.image_source.is_(None),
                Story.image_source == ImageSource.admin_default,
            )
        )
    return query.limit(max(1, min(limit, 80))).all()


def cover_regeneration_worker(story_ids: list[str]) -> None:
    """Regenerate unique AI covers for the given story IDs. Own DB session."""
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        for story_id in story_ids:
            story = db.query(Story).filter(Story.id == story_id).first()
            if not story:
                logger.warning("Cover regen skipped — story %s not found", story_id)
                continue
            if story.image_source == ImageSource.user_uploaded:
                continue
            try:
                try_generate_story_cover(
                    db,
                    story,
                    image_prompt=None,
                    allow_admin_fallback=False,
                    replace_member_cover=False,
                )
                db.commit()
                logger.info(
                    "Cover regen finished for %s source=%s url=%s",
                    story.id,
                    story.image_source,
                    bool(story.cover_image_url),
                )
            except Exception:
                db.rollback()
                logger.exception("Cover regen failed for story %s", story_id)
    finally:
        db.close()
