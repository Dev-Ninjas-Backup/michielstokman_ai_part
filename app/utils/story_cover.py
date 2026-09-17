"""Cover generation router — DALL-E collage vs HTML cover_template + portrait.

Controlled by ``COVER_GENERATION_METHOD`` (default ``dalle``).

- ``dalle``    → unchanged path in ``story_image_prompt.try_generate_story_cover``
                 (Grok IMAGE_PROMPT / P2 full-collage + ``generate_ai_cover_image``).
                 Sets ``image_source=ai_generated``.
- ``template`` → for *confession* and *meditation* stories:
                 1) portrait-only OpenAI Image API prompt (``build_portrait_only_prompt``)
                 2) Playwright ``cover_template`` with that photo in the tear-hole slot
                 Sets ``image_source=template_v1``.
                 Other story types still use the DALL-E collage path.

Product preference: HTML template + OpenAI portrait in the photo hole (client-approved).
Flip the env var back to ``dalle`` at any time to restore full-collage covers.
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
# Soft ≈ 3–4 lines; hard ≈ 5 lines with location pinned to .left-copy bottom
# and confession max-height 525px (vertically centered between titles & location).
CONFESSION_DESCRIPTION_HARD_LIMIT = 110
CONFESSION_DESCRIPTION_SOFT_LIMIT = 80  # ~4 lines with equal gap above/below
# Fluid wrap inside the beige column (white torn edge ~1000–1050; titles max-width ~880).
# Pack toward HARD so lines fill horizontal space; CSS wraps glyphs within max-width.
# cover.js fitCopyFonts shrinks Edo so long titles stay ≤2 lines; copy stays under photo.
TITLE_LINE_SOFT_LIMIT = 16  # fill the wider beige column
TITLE_LINE_HARD_LIMIT = 22
# Prefer one Cover.set span when copy fits ~2 visual lines — CSS wraps to fill width.
TITLE_MAX_VISUAL_LINES = 2
# Shorter soft wrap keeps each pink line glyph-short so fitCopyFonts can stay ≥60px.
SUBTITLE_LINE_SOFT_LIMIT = 22
SUBTITLE_LINE_HARD_LIMIT = 32
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
    # Template chrome is shared; confession + meditation get type-specific portraits.
    return story.story_type in (StoryType.confession, StoryType.meditation)


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


def _strip_emphasis(text: str) -> str:
    """Remove Grok ``**punch**`` markers for plain cover text."""
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", text or "")
    return re.sub(r"\s+", " ", cleaned.replace("\r\n", "\n")).strip()


def _fill_column_text(
    text: str,
    *,
    per_line: int,
    max_lines: int,
    hard_limit: int,
) -> str:
    """Pack copy to fill the beige column without crossing the torn edge.

    Prefer a **single** Cover.set span sized to ``max_lines * hard_limit`` so
    CSS wraps across the full max-width (avoids skinny stacks like ``THE`` /
    ``IRON`` with unused space to the torn edge). Multi-line packing is only
    a fallback when word-boundary truncation cannot fit the budget.
    """
    cleaned = _strip_emphasis(text)
    if not cleaned:
        return ""
    budget = hard_limit * max_lines
    if len(cleaned) <= budget:
        return cleaned
    # One span truncated at a word boundary — CSS fluid-wraps inside max-width.
    one = truncate_at_last_word(cleaned, budget)
    if one:
        return one
    return _pack_words_to_lines(
        cleaned,
        per_line=per_line,
        max_lines=max_lines,
        hard_limit=hard_limit,
    )


def _active_title(story: Story) -> str:
    """Brush title that fills the beige column; CSS wraps up to the torn edge."""
    raw = (story.title or story.member_title or story.ai_generated_title or "Untitled").strip()
    packed = _fill_column_text(
        raw,
        per_line=TITLE_LINE_SOFT_LIMIT,
        max_lines=TITLE_MAX_VISUAL_LINES,
        hard_limit=TITLE_LINE_HARD_LIMIT,
    )
    return packed or "Untitled"


def _is_complete_sentence(text: str) -> bool:
    """True when copy ends with sentence punctuation and is long enough to ship."""
    cleaned = (text or "").strip()
    return len(cleaned) >= 12 and cleaned.endswith((".", "!", "?"))


def _clause_as_sentence(text: str, hard_limit: int) -> str | None:
    """Promote the longest comma/semicolon clause that fits under ``hard_limit``."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return None
    best: str | None = None
    for sep in (";", ","):
        start = 0
        while True:
            idx = cleaned.find(sep, start)
            if idx < 0:
                break
            start = idx + 1
            if idx < 12:
                continue
            clause = _cleanup_truncated_phrase(cleaned[:idx].strip())
            if not clause or len(clause) < 12:
                continue
            normalized = clause if clause.endswith((".", "!", "?")) else f"{clause}."
            if len(normalized) <= hard_limit and (
                best is None or len(normalized) > len(best)
            ):
                best = normalized
    return best


def _sense_cut_as_sentence(text: str, hard_limit: int) -> str:
    """Word-cut an overlong clause into the most understandable sentence possible.

    Prefers breaking before a clause connector (``while``, ``and``, …) so we do
    not ship adjective fragments like ``…while my scarred.``
    """
    cleaned = re.sub(r"\s+", " ", (text or "").strip()).rstrip(".!?")
    if not cleaned:
        return ""
    if len(cleaned) + 1 <= hard_limit:
        return f"{cleaned}."

    window = cleaned[: hard_limit - 1]
    connectors = (
        " while ",
        " and ",
        " that ",
        " which ",
        " where ",
        " when ",
        " because ",
        " but ",
        " as ",
        " with ",
        " after ",
        " before ",
        " without ",
    )
    best_idx = -1
    lower = window.lower()
    for connector in connectors:
        idx = lower.rfind(connector)
        if idx >= 12:
            best_idx = max(best_idx, idx)
    if best_idx >= 12:
        cut = _cleanup_truncated_phrase(window[:best_idx])
        if cut and len(cut) >= 12:
            return cut if cut.endswith((".", "!", "?")) else f"{cut}."

    cut = _cleanup_truncated_phrase(truncate_at_last_word(cleaned, hard_limit - 1))
    if not cut:
        return ""
    if not cut.endswith((".", "!", "?")):
        cut = f"{cut}."
    return cut if len(cut) <= hard_limit and len(cut) >= 12 else ""


def first_complete_sentence(
    text: str,
    *,
    soft_limit: int = CONFESSION_DESCRIPTION_SOFT_LIMIT,
    hard_limit: int = CONFESSION_DESCRIPTION_HARD_LIMIT,
) -> str:
    """Prefer the *first* complete sentence; never ship a mid-sentence fragment.

    Cover description should open the hook as an understandable sentence —
    not a word-cut of an overlong clause.
    """
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""

    match = re.match(r"^(.{12,}?[.!?])(?:\s|$)", cleaned)
    if match:
        sentence = match.group(1).strip()
        if len(sentence) <= hard_limit:
            return sentence
        # First sentence is too long — try an earlier clause, then any complete
        # sentence within budget. Do not word-cut into an incomplete fragment.
        clause = _clause_as_sentence(sentence, hard_limit)
        if clause:
            return clause
        alt = truncate_at_sentence(cleaned, soft_limit=soft_limit, hard_limit=hard_limit)
        if _is_complete_sentence(alt) and alt != sentence:
            return alt
        sense = _sense_cut_as_sentence(sentence, hard_limit)
        if sense:
            return sense
        return alt if _is_complete_sentence(alt) else sense

    semi = cleaned.find(";")
    if semi >= 12:
        clause = _cleanup_truncated_phrase(cleaned[:semi].strip())
        if clause:
            normalized = clause if clause.endswith((".", "!", "?")) else f"{clause}."
            if len(normalized) <= hard_limit:
                return normalized
            short = _clause_as_sentence(normalized, hard_limit)
            if short:
                return short
            sense = _sense_cut_as_sentence(normalized, hard_limit)
            if sense:
                return sense

    result = truncate_at_sentence(cleaned, soft_limit=soft_limit, hard_limit=hard_limit)
    if _is_complete_sentence(result):
        return result
    return _sense_cut_as_sentence(result or cleaned, hard_limit)


def _split_complete_sentences(text: str) -> list[str]:
    """Split prose into complete .!? sentences (keeps terminal punctuation)."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return []
    parts = re.findall(r"[^.!?]*[.!?]+", cleaned)
    sentences = [p.strip() for p in parts if p.strip()]
    if not sentences:
        return [cleaned] if cleaned else []
    # Trailing fragment without terminal punctuation — keep for sense-cut path.
    consumed = "".join(parts)
    rest = cleaned[len(consumed) :].strip()
    if rest:
        sentences.append(rest)
    return sentences


def pack_cover_confession(
    text: str,
    *,
    soft_limit: int = CONFESSION_DESCRIPTION_SOFT_LIMIT,
    hard_limit: int = CONFESSION_DESCRIPTION_HARD_LIMIT,
) -> str:
    """Pack consecutive complete sentences into human-readable cover body copy.

    Prefer filling toward soft/hard with 1–2+ full sentences rather than a short
    first-sentence stub. Never cuts mid-sentence when another full sentence fits.
    """
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""

    sentences = _split_complete_sentences(cleaned)
    if not sentences:
        return ""

    first = sentences[0]
    # Single sentence (or fragment) — reuse first_complete_sentence / sense-cut.
    if len(sentences) == 1 or not first.endswith((".", "!", "?")):
        return first_complete_sentence(
            cleaned, soft_limit=soft_limit, hard_limit=hard_limit
        )

    if len(first) > hard_limit:
        return first_complete_sentence(
            cleaned, soft_limit=soft_limit, hard_limit=hard_limit
        )

    packed = first
    for nxt in sentences[1:]:
        if not nxt.endswith((".", "!", "?")):
            break
        candidate = f"{packed} {nxt}".strip()
        if len(candidate) > hard_limit:
            break
        packed = candidate
        # Once we have reached soft with at least one sentence, keep appending
        # only while under hard (already gated above).
        if len(packed) >= soft_limit:
            # Prefer one more sentence when it still fits under hard — already
            # handled by the loop; stop after soft is met only if next would
            # overshoot (break above). Continue to take another if it fits.
            continue

    # If still under soft and we only have the first sentence, that is fine —
    # do not invent copy. If first alone is tiny and a second was skipped only
    # because it was a fragment, leave packed as-is.
    return packed


def _subtitle_for_story(story: Story) -> str:
    """Pack a story tagline for a cover subtitle line.

    Unused by ``story_to_cover_template_payload`` since the cover card ships
    the purple title only — kept for callers that still want a packed tagline.
    """
    # None → keep the classic default for layout stability.
    # Explicit "" → allow empty subtitle (pink underline sits under the title).
    tag = getattr(story, "hero_tagline", None)
    if tag is None:
        tag = "A Night That Liberated My Essence"
    # Same packing as persist_hero_hook / public tagline generation.
    return format_two_line_field(
        str(tag),
        SUBTITLE_LINE_HARD_LIMIT,
        wrap_soft_limit=SUBTITLE_LINE_SOFT_LIMIT,
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
        return pack_cover_confession(hook)
    raw = (story.story_text or story.story_input or "").strip()
    if not raw:
        return "A confession about shame, desire and finally choosing me."
    # Hard/soft limits from cover_template/DYNAMIC.md — pack complete sentences.
    return pack_cover_confession(raw)


def story_to_cover_template_payload(
    story: Story,
    *,
    photo_url: str | None = None,
) -> dict:
    """Map story row fields onto cover_template render / Cover.set payload keys."""
    city, country = _split_location(story)
    return {
        "title": _active_title(story),
        # Cover card headline is the purple title only — the public tagline
        # (hero_tagline) stays in the DB and on the details page. Empty string
        # collapses .subtitle in cover_template/styles.css so the pink rule
        # sits under the title.
        "subtitle": "",
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
