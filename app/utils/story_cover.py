"""Cover generation router — DALL-E collage vs HTML cover_template + portrait.

Controlled by ``COVER_GENERATION_METHOD`` (default ``dalle``).

- ``dalle``    → unchanged path in ``story_image_prompt.try_generate_story_cover``
                 (Grok IMAGE_PROMPT / P2 full-collage + ``generate_ai_cover_image``).
                 Sets ``image_source=ai_generated``.
- ``template`` → for *confession* stories only:
                 1) portrait-only DALL-E prompt (``build_portrait_only_prompt``)
                 2) Playwright ``cover_template`` with that photo in the slot
                 Sets ``image_source=template_v1``.
                 Non-confession stories still use the DALL-E collage path.

Flip the env var back to ``dalle`` at any time to restore old behavior with no
code changes. Full-collage P1/P2 builders remain intact for the dalle path.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.model.story import ImageSource, Story, StoryType

logger = logging.getLogger(__name__)

# Hard limits from cover_template/DYNAMIC.md (empirically measured).
CONFESSION_DESCRIPTION_HARD_LIMIT = 77
CONFESSION_DESCRIPTION_SOFT_LIMIT = 58  # ~3 lines with gap above location
# Fluid wrap inside the 558px beige column (torn edge @ 670). CSS wraps; Python
# packs complete words so height stays within title ≤3 / subtitle ≤2 visual lines.
TITLE_LINE_SOFT_LIMIT = 6  # ~one wide Edo@164 word per packed line in 558px
TITLE_LINE_HARD_LIMIT = 14
# 2 packed lines ≈ ≤3 CSS wraps max; keeps block above confession (top: 1000).
TITLE_MAX_VISUAL_LINES = 2
SUBTITLE_LINE_SOFT_LIMIT = 16  # ~one Edo@80 line in 558px
SUBTITLE_LINE_HARD_LIMIT = 20
SUBTITLE_MAX_VISUAL_LINES = 2

COVER_METHOD_DALLE = "dalle"
COVER_METHOD_TEMPLATE = "template"
# Logged / stored marker for the HTML pipeline (image_source enum value).
TEMPLATE_SOURCE_LABEL = "template_v1"


def cover_generation_method() -> str:
    """Normalized pipeline selector: ``dalle`` (default) or ``template``."""
    return settings.COVER_GENERATION_METHOD


def uses_template_pipeline(story: Story | None = None) -> bool:
    """True when this story should render via cover_template."""
    if cover_generation_method() != COVER_METHOD_TEMPLATE:
        return False
    if story is None:
        return True
    # Template art is confession-shaped; other types keep DALL-E collage for now.
    return story.story_type == StoryType.confession


def _split_location(story: Story) -> tuple[str, str]:
    city = (story.city or "").strip()
    country = (story.country or "").strip()
    if city or country:
        return city, country
    loc = (story.location or "").strip()
    if not loc:
        return "", ""
    if "," in loc:
        left, right = loc.split(",", 1)
        return left.strip(), right.strip()
    return loc, ""


def _pack_words_to_lines(
    text: str,
    *,
    per_line: int,
    max_lines: int,
    hard_limit: int | None = None,
) -> str:
    """Pack complete words into up to ``max_lines`` lines (soft width ``per_line``).

    Returns newline-separated lines for Cover.set line1/line2 (extra lines beyond
    two are joined into line2). Never splits mid-word when the token fits
    ``hard_limit`` (defaults to ``per_line``).
    """
    token_cap = hard_limit if hard_limit is not None else per_line
    cleaned = re.sub(r"\s+", " ", (text or "").replace("\r\n", "\n").strip())
    if not cleaned:
        return ""
    # Honor explicit newlines as hard breaks, then re-pack each segment.
    segments = [p.strip() for p in cleaned.split("\n") if p.strip()]
    words: list[str] = []
    for seg in segments:
        words.extend(seg.split())

    lines: list[str] = []
    current = ""
    for word in words:
        if len(word) > per_line:
            # Finish the current soft line, then place the long token alone.
            if current:
                lines.append(current)
                current = ""
                if len(lines) >= max_lines:
                    break
            if len(word) <= token_cap:
                lines.append(word)
            else:
                # Last resort for a single overlong token.
                lines.append(truncate_at_last_word(word, token_cap) or word[:token_cap])
            if len(lines) >= max_lines:
                break
            continue

        trial = f"{current} {word}".strip() if current else word
        if len(trial) <= per_line:
            current = trial
            continue
        if current:
            lines.append(current)
            if len(lines) >= max_lines:
                current = ""
                break
        current = word

    if current and len(lines) < max_lines:
        lines.append(current)

    if not lines:
        return ""
    # Cover template has two binds: fold line3+ into line2 with spaces (CSS wraps).
    if len(lines) == 1:
        return lines[0]
    if len(lines) == 2:
        return f"{lines[0]}\n{lines[1]}"
    return f"{lines[0]}\n{' '.join(lines[1:max_lines])}"


def _active_title(story: Story) -> str:
    """Brush title packed with complete words for fluid wrap up to the torn edge.

    Very short titles (≤3 words that fit the hard line) stay on one line so we
    do not invent a blank second Edo row for cases like ``The Salt``.
    """
    raw = (story.title or story.member_title or story.ai_generated_title or "Untitled").strip()
    raw = re.sub(r"\s+", " ", raw)
    words = raw.split()
    if words and len(words) <= 3 and len(raw) <= TITLE_LINE_HARD_LIMIT:
        return raw
    packed = _pack_words_to_lines(
        raw,
        per_line=TITLE_LINE_SOFT_LIMIT,
        max_lines=TITLE_MAX_VISUAL_LINES,
        hard_limit=TITLE_LINE_HARD_LIMIT,
    )
    return packed or "Untitled"


def _subtitle_for_story(story: Story) -> str:
    # None → keep the classic two-line default for layout stability.
    # Explicit "" → allow empty subtitle (pink underline sits under the title).
    tag = getattr(story, "hero_tagline", None)
    if tag is None:
        return _pack_words_to_lines(
            "A Night That Liberated My Essence",
            per_line=SUBTITLE_LINE_SOFT_LIMIT,
            max_lines=SUBTITLE_MAX_VISUAL_LINES,
            hard_limit=SUBTITLE_LINE_HARD_LIMIT,
        )
    return _pack_words_to_lines(
        str(tag),
        per_line=SUBTITLE_LINE_SOFT_LIMIT,
        max_lines=SUBTITLE_MAX_VISUAL_LINES,
        hard_limit=SUBTITLE_LINE_HARD_LIMIT,
    )


def truncate_at_last_word(text: str, max_chars: int = CONFESSION_DESCRIPTION_HARD_LIMIT) -> str:
    """Trim to max_chars at the last complete word — never mid-word.

    Also drops trailing function-words and dangling punctuation so the
    confession does not end on ``… heavy,`` or ``… in a``.
    """
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        result = cleaned
    else:
        cut = cleaned[:max_chars]
        # If we landed on a word boundary, keep the hard cut.
        if max_chars >= len(cleaned) or cleaned[max_chars].isspace():
            result = cut.rstrip()
        else:
            sp = cut.rfind(" ")
            if sp <= 0:
                # Single overlong token — last resort hard cut (still ≤ max_chars).
                result = cut.rstrip()
            else:
                result = cut[:sp].rstrip()

    return _cleanup_truncated_phrase(result)


def _cleanup_truncated_phrase(text: str) -> str:
    """Strip dangling articles/conjunctions and trailing clause punctuation."""
    result = (text or "").strip()
    if not result:
        return ""

    dangling = re.compile(
        r"\b(a|an|the|in|on|of|to|for|and|or|with|at|by|from|as|but|nor|so|yet|"
        r"into|onto|upon|over|under|like|than|then|that|this|these|those|my|our|"
        r"his|her|their|its)\s*$",
        re.I,
    )
    # Repeat: drop a dangling function word, then strip trailing ,;:—-
    for _ in range(8):
        prev = result
        while dangling.search(result) and " " in result:
            result = result.rsplit(" ", 1)[0].rstrip()
        result = re.sub(r"[\s,;:—–\-]+$", "", result).rstrip()
        if result == prev:
            break
    return result


def truncate_at_sentence(
    text: str,
    *,
    soft_limit: int = CONFESSION_DESCRIPTION_SOFT_LIMIT,
    hard_limit: int = CONFESSION_DESCRIPTION_HARD_LIMIT,
) -> str:
    """Prefer a complete sentence within soft, then hard; else cleaned word-cut.

    Prefers ``.!?`` first. If none, a ``;`` clause is treated as a sentence and
    normalized to end with ``.`` — so Salt-style copy like
    ``…salt; the wanting settled heavy,`` becomes ``…salt.`` instead of a
    dangling comma. Trailing ``,`` / conjunctions are always stripped.
    """
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""

    def _last_match_within(limit: int, pattern: str) -> str | None:
        window = cleaned if len(cleaned) <= limit else cleaned[:limit]
        best_end = -1
        for m in re.finditer(pattern, window):
            best_end = m.end()
        if best_end <= 0:
            return None
        sentence = window[:best_end].strip()
        # Reject tiny fragments like "I." when more copy exists.
        if len(sentence) >= 12 or len(cleaned) <= limit:
            return sentence
        return None

    for limit in (soft_limit, hard_limit):
        hit = _last_match_within(limit, r"[.!?]")
        if hit:
            return hit

    # No .!? — promote a semicolon clause to a clean sentence end.
    for limit in (soft_limit, hard_limit):
        hit = _last_match_within(limit, r";")
        if hit:
            clause = _cleanup_truncated_phrase(hit.rstrip(";").strip())
            if clause:
                return clause if clause.endswith((".", "!", "?")) else f"{clause}."

    # Still incomplete but contains `;` somewhere (e.g. under soft with trailing ,).
    if ";" in cleaned:
        first = _cleanup_truncated_phrase(cleaned.split(";", 1)[0].strip())
        if len(first) >= 12:
            return first if first.endswith((".", "!", "?")) else f"{first}."

    return truncate_at_last_word(cleaned, hard_limit)


def format_two_line_field(
    text: str,
    line_limit: int,
    *,
    wrap_soft_limit: int | None = None,
) -> str:
    """Split/wrap into at most two lines, each word-truncated to ``line_limit``.

    When wrapping a single long line, prefer breaking near ``wrap_soft_limit``
    (Edo brush subtitle soft width) so glyphs do not spill into the photo.
    Strips Grok emphasis markers (``**word**``). Empty input → empty string.
    """
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw:
        return ""
    # Taglines may include **PUNCH** markers — cover template is plain text.
    raw = re.sub(r"\*\*([^*]+)\*\*", r"\1", raw)
    raw = re.sub(r"[ \t]+", " ", raw)

    parts = [p.strip() for p in raw.split("\n") if p.strip()]
    if not parts:
        return ""

    wrap_at = wrap_soft_limit if wrap_soft_limit is not None else line_limit

    if len(parts) == 1 and len(parts[0]) > wrap_at:
        # Wrap a single long line into two cover lines at a word boundary.
        line = parts[0]
        cut = truncate_at_last_word(line, wrap_at)
        if len(cut) < max(8, wrap_at // 3):
            cut = truncate_at_last_word(line, line_limit)
        rest = line[len(cut) :].strip()
        # Line 2 may use the hard limit so punch-words (e.g. "held") are kept;
        # line 1 uses soft wrap so glyphs stay out of the photo column.
        line2 = truncate_at_last_word(rest, line_limit) if rest else ""
        return f"{cut}\n{line2}".strip() if line2 else cut

    line1 = truncate_at_last_word(parts[0], line_limit)
    if len(parts) == 1:
        return line1
    # Remaining parts join into line 2 (still capped).
    line2 = truncate_at_last_word(" ".join(parts[1:]), line_limit)
    if not line2:
        return line1
    return f"{line1}\n{line2}"


def _description_for_story(story: Story) -> str:
    hook = (story.hero_hook or "").strip()
    if hook:
        return truncate_at_sentence(hook)
    raw = (story.story_text or story.story_input or "").strip()
    if not raw:
        return "A confession about shame, desire and finally choosing me."
    # Hard/soft limits from cover_template/DYNAMIC.md — prefer full sentence.
    return truncate_at_sentence(raw)


def story_to_cover_template_payload(
    story: Story,
    *,
    photo_url: str | None = None,
) -> dict:
    """Map story row fields onto cover_template render / Cover.set payload keys."""
    city, country = _split_location(story)
    return {
        "title": _active_title(story),
        "subtitle": _subtitle_for_story(story),
        "description": _description_for_story(story),
        "author_name": (story.first_name or "Anonymous").strip() or "Anonymous",
        "age": str(story.age) if story.age is not None else "",
        "gender": (story.gender or "").strip().lower(),
        "orientation": (story.sexual_orientation or "").strip().lower(),
        "city": city,
        "country": country,
        "is_explicit": bool(story.high_intensity),
        # Portrait for the torn-photo hole (DALL-E portrait URL or None = sample).
        "photo_url": photo_url,
    }


def _generate_portrait_for_template(story: Story) -> tuple[str | None, str | None]:
    """DALL-E portrait-only image for the template photo slot. Returns (url, key)."""
    from app.utils.image_generator import generate_ai_cover_image
    from app.utils.story_image_prompt import build_portrait_only_prompt

    if not settings.OPENAI_API_KEY:
        logger.warning(
            "COVER_GENERATION_METHOD=template but OPENAI_API_KEY missing — "
            "falling back to sample portrait for story %s",
            story.id,
        )
        return None, None

    prompt = build_portrait_only_prompt(story)
    logger.info(
        "Cover method=template_v1 portrait-only DALL-E story=%s author=%s prompt_words=%s",
        story.id,
        story.first_name,
        len(prompt.split()),
    )
    return generate_ai_cover_image(
        title=_active_title(story),
        story_type=story.story_type.value if story.story_type else "confession",
        author_name=(story.first_name or "Anonymous").strip() or "Anonymous",
        image_prompt=prompt,
        gender=story.gender,
    )


def _generate_template_cover(
    db: Session,
    story: Story,
    *,
    allow_admin_fallback: bool,
) -> None:
    """Portrait DALL-E → HTML cover_template → PNG → S3; image_source=template_v1."""
    from app.cover_template.render import render_cover_png_sync
    from app.utils.s3 import delete_s3_object, upload_image_to_s3
    from app.utils.story_image_prompt import _apply_admin_default_cover

    portrait_url, portrait_key = _generate_portrait_for_template(story)
    payload = story_to_cover_template_payload(story, photo_url=portrait_url)
    logger.info(
        "Cover method=template_v1 story=%s type=%s author=%s title=%r portrait=%s",
        story.id,
        story.story_type.value if story.story_type else None,
        payload.get("author_name"),
        payload.get("title"),
        bool(portrait_url),
    )

    try:
        png = render_cover_png_sync(payload)
    except Exception:
        logger.exception(
            "cover_template render failed for story %s (method=template_v1)",
            story.id,
        )
        if portrait_key:
            delete_s3_object(portrait_key)
        if allow_admin_fallback:
            _apply_admin_default_cover(db, story)
        return

    if not png:
        logger.warning(
            "cover_template returned empty PNG for story %s (method=template_v1)",
            story.id,
        )
        if portrait_key:
            delete_s3_object(portrait_key)
        if allow_admin_fallback:
            _apply_admin_default_cover(db, story)
        return

    previous_key = story.cover_image_key
    cover_url, cover_key = upload_image_to_s3(png, file_extension="png")
    if cover_url:
        story.cover_image_url = cover_url
        story.cover_image_key = cover_key
        story.image_source = ImageSource.template_v1
        logger.info(
            "Cover saved method=template_v1 image_source=%s story=%s key=%s",
            ImageSource.template_v1.value,
            story.id,
            cover_key,
        )
        # Final cover replaces both the prior cover and the intermediate portrait.
        if previous_key and previous_key != cover_key:
            delete_s3_object(previous_key)
        if portrait_key and portrait_key != cover_key:
            delete_s3_object(portrait_key)
        return

    logger.warning(
        "S3 upload failed for template cover story %s (method=template_v1)",
        story.id,
    )
    if portrait_key:
        delete_s3_object(portrait_key)
    if allow_admin_fallback:
        _apply_admin_default_cover(db, story)


def try_generate_story_cover(
    db: Session,
    story: Story,
    *,
    image_prompt: Optional[str],
    allow_admin_fallback: bool = True,
    replace_member_cover: bool = False,
    force_rebuild: bool = False,
) -> None:
    """Route cover generation by ``COVER_GENERATION_METHOD``.

    Same signature as ``app.utils.story_image_prompt.try_generate_story_cover``.
    Default (``dalle``) delegates unchanged to that function.
    """
    # Shared guard: leave member uploads alone unless explicitly replacing.
    if (
        story.image_source == ImageSource.user_uploaded
        and story.cover_image_url
        and not replace_member_cover
    ):
        return

    if uses_template_pipeline(story):
        _generate_template_cover(
            db, story, allow_admin_fallback=allow_admin_fallback
        )
        return

    # Default / non-confession under template flag: original full-collage DALL-E path.
    from app.utils import story_image_prompt as dalle_path

    logger.info(
        "Cover method=dalle story=%s type=%s image_source_will_be=ai_generated",
        story.id,
        story.story_type.value if story.story_type else None,
    )
    dalle_path.try_generate_story_cover(
        db,
        story,
        image_prompt=image_prompt,
        allow_admin_fallback=allow_admin_fallback,
        replace_member_cover=replace_member_cover,
        force_rebuild=force_rebuild,
    )


def cover_regeneration_worker(story_ids: list[str]) -> None:
    """Bulk regen worker that respects ``COVER_GENERATION_METHOD``."""
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
                    "Cover regen finished for %s method=%s source=%s url=%s",
                    story.id,
                    cover_generation_method(),
                    story.image_source,
                    bool(story.cover_image_url),
                )
            except Exception:
                db.rollback()
                logger.exception("Cover regen failed for story %s", story_id)
    finally:
        db.close()
