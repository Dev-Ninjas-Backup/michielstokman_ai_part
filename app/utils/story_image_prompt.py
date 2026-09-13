"""
Build and resolve DALL-E prompts for per-story cover artwork.

The story LLM is supposed to return an IMAGE_PROMPT block, but when it does not we
build one from the finished story text so every cover reflects that story.
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


def ensure_confession_photography_style(prompt: str, story: Story) -> str:
    """Append the fixed confession photo style if missing (P1 or P2 output)."""
    from app.model.story import StoryType
    from app.utils.prompts import CONFESSION_COVER_PHOTOGRAPHY_STYLE

    story_type = getattr(story, "story_type", None)
    if story_type != StoryType.confession:
        return prompt
    text = (prompt or "").strip()
    if not text:
        return text
    # Already present (Grok followed instructions) — do not duplicate.
    if "Photography style (always apply, non-negotiable)" in text:
        return text
    return f"{text} {CONFESSION_COVER_PHOTOGRAPHY_STYLE}".strip()


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


def _cover_art_direction(story: Story) -> str:
    from app.utils.prompts import STORY_HUMAN_TEMPLATE, cover_identity_template_vars

    raw = STORY_HUMAN_TEMPLATE.split("IMAGE_PROMPT:", 1)[1].split("STORY:", 1)[0].strip()
    return raw.format(
        **cover_identity_template_vars(story.first_name, story.gender, story.location)
    )


def brief_story_mood_scene(story: Story) -> str:
    """One-sentence mood/scene line for the portrait-only DALL-E prompt."""
    situation = re.sub(r"\s+", " ", (story.situation or "").strip())
    background = re.sub(r"\s+", " ", (story.background or "").strip())
    title = (story.title or story.member_title or story.ai_generated_title or "").strip()

    if situation:
        sentence = situation
    elif background:
        sentence = background
    elif title:
        sentence = f"a quiet, emotionally charged moment reflecting the confession titled '{title}'"
    else:
        sentence = "a quiet moment of emotional honesty and release"

    # Keep to roughly one sentence.
    if "." in sentence:
        sentence = sentence.split(".", 1)[0].strip() + "."
    if len(sentence) > 220:
        sentence = sentence[:217].rstrip() + "..."
    if not sentence.endswith("."):
        sentence += "."
    return sentence


_SCENE_SETTING_RE = re.compile(
    r"\b("
    r"window|windowsill|balcony|railing|harbor|harbour|dock|pier|coast|beach|shore|"
    r"street|alley|cafe|café|kitchen|bedroom|bed|sofa|chair|table|doorway|stairs|"
    r"bridge|park|forest|mountain|field|campfire|car|train|hotel|bathroom|mirror|"
    r"rooftop|apartment|flat|studio|church|bar|club|office"
    r")\b",
    re.I,
)
_SCENE_WEATHER_RE = re.compile(
    r"\b("
    r"dusk|dawn|sunset|sunrise|night|midnight|morning|afternoon|golden hour|"
    r"rain|rainy|rain-streaked|storm|fog|mist|snow|winter|cold|humid|overcast|"
    r"cloudy|wind|windy"
    r")\b",
    re.I,
)
_SCENE_PROP_RE = re.compile(
    r"\b("
    r"coat|jacket|scarf|notebook|letter|note|photo|bag|cup|glass|wine|cigarette|"
    r"phone|book|keys|umbrella|blanket|sweater|dress|shirt"
    r")\b",
    re.I,
)

_CELEBRATION_RE = re.compile(
    r"\b(celebrat\w*|triumphant|arms?\s+out|release|liberat\w*|euphori\w*|"
    r"face\s+(?:to|toward)\s+(?:the\s+)?sky|finally\s+free)\b",
    re.I,
)
_MULTI_PERSON_RE = re.compile(
    r"\b("
    r"partner|lover|boyfriend|girlfriend|husband|wife|spouse|fiancé|fiancee|"
    r"couple|together|embrace|embracing|kiss(?:ing|ed)?|holding\s+(?:him|her|each\s+other)|"
    r"in\s+(?:his|her|their)\s+arms|we\s+(?:lay|lie|sat|sit|stood|stand|danced|kiss)|"
    r"two\s+people|another\s+person|with\s+(?:him|her|them)|beside\s+(?:him|her|them)"
    r")\b",
    re.I,
)
_INTIMACY_RE = re.compile(
    r"\b("
    r"bed|bedroom|sheets|undress|naked|bare|skin|kiss|embrace|desire|lust|"
    r"arousal|intimate|intimacy|sexual|sex|lover|afterglow|shirtless|lingerie|"
    r"collarbone|shoulder|breath(?:ing)?\s+on|touch(?:ing|ed)?"
    r")\b",
    re.I,
)
# Habitual stock pose the model overuses — always banned unless story says otherwise.
_NECK_BAN = (
    "Neck and head carriage (required): keep the neck naturally aligned with the spine — "
    "upright or only a slight natural turn. Do NOT use a bent/crooked neck, chin tucked "
    "into chest, or the cliché soft head-tilt / three-quarter downturned gaze that repeats "
    "across covers. Vary head angle from story action (looking at a person, a window, a "
    "phone, the horizon at eye level, laughing mid-motion) — not a default coy tilt."
)


def _story_blob(story: Story, *, story_chars: int = 900) -> str:
    return " ".join(
        p
        for p in (
            re.sub(r"\s+", " ", (story.situation or "").strip()),
            re.sub(r"\s+", " ", (story.background or "").strip()),
            re.sub(r"\s+", " ", (story.hero_hook or "").strip()),
            re.sub(
                r"\s+",
                " ",
                (story.story_text or story.story_input or "").strip(),
            )[:story_chars],
        )
        if p
    )


def _story_allows_multi_person(story: Story) -> bool:
    return bool(_MULTI_PERSON_RE.search(_story_blob(story)))


def _story_wants_semi_explicit(story: Story) -> bool:
    if bool(getattr(story, "high_intensity", False)):
        return True
    return bool(_INTIMACY_RE.search(_story_blob(story)))


def portrait_narrative_moment(story: Story) -> str:
    """Story-first moment the photograph must depict (not a generic mood line)."""
    situation = re.sub(r"\s+", " ", (story.situation or "").strip())
    excerpt = re.sub(
        r"\s+", " ", (story.story_text or story.story_input or "").strip()
    )
    # Prefer situation + first ~2 sentences of story body for a concrete beat.
    beats: list[str] = []
    if situation:
        beats.append(situation.rstrip(".") + ".")
    if excerpt:
        parts = re.split(r"(?<=[.!?])\s+", excerpt)
        for sent in parts:
            s = sent.strip()
            if not s:
                continue
            # Skip pure meta / address-to-reader lines if possible.
            if re.match(r"^(dear |hi |hello |my name)", s, re.I):
                continue
            beats.append(s if s.endswith((".", "!", "?")) else s + ".")
            if len(beats) >= 3:
                break
    if not beats:
        beats.append(brief_story_mood_scene(story))

    moment = " ".join(beats)
    if len(moment) > 480:
        moment = moment[:477].rstrip() + "..."
    return (
        "Narrative moment to depict (mandatory — invent nothing that contradicts this): "
        f"{moment} "
        "The photograph must read as THIS confession's scene, not a reused stock cover pose "
        "or empty sky portrait."
    )


def portrait_scene_detail(story: Story) -> str:
    """Compact story-grounded setting/props/weather cues for portrait prompts.

    Pulls concrete nouns from situation, background, and a short story excerpt.
    Kept ~40–60 words; English; never asks for text in the image.
    """
    blob = _story_blob(story, story_chars=500)
    if not blob:
        return (
            "Scene detail: intimate lived-in environment with tangible surfaces and "
            "practical light matching the subject's location — no empty void."
        )

    settings = list(dict.fromkeys(m.group(1).lower() for m in _SCENE_SETTING_RE.finditer(blob)))
    weather = list(dict.fromkeys(m.group(1).lower() for m in _SCENE_WEATHER_RE.finditer(blob)))
    props = list(dict.fromkeys(m.group(1).lower() for m in _SCENE_PROP_RE.finditer(blob)))

    location = (
        (story.location or "").strip()
        or ", ".join(
            p for p in ((story.city or "").strip(), (story.country or "").strip()) if p
        )
    )

    parts: list[str] = []
    if location:
        parts.append(f"Place cues for {location}.")
    if settings:
        parts.append("Visible setting: " + ", ".join(settings[:4]) + ".")
    if weather:
        parts.append("Time/weather: " + ", ".join(weather[:3]) + ".")
    if props:
        parts.append("Include prop/clothing cue if natural: " + ", ".join(props[:3]) + ".")
    if not settings and not weather and not props:
        mood = brief_story_mood_scene(story)
        parts.append(f"Ground the frame in: {mood.rstrip('.')}.")

    parts.append(
        "Build an aesthetic, cinematic environment unique to this story "
        "(architecture, furniture, weather, light) — no empty sky-only backdrop; "
        "no readable text in the image."
    )
    text = "Scene detail: " + " ".join(parts)
    if len(text) > 420:
        text = text[:417].rstrip() + "..."
    return text


def portrait_cast_instruction(story: Story) -> str:
    """Solo vs multi-person cast from the confession text."""
    if _story_allows_multi_person(story):
        return (
            "Cast (story-required): Include a second person when the confession involves "
            "a partner or shared moment — visible interaction (embrace, conversation, "
            "walking together, sitting close). The narrator remains the primary subject "
            "and stays fully readable in frame; the other person may be partial, behind, "
            "or secondary. Do not invent a crowd."
        )
    return (
        "Cast: Narrator alone unless the story clearly includes another person. "
        "Do not add random bystanders."
    )


def portrait_intimacy_instruction(story: Story) -> str:
    """Tasteful semi-explicit cues when intensity/intimacy is story-true."""
    if not _story_wants_semi_explicit(story):
        return (
            "Tone / wardrobe: Keep clothing and body language honest to the story — "
            "everyday or editorial, not gratuitously revealing."
        )
    return (
        "Tone / wardrobe (story allows intimate / high-intensity heat): Suggest adult "
        "intimacy aesthetically — close proximity, rumpled sheets or open collar, bare "
        "shoulders or collarbones, skin catching light, charged stillness or touch — "
        "tasteful editorial, not pornographic. No graphic sex acts, no full frontal "
        "nudity, no fetish framing. Stay artistic and story-motivated."
    )


def portrait_pose_instruction(story: Story) -> str:
    """Story-derived pose/body-language block for the portrait-only prompt.

    Prefers concrete physical actions from situation/background over the
    collage path's default arms-out / face-skyward euphoria pose. Actively
    bans the bent-neck / soft-tilt stock pose that repeats across covers.
    """
    lower = _story_blob(story).lower()

    actions: list[str] = []
    if re.search(r"\bhold(?:ing|s)?\b.{0,40}\b(letter|note|paper|photo|bag|cup|coat)\b", lower):
        m = re.search(
            r"\bhold(?:ing|s)?\b.{0,40}\b(letter|note|paper|photo|bag|cup|coat)\b",
            lower,
        )
        actions.append(f"holding a {m.group(1)}" if m else "holding an object from the scene")
    elif re.search(r"\bhold(?:ing|s)?\b", lower):
        actions.append("holding the object described in the scene")
    if re.search(r"\bdanc(?:ing|e|ed)\b", lower):
        actions.append("mid-motion dancing or moving to music")
    if re.search(r"\brun(?:ning|s)?\b|\bjogg(?:ing|ed)?\b", lower):
        actions.append("in motion — running or brisk walking")
    if re.search(r"\bsitt?(?:ing|s|en)?\b|\bsat\b", lower):
        actions.append("sitting")
    if re.search(r"\bwalk(?:ing|s|ed)?\b", lower):
        actions.append("walking")
    if re.search(r"\blean(?:ing|s|ed)?\b|\brailing\b|\bbalcony\b", lower):
        actions.append("leaning on a railing or balcony edge")
    if re.search(r"\bstand(?:ing|s)?\b|\bdock\b|\bplatform\b|\bharbour\b|\bharbor\b", lower):
        actions.append("standing in place within the scene")
    if re.search(r"\bembrac(?:e|ing|ed)\b|\bin\s+(?:his|her|their)\s+arms\b", lower):
        actions.append("in an embrace matching the story")
    if re.search(r"\bkiss(?:ing|ed)?\b", lower):
        actions.append("close faces / almost-kiss or kiss as the story implies")
    if re.search(r"\blook(?:ing)?\s+out\b|\bgazing\b|\bstaring\b", lower):
        actions.append("gaze directed into the scene at eye level (not chin-down)")
    # Only when eyes/contemplation are explicit — do NOT trigger on lone "quiet".
    if re.search(r"\beyes?\s+closed\b|\bcontemplat\w*\b|\bthoughtful\b|\bmeditat\w*\b", lower):
        actions.append("expression matches contemplation — eyes soft or closed if written")
    if re.search(r"\blaugh(?:ing|ed|s)?\b|\bsmil(?:ing|ed|e)\b", lower):
        actions.append("natural laugh or smile mid-moment")
    if re.search(r"\bbreath\b|\bsteam\b|\bwinter\b|\bcold\b", lower):
        actions.append("breath visible in cold air if the setting is cold")

    if actions:
        seen: set[str] = set()
        unique = []
        for a in actions:
            if a not in seen:
                seen.add(a)
                unique.append(a)
        stance = "; ".join(unique[:6])
    else:
        stance = (
            "a dynamic, story-true body posture taken from the narrated action — "
            "change it per confession; never reuse the same soft-tilt stock pose"
        )

    allow_arms_out = bool(_CELEBRATION_RE.search(lower))
    arms_rule = (
        "A triumphant arms-out / face-skyward pose is allowed because the story "
        "explicitly involves release or celebration."
        if allow_arms_out
        else (
            "Do not default to a generic triumphant arms-out pose unless the story "
            "explicitly involves release/celebration. Reflect the story's specific "
            "physical action or stance where one is described."
        )
    )
    grounded = (
        ""
        if allow_arms_out
        else (
            " Physically ground the subject in-frame — sitting on, leaning against, "
            "walking through, or holding something visible — so they do not float in "
            "empty tone."
        )
    )

    return (
        f"Pose / body language (required, story-specific, must vary per story): {stance}. "
        f"{_NECK_BAN} "
        "Body language matches the confession's energy (joyful, tense, intimate, "
        "resolute, exhausted) — do not force the same contemplative template every time. "
        f"{arms_rule}{grounded}"
    )


def build_portrait_only_prompt(story: Story) -> str:
    """Portrait-only DALL-E prompt for COVER_GENERATION_METHOD=template.

    The HTML cover_template owns all collage text/badges/layout. DALL-E only
    produces the person photograph for the photo slot. Reuses
    ``CONFESSION_COVER_PHOTOGRAPHY_LOOK`` (same look source as P1/P2) but does
    **not** inject the collage default arms-out pose — pose comes from the story.
    """
    from app.utils.prompts import (
        CONFESSION_COVER_PHOTOGRAPHY_LOOK,
        CONFESSION_COVER_PHOTOGRAPHY_PORTRAIT_CLOSING,
        CONFESSION_COVER_PORTRAIT_ENVIRONMENT,
    )

    gender = (story.gender or "person").strip().lower() or "person"
    location = (
        (story.location or "").strip()
        or ", ".join(
            p for p in ((story.city or "").strip(), (story.country or "").strip()) if p
        )
        or "an unspecified place"
    )
    if story.age is not None:
        subject = f"a {story.age}-year-old {gender} person"
    else:
        subject = f"a {gender} adult"
    mood = brief_story_mood_scene(story)
    narrative = portrait_narrative_moment(story)
    scene_detail = portrait_scene_detail(story)
    cast = portrait_cast_instruction(story)
    intimacy = portrait_intimacy_instruction(story)
    pose = portrait_pose_instruction(story)
    multi = _story_allows_multi_person(story)
    framing = (
        "Compose as a 4:5 vertical photographic frame with the narrator's full head "
        "and shoulders readable and adequate headroom. "
        + (
            "When a second person is present, keep the narrator dominant and both "
            "figures inside the frame without awkward edge crops."
            if multi
            else "Keep the narrator clearly primary; skip random bystanders."
        )
        + " Show the aesthetic environment around them — do not crop to a face-only void."
    )

    return (
        "Generate a single photographic image, no text, no graphic design elements, "
        "no logos, no borders, no collage — vertical orientation "
        "(portrait aspect ratio, approximately 4:5).\n\n"
        f"Primary subject: {subject}, in {location}. "
        f"Story beat (one line): {mood}\n\n"
        f"{narrative}\n\n"
        f"{scene_detail}\n\n"
        f"{cast}\n\n"
        f"{intimacy}\n\n"
        f"{pose}\n\n"
        f"{CONFESSION_COVER_PORTRAIT_ENVIRONMENT}\n\n"
        f"{framing}\n\n"
        "Anti-repetition: each confession must look different in posture, framing, "
        "and scene — never recycle the same bent-neck contemplative cover formula.\n\n"
        f"{CONFESSION_COVER_PHOTOGRAPHY_LOOK}"
        f"{CONFESSION_COVER_PHOTOGRAPHY_PORTRAIT_CLOSING}\n\n"
        "The photo must fill the entire frame edge-to-edge with no white space, no borders, "
        "no text overlays of any kind."
    )


def build_image_prompt_from_story(story: Story) -> str:
    """Ask the LLM for a story-specific DALL-E prompt after generation completes."""
    from app.model.story import StoryType
    from app.utils.prompts import CONFESSION_COVER_PHOTOGRAPHY_STYLE

    excerpt = (story.story_text or "")[:STORY_EXCERPT_CHARS]
    input_excerpt = (story.story_input or "")[:INPUT_EXCERPT_CHARS]
    tags = ", ".join(story.tags or [])
    growth = ", ".join(story.growth_areas or [])

    confession_style_block = ""
    if story.story_type == StoryType.confession:
        confession_style_block = (
            "\n\nCONFESSION PHOTOGRAPHY STYLE (NON-NEGOTIABLE): "
            "Per-story subject age/gender/location/activity/mood MUST still vary "
            "from the narrated story. Only the photographic treatment is fixed. "
            "Your returned prompt MUST include this exact paragraph verbatim "
            "(append after the scene description; do not rewrite or omit it):\n"
            f"{CONFESSION_COVER_PHOTOGRAPHY_STYLE}\n"
        )

    llm = get_story_llm(temperature=0.8)
    response = llm.invoke(
        "You write image prompts for cover artwork. Return only the prompt text, "
        "with no preamble and no quotes.\n\n"
        f"Story type: {story.story_type.value}\n"
        f"Title: {story.title or 'Untitled'}\n"
        f"Name: {story.first_name or 'Anonymous'}\n"
        f"Location: {story.location or 'unspecified'}\n"
        f"Gender: {story.gender or 'unspecified'}\n"
        f"Sexual orientation: {story.sexual_orientation or 'unspecified'}\n"
        f"Occupation: {story.occupation or 'unspecified'}\n"
        f"Age: {story.age if story.age is not None else 'unspecified'}\n"
        f"Background: {story.background or 'unspecified'}\n"
        f"Personality: {story.personality or 'unspecified'}\n"
        f"Lifestyle: {story.lifestyle or 'unspecified'}\n"
        f"Situation: {story.situation or 'unspecified'}\n"
        f"Themes/tags: {tags or 'none'}\n"
        f"Growth areas: {growth or 'none'}\n\n"
        f"Art direction:\n{_cover_art_direction(story)}\n"
        f"{confession_style_block}\n"
        f"Member's original submission:\n{input_excerpt}\n\n"
        f"Narrated story:\n{excerpt}\n\n"
        "The cover scene must visually reflect THIS specific story — its setting, "
        "mood, and symbols. Do not describe a generic stock scene. "
        f"The tape text MUST read exactly: {story.first_name or 'Anonymous'}. "
        f"The portrait MUST depict a {story.gender or 'unspecified'} person."
    )
    built = response.content.strip()
    return ensure_confession_photography_style(built, story)


def resolve_image_prompt(
    story: Story,
    generated_prompt: Optional[str],
    *,
    force_rebuild: bool = False,
) -> Optional[str]:
    """
    Prefer the IMAGE_PROMPT from story generation; otherwise reuse a stored
    prompt; otherwise build one from the finished story so covers are not
    identical across the library.
    """
    title = story.title or story.member_title or "Untitled"
    author = story.first_name or "Anonymous"

    generated = (generated_prompt or "").strip()
    if generated:
        return ensure_confession_photography_style(
            substitute_cover_placeholders(generated, title=title, author_name=author),
            story,
        )

    stored = (getattr(story, "image_prompt", None) or "").strip()
    if stored and not force_rebuild:
        return ensure_confession_photography_style(
            substitute_cover_placeholders(stored, title=title, author_name=author),
            story,
        )

    if not (story.story_text or "").strip():
        return None

    logger.info(
        "No IMAGE_PROMPT from story generation for story %s; building from story text.",
        story.id,
    )
    built = build_image_prompt_from_story(story)
    if not built:
        return None
    return ensure_confession_photography_style(
        substitute_cover_placeholders(built, title=title, author_name=author),
        story,
    )


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
    force_rebuild: bool = False,
) -> None:
    """
    Generate a unique AI cover for a story.

    During automatic story generation, member uploads are left untouched.
    When the member explicitly requests artwork generation, set
    ``replace_member_cover=True`` so AI art can replace a prior upload.
    ``force_rebuild=True`` skips a stored P1 prompt and runs P2.
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

    resolved_prompt = resolve_image_prompt(
        story, image_prompt, force_rebuild=force_rebuild
    )
    if not resolved_prompt:
        if allow_admin_fallback:
            _apply_admin_default_cover(db, story)
        return

    story.image_prompt = resolved_prompt

    previous_key = story.cover_image_key
    cover_url, cover_key = generate_ai_cover_image(
        title=story.title or story.member_title or "Untitled",
        story_type=story.story_type.value,
        author_name=story.first_name or "Anonymous",
        image_prompt=resolved_prompt,
        gender=story.gender,
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
                    # Reuse a stored P1 prompt when present (cost); identity lock still applies.
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
