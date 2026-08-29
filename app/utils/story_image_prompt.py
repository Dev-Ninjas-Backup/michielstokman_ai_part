"""
Build and resolve DALL-E prompts for per-story cover artwork.

The story LLM is supposed to return an IMAGE_PROMPT block, but when it does not we
build one from the finished story text so every cover reflects that story.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.llm import get_story_llm
from app.model.story import ImageSource, Story

logger = logging.getLogger(__name__)

STORY_EXCERPT_CHARS = 6000
INPUT_EXCERPT_CHARS = 1500


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


def build_image_prompt_from_story(story: Story) -> str:
    """Ask the LLM for a story-specific DALL-E prompt after generation completes."""
    from app.utils.prompts import STORY_HUMAN_TEMPLATE

    art_direction = STORY_HUMAN_TEMPLATE.split("IMAGE_PROMPT:", 1)[1].split("STORY:", 1)[0]
    excerpt = (story.story_text or "")[:STORY_EXCERPT_CHARS]
    input_excerpt = (story.story_input or "")[:INPUT_EXCERPT_CHARS]
    tags = ", ".join(story.tags or [])
    growth = ", ".join(story.growth_areas or [])

    llm = get_story_llm(temperature=0.8)
    response = llm.invoke(
        "You write image prompts for cover artwork. Return only the prompt text, "
        "with no preamble and no quotes.\n\n"
        f"Story type: {story.story_type.value}\n"
        f"Title: {story.title or 'Untitled'}\n"
        f"Name: {story.first_name or 'Anonymous'}\n"
        f"Location: {story.location or 'unspecified'}\n"
        f"Gender: {story.gender or 'unspecified'}\n"
        f"Occupation: {story.occupation or 'unspecified'}\n"
        f"Age: {story.age if story.age is not None else 'unspecified'}\n"
        f"Themes/tags: {tags or 'none'}\n"
        f"Growth areas: {growth or 'none'}\n\n"
        f"Art direction:\n{art_direction.strip()}\n\n"
        f"Member's original submission:\n{input_excerpt}\n\n"
        f"Narrated story:\n{excerpt}\n\n"
        "The cover scene must visually reflect THIS specific story — its setting, "
        "mood, and symbols. Do not describe a generic stock scene."
    )
    return response.content.strip()


def resolve_image_prompt(story: Story, generated_prompt: Optional[str]) -> Optional[str]:
    """
    Prefer the IMAGE_PROMPT from story generation; otherwise build one from the
    finished story so covers are not identical across the library.
    """
    title = story.title or story.member_title or "Untitled"
    author = story.first_name or "Anonymous"

    generated = (generated_prompt or "").strip()
    if generated:
        return substitute_cover_placeholders(generated, title=title, author_name=author)

    if not (story.story_text or "").strip():
        return None

    logger.info(
        "No IMAGE_PROMPT from story generation for story %s; building from story text.",
        story.id,
    )
    built = build_image_prompt_from_story(story)
    if not built:
        return None
    return substitute_cover_placeholders(built, title=title, author_name=author)


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
        .order_by(Story.updated_at.asc(), Story.created_at.asc())
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
    """Regenerate collage covers for the given story IDs. Own DB session."""
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
