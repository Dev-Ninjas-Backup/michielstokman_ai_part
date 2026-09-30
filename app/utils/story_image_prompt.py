"""
Build and resolve DALL-E prompts for per-story cover artwork.

The story LLM is supposed to return an IMAGE_PROMPT block, but when it does not we
build one from the finished story text so every cover reflects that story.
"""
from __future__ import annotations

import json
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
    from app.model.story import StoryType

    kind = "meditation" if story.story_type == StoryType.meditation else "confession"
    situation = re.sub(r"\s+", " ", (story.situation or "").strip())
    background = re.sub(r"\s+", " ", (story.background or "").strip())
    title = (story.title or story.member_title or story.ai_generated_title or "").strip()

    if situation:
        sentence = situation
    elif background:
        sentence = background
    elif title:
        sentence = f"a quiet, emotionally charged moment reflecting the {kind} titled '{title}'"
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
    r"rooftop|apartment|flat|studio|church|bar|club"
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
    r"phone|book|keys|umbrella|blanket|sweater|dress|shirt|heels|lipstick|neon|"
    r"lamplight|streetlight|sheets|pillow|perfume"
    r")\b",
    re.I,
)

# Feeling-arc cues from the confession text (not a single mood keyword).
_EMOTION_RE = re.compile(
    r"\b("
    r"shame|shamed|ashamed|guilt|guilty|desire|desiring|longing|yearning|"
    r"fear|afraid|anxious|anxiety|grief|grieving|lonely|loneliness|"
    r"vulnerable|vulnerability|tender|tenderness|raw|exposed|"
    r"liberat\w*|free(?:dom)?|release|released|catharsis|cathartic|"
    r"daring|bold|wild|reckless|thrill|thrilled|ecstatic|euphori\w*|"
    r"sensual|provocative|hungry|aroused|intimate|intimacy|"
    r"resolute|defiant|defiance|angry|anger|heartbroken|heartbreak|"
    r"quiet|contemplat\w*|thoughtful|hesitant|trembling|relieved|relief|"
    r"choosing\s+me|finally\s+free|told\s+the\s+truth"
    r")\b",
    re.I,
)

_QUIET_VULNERABLE_RE = re.compile(
    r"\b("
    r"quiet|vulnerable|vulnerability|tender|tenderness|grief|lonely|loneliness|"
    r"hesitant|trembling|contemplat\w*|thoughtful|soft|fragile|afraid|shame|ashamed"
    r")\b",
    re.I,
)

_BOLD_OUTWARD_RE = re.compile(
    r"\b("
    r"daring|bold|wild|reckless|thrill|thrilled|neon|club|dance|dancing|"
    r"provocative|liberat\w*|finally\s+free|euphori\w*|celebrat\w*|defiant|defiance"
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

# Broader connection / relationship / shared-experience lexicon. _MULTI_PERSON_RE
# only fires on explicit partner + physical-intimacy wording, which under-casts
# against the warm lifestyle direction (friends, family, festival, group joy).
# Scanned over the story fields AND the STORY BRIEF, so a brief that names
# connection themes still puts a second person (or small group) in frame.
_CONNECTION_RE = re.compile(
    r"\b("
    # relationships
    r"partner|lover|boyfriend|girlfriend|husband|wife|spouse|fianc\w*|"
    r"couple|dating|date\s+night|first\s+date|romance|romantic|married|marriage|"
    # friendship / chosen family
    r"friend|friends|friendship|best\s+friend|companion|confidant\w*|"
    r"buddy|roommate|classmate|soulmate|teammate|housemate|mates|"
    # family
    r"family|families|mother|mum|mom|father|dad|parent|parents|sister|brother|"
    r"sibling|daughter|son|cousin|aunt|uncle|grandmother|grandfather|grandma|"
    r"grandpa|niece|nephew|"
    # shared experience / community / celebration
    r"together|community|gathering|reunion|festival|carnival|parade|celebration|"
    r"party|wedding|ceremony|anniversary|"
    r"we\s+(?:danced|laughed|cried|sang|walked|ran|sat|stood|held|shared|"
    r"travelled|traveled|celebrated)|"
    r"shared|joined|united|hand\s+in\s+hand|side\s+by\s+side|"
    r"each\s+other|one\s+another|"
    # physical connection (non-explicit)
    r"hug|hugging|hugged|embrace|embracing|embraced|"
    r"arm\s+around|arms\s+around|holding\s+hands|"
    r"danc\w*\s+with|sat\s+(?:close|beside|next\s+to)|"
    r"sitting\s+(?:close|beside|next\s+to)|"
    r"with\s+(?:him|her|them)|beside\s+(?:him|her|them)|next\s+to\s+(?:him|her|them)|"
    r"in\s+(?:his|her|their)\s+arms|"
    # group presence. ("company" is deliberately absent — "the rain keeps me
    # company" is an idiom about being alone, not about people in frame.)
    r"group|groups|crowd|crowds|crew|squad|troupe|strangers"
    r")\b",
    re.I,
)

# Subset signalling a small group rather than exactly one other person. Event
# nouns like "wedding"/"party" are deliberately excluded — a couple dancing at
# their own wedding is a pair, not a crowd.
_GROUP_RE = re.compile(
    r"\b("
    r"group|groups|friends|friend\s+group|crew|squad|troupe|crowd|crowds|"
    r"festival|festivals|carnival|parade|"
    r"reunion|gathering|community|team|strangers|family|families"
    r")\b",
    re.I,
)

# Genuine aloneness — keeps solo portraits for stories about solitude and
# individual reflection. Deliberately aloneness NOUNS only: reflective words such
# as "contemplative" describe a mood, not the absence of other people, and would
# otherwise suppress a second person in stories that clearly have one.
_SOLITUDE_RE = re.compile(
    r"\b("
    r"alone|lonely|loneliness|solitude|solitary|solo|"
    r"by\s+myself|on\s+my\s+own|my\s+own\s+company|"
    r"isolated|isolation|withdrawn|unaccompanied|"
    r"no\s+one\s+(?:else|around)|nobody\s+else"
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


def _cast_scan_text(story: Story, brief_text: str | None = None) -> str:
    """Story fields plus the STORY BRIEF, minus the brief's "Do not invent:" clause.

    The brief's label naming and its "Do not invent" list are dropped because that
    clause enumerates what must NOT appear in the frame — scanning it would invert
    its meaning ("Do not invent: other people" would cast a second person).
    """
    parts = [_story_blob(story)]
    if brief_text:
        text = brief_text
        marker = "Do not invent:"
        idx = text.find(marker)
        if idx >= 0:
            end = text.find("\n", idx)
            text = text[:idx] + (text[end:] if end >= 0 else "")
        # Drop the "STORY BRIEF (...)/STORY ANALYSIS (...)" label line too — its
        # parenthetical mentions the story type, not a person.
        text = re.sub(r"\bSTORY (?:BRIEF|ANALYSIS) \([^)]*\):", " ", text)
        parts.append(text)
    return " ".join(p for p in parts if p)


def _distinct_matches(pattern: re.Pattern[str], text: str) -> set[str]:
    return {m.group(0).lower() for m in pattern.finditer(text)}


def _cast_mode(story: Story, brief_text: str | None = None) -> str:
    """Portrait cast size: ``"solo"``, ``"pair"``, or ``"group"``.

    Explicit partner/intimacy wording (``_MULTI_PERSON_RE``) still wins, but is now
    joined by the broader connection lexicon. Genuine aloneness outweighs both, so
    "alone, remembering my husband" stays a solo portrait.
    """
    text = _cast_scan_text(story, brief_text)
    explicit = bool(_MULTI_PERSON_RE.search(text))
    connection = _distinct_matches(_CONNECTION_RE, text)
    solitude = _distinct_matches(_SOLITUDE_RE, text)

    if len(solitude) > len(connection):
        return "solo"
    if explicit or len(connection) > len(solitude):
        return "group" if _distinct_matches(_GROUP_RE, text) else "pair"
    return "solo"


def _story_allows_multi_person(story: Story, brief_text: str | None = None) -> bool:
    return _cast_mode(story, brief_text) != "solo"


def _story_wants_semi_explicit(story: Story) -> bool:
    if bool(getattr(story, "high_intensity", False)):
        return True
    return bool(_INTIMACY_RE.search(_story_blob(story)))


def portrait_emotional_state(story: Story) -> str:
    """Feeling-arc line from the story — not a single mood keyword."""
    from app.model.story import StoryType

    kind = "meditation" if story.story_type == StoryType.meditation else "confession"
    blob = _story_blob(story, story_chars=700)
    lower = blob.lower()
    emotions = list(dict.fromkeys(m.group(1).lower() for m in _EMOTION_RE.finditer(blob)))

    quiet = bool(_QUIET_VULNERABLE_RE.search(lower))
    bold = bool(_BOLD_OUTWARD_RE.search(lower) or _CELEBRATION_RE.search(lower))
    intimate = bool(_INTIMACY_RE.search(lower)) or bool(
        getattr(story, "high_intensity", False)
    )

    # Register: match the story's real emotional content (never force intensity).
    if quiet and not bold:
        register = (
            "quiet, vulnerable, and inwardly honest — do not force wild or "
            "provocative energy onto this moment"
        )
    elif bold and not quiet:
        register = (
            "outward, daring, and liberating — allow sensual, energetic, or "
            "provocative heat where the story supports it"
        )
    elif intimate and not quiet:
        register = (
            "intimate and emotionally charged — sensual stillness or charged "
            "proximity matching the story's heat"
        )
    elif quiet and bold:
        register = (
            "tension between vulnerability and daring release — hold both poles "
            "honestly without flattening into a stock mood"
        )
    else:
        register = (
            f"emotionally specific to this {kind}'s arc — match its real "
            "emotional register without inventing intensity the text does not carry"
        )

    if emotions:
        arc = ", ".join(emotions[:6])
        return (
            f"Emotional state (feeling arc of THIS {kind}): the narrator moves "
            f"through {arc}. Register: {register}."
        )

    mood = brief_story_mood_scene(story).rstrip(".")
    return (
        f"Emotional state (feeling arc of THIS {kind}): grounded in "
        f"\"{mood}\" — capture that specific emotional truth, not a generic mood "
        f"label. Register: {register}."
    )


def portrait_narrative_moment(story: Story) -> str:
    """Story-first moment the photograph must depict (not a generic mood line)."""
    from app.model.story import StoryType

    kind = "meditation" if story.story_type == StoryType.meditation else "confession"
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
        f"The photograph must read as THIS {kind}'s scene, not a reused stock cover pose "
        "or empty sky portrait."
    )


def portrait_story_analysis(story: Story) -> str:
    """Labeled STORY ANALYSIS: emotion + distinctive visuals + atmosphere.

    Extends the older scene-detail regex extraction with explicit labels so the
    model cannot reduce the submission to age+gender+location alone.
    """
    from app.model.story import StoryType

    kind = "meditation" if story.story_type == StoryType.meditation else "confession"
    blob = _story_blob(story, story_chars=1800)
    emotional = portrait_emotional_state(story)

    if not blob:
        return (
            f"STORY ANALYSIS (from the complete {kind} — invent nothing that "
            "contradicts it):\n"
            f"{emotional}\n"
            f"Distinctive visual details from the {kind}: intimate lived-in "
            "environment with tangible surfaces and practical light matching the "
            "subject's location — no empty void.\n"
            "Atmosphere: sensory environment honest to the story's place and hour; "
            "no empty sky-only backdrop; no readable text in the image."
        )

    settings = list(
        dict.fromkeys(m.group(1).lower() for m in _SCENE_SETTING_RE.finditer(blob))
    )
    weather = list(
        dict.fromkeys(m.group(1).lower() for m in _SCENE_WEATHER_RE.finditer(blob))
    )
    props = list(
        dict.fromkeys(m.group(1).lower() for m in _SCENE_PROP_RE.finditer(blob))
    )

    location = (
        (story.location or "").strip()
        or ", ".join(
            p for p in ((story.city or "").strip(), (story.country or "").strip()) if p
        )
    )

    visual_bits: list[str] = []
    if location:
        visual_bits.append(f"place cues for {location}")
    if settings:
        visual_bits.append("setting: " + ", ".join(settings[:5]))
    if props:
        visual_bits.append(
            "objects/clothing/actions named in the text: " + ", ".join(props[:5])
        )
    if not settings and not props:
        mood = brief_story_mood_scene(story).rstrip(".")
        visual_bits.append(f"ground the frame in: {mood}")

    if weather:
        atmosphere = (
            "time of day / weather / sensory environment from the submission: "
            + ", ".join(weather[:4])
            + " — make air, light, and temperature readable in-frame"
        )
    else:
        atmosphere = (
            "sensory environment honest to the story's place and hour "
            "(practical light, air, temperature) — never a flat studio void"
        )

    visuals = "; ".join(visual_bits)
    text = (
        f"STORY ANALYSIS (from the complete {kind} — invent nothing that "
        "contradicts it):\n"
        f"{emotional}\n"
        f"Distinctive visual details from the {kind}: {visuals}. "
        "Use these concrete narrative elements — not a generic age+gender+location portrait.\n"
        f"Atmosphere: {atmosphere}. No empty sky-only backdrop; no readable text in the image."
    )
    if len(text) > 1100:
        cut = text[:1097].rsplit(" ", 1)[0].rstrip()
        text = cut + "..."
    return text


def build_portrait_story_brief(story: Story, *, use_llm: bool = True) -> str:
    """Deep cover brief for the template photo slot — heuristic + optional LLM.

    The analysis model receives the COMPLETE available story text (plus title,
    hero hook, tags, situation, background) and transforms it into a concise
    visual brief. The brief — never the full story — drives portrait
    generation. Falls back to the type-aware ``portrait_story_analysis``
    heuristic when the LLM is unavailable or fails.
    """
    from app.model.story import StoryType

    heuristic = portrait_story_analysis(story)
    if not use_llm or not (settings.XAI_API_KEY or "").strip():
        logger.info(
            "Portrait brief path=heuristic story=%s reason=no_llm_or_disabled",
            getattr(story, "id", None),
        )
        return heuristic

    kind = "meditation" if story.story_type == StoryType.meditation else "confession"
    energy = (
        "inward, reflective, contemplative, intimate, emotionally layered, focused "
        "on the inner world"
        if story.story_type == StoryType.meditation
        else "outward, expressive, daring, liberating when the content earns it"
    )
    # Complete story text — stories are capped at 8,000 chars on save, so the
    # analysis model sees the whole piece, not an excerpt.
    full_text = (story.story_text or story.story_input or "").strip()
    hook = (getattr(story, "hero_hook", None) or "").strip()
    situation = (story.situation or "").strip()
    background = (story.background or "").strip()
    title = (
        story.title or story.member_title or getattr(story, "ai_generated_title", None) or ""
    ).strip()
    tags = ", ".join(getattr(story, "tags", None) or [])
    location = (story.location or story.city or "").strip()

    try:
        llm = get_story_llm(temperature=0.35)
        response = llm.invoke(
            "You analyse TTL cover photography briefs. You are given the COMPLETE "
            f"{kind} and must transform it into a concise visual brief for a single "
            "portrait photograph. Return ONLY plain text with these exact labeled "
            "lines (no markdown, no preamble, each line concise):\n"
            "Emotional register: ... (the narrator's actual emotional state and tension)\n"
            "Setting: ... (the story's specific place and time)\n"
            "Atmosphere: ... (light, weather, air, hour — from the story)\n"
            "Distinctive visuals: ... (2-4 concrete props, garments, gestures, or "
            "motifs named in the text)\n"
            "Do not invent: ... (what must not appear)\n"
            "The brief must capture THIS submission's specific visual and emotional "
            "truth — never a generic age+gender+location portrait.\n\n"
            f"Story type: {kind} — energy should feel {energy} when the story "
            "supports it (guiding principle, never forced).\n"
            f"Title: {title or 'untitled'}\n"
            f"Age: {story.age if story.age is not None else 'unspecified'}; "
            f"gender: {story.gender or 'unspecified'}; "
            f"location: {location or 'unspecified'}.\n"
            f"Tags: {tags or 'none'}\n"
            f"Situation: {situation or 'n/a'}\n"
            f"Background: {background or 'n/a'}\n"
            f"Hero hook: {hook or 'n/a'}\n"
            f"Complete {kind} text:\n{full_text or 'n/a'}\n"
        )
        content = (getattr(response, "content", None) or str(response) or "").strip()
        if len(content) < 40 or "Emotional register" not in content:
            logger.warning(
                "Portrait brief path=heuristic story=%s reason=malformed_llm_output",
                getattr(story, "id", None),
            )
            return heuristic
        brief = (
            f"STORY BRIEF (LLM analysis of the complete {kind} — invent nothing "
            f"that contradicts the text):\n{content}"
        )
        if len(brief) > 1400:
            brief = brief[:1397].rsplit(" ", 1)[0].rstrip() + "..."
        logger.info(
            "Portrait brief path=llm story=%s kind=%s brief_chars=%s",
            getattr(story, "id", None),
            kind,
            len(brief),
        )
        return brief
    except Exception:
        logger.warning(
            "Portrait brief path=heuristic story=%s reason=llm_failed",
            getattr(story, "id", None),
            exc_info=True,
        )
        return heuristic


def portrait_scene_detail(story: Story) -> str:
    """Compact story-grounded setting/props/weather cues for portrait prompts.

    Kept for callers/tests; full labeled analysis lives in ``portrait_story_analysis``.
    Pulls concrete nouns from situation, background, and a short story excerpt.
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


def portrait_cast_instruction(
    story: Story,
    *,
    brief_text: str | None = None,
    cast_mode: str | None = None,
) -> str:
    """Solo vs pair vs small-group cast from the story text and STORY BRIEF."""
    mode = cast_mode or _cast_mode(story, brief_text)

    if mode == "group":
        return (
            "Cast (story-required): Include a small group — the narrator plus two or "
            "three other people from the story (friends, family, or companions) sharing "
            "the moment: laughing together, gathered around a table, walking side by "
            "side, or celebrating as one. The narrator remains the primary subject and "
            "stays fully readable in frame; the others may be partial, behind, or "
            "secondary. Keep it an intimate group, not an anonymous crowd — do not fill "
            "the frame with strangers."
        )
    if mode == "pair":
        return (
            "Cast (story-required): Include a second person when the story involves a "
            "partner, friend, family member, or shared moment — visible interaction "
            "(embrace, conversation, walking together, sitting close, laughing "
            "together). The narrator remains the primary subject and stays fully "
            "readable in frame; the other person may be partial, behind, or secondary. "
            "Do not invent a crowd."
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
    from app.model.story import StoryType

    kind = "meditation" if story.story_type == StoryType.meditation else "confession"
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
            f"change it per {kind}; never reuse the same soft-tilt stock pose"
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
        "Body language matches the story's energy (joyful, tense, intimate, "
        "resolute, exhausted) — do not force the same contemplative template every time. "
        f"{arms_rule}{grounded}"
    )


def _portrait_prompt_char_budget() -> int | None:
    """Max final prompt length for the configured OpenAI image model.

    gpt-image family accepts long prompts; dall-e-3 rejects >4,000 chars.
    Returns None when no trim is needed (default gpt-image models).
    """
    model = (settings.OPENAI_IMAGE_MODEL or "gpt-image-2").strip().lower()
    if model.startswith("dall-e"):
        return 3900
    return None


def _trim_prompt_to_budget(prompt: str, budget: int | None) -> str:
    """Compact boilerplate, never story-specific blocks, to fit ``budget``."""
    if budget is None or len(prompt) <= budget:
        return prompt
    # Drop blocks from the least story-critical end first: the anti-repetition
    # line, then the framing block. Never touch narrative/analysis/energy.
    drop_markers = (
        "Anti-repetition: each confession",
        "Anti-repetition: each meditation",
    )
    for marker in drop_markers:
        if len(prompt) <= budget:
            break
        start = prompt.find(marker)
        if start >= 0:
            end = prompt.find("\n\n", start)
            end = len(prompt) if end < 0 else end
            prompt = prompt[:start] + prompt[end:].lstrip("\n")
    if len(prompt) <= budget:
        return prompt
    # Still over: word-boundary trim (story blocks sit at the front).
    return prompt[: max(0, budget - 3)].rsplit(" ", 1)[0].rstrip() + "..."


def build_portrait_only_prompt(story: Story, *, use_llm_brief: bool = True) -> str:
    """Portrait-only OpenAI prompt for COVER_GENERATION_METHOD=template photo slot.

    The HTML cover_template owns all collage text/badges/layout. OpenAI Images only
    produces the person photograph for the tear-hole. Confession vs meditation
    energy and TTL LOOK/anti-AI are applied from brand constants.
    """
    from app.model.story import StoryType
    from app.utils.prompts import (
        CONFESSION_COVER_ANTI_AI_LOOK,
        CONFESSION_COVER_BRAND_COLLECTION,
        CONFESSION_COVER_ENERGY,
        CONFESSION_COVER_PHOTOGRAPHY_LOOK_V2,
        CONFESSION_COVER_PHOTOGRAPHY_PORTRAIT_CLOSING_V2,
        CONFESSION_COVER_PORTRAIT_ENVIRONMENT,
        MEDITATION_COVER_ANTI_AI_LOOK,
        MEDITATION_COVER_BRAND_COLLECTION,
        MEDITATION_COVER_ENERGY,
        MEDITATION_COVER_PHOTOGRAPHY_LOOK,
        MEDITATION_COVER_PHOTOGRAPHY_PORTRAIT_CLOSING,
        MEDITATION_COVER_PORTRAIT_ENVIRONMENT,
    )

    is_meditation = story.story_type == StoryType.meditation
    if is_meditation:
        energy = MEDITATION_COVER_ENERGY
        look = MEDITATION_COVER_PHOTOGRAPHY_LOOK
        closing = MEDITATION_COVER_PHOTOGRAPHY_PORTRAIT_CLOSING
        environment = MEDITATION_COVER_PORTRAIT_ENVIRONMENT
        brand = MEDITATION_COVER_BRAND_COLLECTION
        anti_ai = MEDITATION_COVER_ANTI_AI_LOOK
        kind = "meditation"
    else:
        energy = CONFESSION_COVER_ENERGY
        look = CONFESSION_COVER_PHOTOGRAPHY_LOOK_V2
        closing = CONFESSION_COVER_PHOTOGRAPHY_PORTRAIT_CLOSING_V2
        environment = CONFESSION_COVER_PORTRAIT_ENVIRONMENT
        brand = CONFESSION_COVER_BRAND_COLLECTION
        anti_ai = CONFESSION_COVER_ANTI_AI_LOOK
        kind = "confession"

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
    analysis = build_portrait_story_brief(story, use_llm=use_llm_brief)
    # Cast reads the brief as well as the story, so connection / friendship /
    # shared-experience themes the brief surfaces widen the frame beyond the
    # explicit partner-and-intimacy regexes. Computed once so the framing block
    # and the cast block can never disagree.
    cast_mode = _cast_mode(story, analysis)
    cast = portrait_cast_instruction(story, cast_mode=cast_mode)
    intimacy = portrait_intimacy_instruction(story)
    pose = portrait_pose_instruction(story)
    if cast_mode == "group":
        framing_people = (
            "Keep the narrator dominant and the whole small group inside the frame "
            "without awkward edge crops."
        )
    elif cast_mode == "pair":
        framing_people = (
            "When a second person is present, keep the narrator dominant and both "
            "figures inside the frame without awkward edge crops."
        )
    else:
        framing_people = "Keep the narrator clearly primary; skip random bystanders."
    framing = (
        "Compose as a 4:5 vertical photographic frame with the narrator's full head "
        "and shoulders readable and adequate headroom. "
        + framing_people
        + " Show the aesthetic environment around them — do not crop to a face-only void."
    )
    anti_repeat = (
        "Anti-repetition: each meditation must look different in posture, framing, "
        "and scene — never recycle the same soft contemplative stock formula."
        if is_meditation
        else (
            "Anti-repetition: each confession must look different in posture, framing, "
            "and scene — never recycle the same bent-neck contemplative cover formula."
        )
    )

    prompt = (
        "Generate a single photographic image for the photo slot of a branded "
        "cover template — the image must contain ONLY the person and their "
        "environment. Absolutely no text, no title, no typography, no logos, "
        "no badges, no labels, no borders, no frame, no collage, no graphic "
        "design elements, no UI elements — vertical orientation "
        "(portrait aspect ratio, approximately 4:5).\n\n"
        f"Primary subject: {subject}, in {location}. "
        f"Story beat (one line): {mood}\n\n"
        f"{narrative}\n\n"
        f"{analysis}\n\n"
        f"{energy}\n\n"
        f"{cast}\n\n"
        f"{intimacy}\n\n"
        f"{pose}\n\n"
        f"{environment}\n\n"
        f"{framing}\n\n"
        f"{anti_repeat}\n\n"
        f"{brand}\n\n"
        f"{anti_ai}\n\n"
        f"{look}"
        f"{closing}\n\n"
        f"Guiding principle: use the specific details and emotional essence of THIS "
        f"{kind} — individual and closely connected to the submission, not a fixed "
        "pose template. The photo must fill the entire frame edge-to-edge with no "
        "white space, no borders, no text overlays of any kind."
    )
    return _trim_prompt_to_budget(prompt, _portrait_prompt_char_budget())


_HOMOSEXUAL_KEYWORDS_RE = re.compile(
    r"\b(homosexual|lesbian|gay|queer|same-sex(?:\s+romance|\s+erotic|\s+intimacy)?)\b",
    re.IGNORECASE,
)
_MELANCHOLIC_CUES_RE = re.compile(
    r"\b(forehead pressed to|pressed to cool glass|staring out (?:the )?window|stare out (?:the )?window|"
    r"gazing out (?:the )?window|bent-?neck|neck bent|melancholic|depressed|brooding|sorrowful|looking away sadly)\b",
    re.IGNORECASE,
)


def _sanitize_v2_scene_text(text: str) -> str:
    """Scrub homosexual keywords and extreme bent-neck cues while preserving emotional atmosphere."""
    if not text:
        return ""
    cleaned = _HOMOSEXUAL_KEYWORDS_RE.sub("close companion", text)
    cleaned = _MELANCHOLIC_CUES_RE.sub("thoughtful and engaged in the moment", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _heuristic_v2_photograph_description(story: Story) -> str:
    """Deterministic, story-grounded 1-2 sentence description for the V2 Polaroid slot."""
    from app.model.story import StoryType

    cast_mode = _cast_mode(story)
    gender = (story.gender or "person").strip().lower()
    age_str = f"{story.age}-year-old " if story.age is not None else "adult "
    stype = getattr(story, "story_type", None)

    blob = _story_blob(story, story_chars=500)
    settings = list(dict.fromkeys(m.group(1).lower() for m in _SCENE_SETTING_RE.finditer(blob))) if blob else []
    location = (story.location or story.city or "").strip()

    if settings:
        s0 = settings[0]
        if s0 in ("bed", "bedroom", "sheets"):
            s0 = "private lounge"
        elif s0 in ("bar", "club"):
            s0 = "corner table with soft ambient light"
        elif s0 in ("office", "desk", "computer", "callcenter", "work"):
            s0 = "quiet room near natural window light"
        setting_desc = f"in an atmospheric {s0}"
    elif location:
        setting_desc = f"in {location}"
    else:
        setting_desc = "in an intimate, atmospheric setting"

    situation = (story.situation or "").strip()
    beat_snippet = ""
    banned_beat_keywords = [
        "bar", "cocktail", "party", "computer", "callcenter", "call center",
        "office", "desk", "laptop", "cubicle", "baan"
    ]
    if situation:
        first_sent = situation.split(".")[0].strip()
        if len(first_sent) > 10 and not any(kw in first_sent.lower() for kw in banned_beat_keywords):
            beat_snippet = f", reflecting the moment of {first_sent.lower()}"

    if stype == StoryType.meditation:
        if cast_mode == "group":
            subjects = f"An adult {gender} and companions"
            action = "sharing a quiet, mindful moment of contemplative silence and grounded stillness"
            comp = "Natural unposed spacing and environmental framing"
        elif cast_mode == "pair":
            subjects = f"An adult {gender} and a companion"
            action = "seated in serene stillness, gently breathing in a tranquil, reflective space"
            comp = "Intimate profile framing and calm interpersonal closeness"
        else:
            subjects = f"A {age_str}{gender}"
            action = "in a deeply peaceful, contemplative state of mindfulness and inner quiet"
            comp = "Contemplative medium shot with centered posture"
        mood_posture = "Gentle breathing, serene expression, and grounded presence"

    elif stype == StoryType.transformation:
        if cast_mode == "group":
            subjects = f"An adult {gender} and companions"
            action = "gathered in an authentic, empowering moment of newfound freedom and mutual courage"
            comp = "Dynamic environmental framing and candid body language"
        elif cast_mode == "pair":
            subjects = f"An adult {gender} and a companion"
            action = "sharing an inspiring, open-hearted moment of breakthrough and mutual encouragement"
            comp = "Candid two-shot with expressive connection"
        else:
            subjects = f"A {age_str}{gender}"
            action = "radiating newfound confidence and quiet strength, looking forward with clear purpose"
            comp = "Grounded documentary framing with poised and resolute presence"
        mood_posture = "Self-assured presence, natural poised posture, and an expressive, liberated demeanor"

    else:  # confession or default
        if cast_mode == "group":
            subjects = f"An adult {gender} and close companions"
            action = "sharing a quiet, candid conversation with subtle emotional depth"
            comp = "Natural unposed documentary framing with authentic interpersonal distance"
            mood_posture = "Candid warmth, subtle expressive eyes, and natural emotional posture"
        elif cast_mode == "pair":
            subjects = f"An adult {gender} and a companion"
            action = "sharing an intimate, honest moment of emotional vulnerability and quiet connection"
            comp = "Intimate over-the-shoulder framing and subtle emotional closeness"
            mood_posture = "Subtle interpersonal closeness, candid warmth, and emotionally honest expression"
        else:
            subjects = f"A {age_str}{gender}"
            action = "captured in a private emotional moment, quietly processing personal truth with subtle vulnerability"
            comp = "Intimate documentary portrait with natural framing"
            confession_gestures = [
                "subtle gesture with hand resting near chest, soft thoughtful gaze",
                "sitting quietly in reflection, hands gently relaxed, soft downward gaze",
                "resting lightly against a wall or window frame, contemplative gaze",
                "walking alone at a quiet pace, lost in honest thought",
                "holding a personal object or cup, introspective posture",
                "fingers lightly touching collar or hair, gentle vulnerable expression",
            ]
            seed_key = getattr(story, "title", None) or getattr(story, "first_name", None) or "confession"
            gesture = confession_gestures[abs(hash(seed_key)) % len(confession_gestures)]
            mood_posture = f"Natural body language, {gesture}, emotionally honest expression"

    return (
        f"{subjects} {action}{beat_snippet}, {setting_desc}. "
        f"{comp}. Fully clothed in stylish, casual attire matching the setting. "
        f"{mood_posture}. Emotional intimacy and deeply authentic human truth, as if witnessing a real private moment. "
        f"Soft motivated natural light. No generic stock-photo compositions, no happy friends at a bar, no posed group shots. "
        f"No bent necks or unnatural head tilts. Naturally readable within the frame."
    )


def _heuristic_v2_visual_art_direction(
    story: Story,
    visual_brief: str | None = None,
) -> dict[str, str]:
    """Deterministic, structured visual art direction extracted without LLM."""
    from app.model.story import StoryType

    cast_mode = _cast_mode(story)
    gender = (story.gender or "person").strip().lower()
    age_str = f"{story.age}-year-old " if story.age is not None else "adult "
    location = (
        (story.location or "").strip()
        or ", ".join(p for p in ((story.city or "").strip(), (story.country or "").strip()) if p)
        or "an intimate setting"
    )

    blob = _story_blob(story, story_chars=500)
    settings_list = list(dict.fromkeys(m.group(1).lower() for m in _SCENE_SETTING_RE.finditer(blob))) if blob else []
    weather_list = list(dict.fromkeys(m.group(1).lower() for m in _SCENE_WEATHER_RE.finditer(blob))) if blob else []
    emotions_list = list(dict.fromkeys(m.group(1).lower() for m in _EMOTION_RE.finditer(blob))) if blob else []

    primary_setting = settings_list[0] if settings_list else "space"
    if primary_setting in ("bed", "bedroom", "sheets"):
        primary_setting = "lounge"
    elif primary_setting in ("bar", "club"):
        primary_setting = "corner table with soft ambient light"
    elif primary_setting in ("office", "desk", "computer", "callcenter", "work"):
        primary_setting = "quiet room near natural window light"
    setting_str = f"An intimate, atmospheric {primary_setting} in {location}."

    stype = getattr(story, "story_type", None)
    if cast_mode == "group":
        characters_str = f"An adult {gender} and close companions, fully clothed in elegant, casual attire (jackets and sweaters)."
        comp_str = "Natural unposed environmental composition with authentic spacing between subjects; strictly avoid posed group shots or repetitive social scenes."
        rel_dynamics = "Subtle conversational dynamics, candid distance, and genuine shared history without artificial group posing."
    elif cast_mode == "pair":
        characters_str = f"An adult {gender} and a companion, fully clothed in tasteful attire, sharing an intimate connection."
        comp_str = "Intimate two-shot or over-the-shoulder framing, subtle body language conveying emotional closeness and unspoken depth; unposed and natural."
        rel_dynamics = "Intimate emotional resonance, shared vulnerability, and nuanced interpersonal tension."
    else:
        characters_str = f"A {age_str}{gender} fully clothed in tasteful, elegant knitwear or jacket."
        if stype == StoryType.meditation:
            comp_str = "A single figure seated or standing in grounded stillness with centered medium framing, gentle breath; unposed and natural."
        elif stype == StoryType.transformation:
            comp_str = "A single figure naturally poised with open, expansive framing, radiant confidence and quiet strength; unposed and natural."
        else:
            comp_str = "A single figure in an intimate documentary portrait, natural body language with subtle unforced gesture (e.g. resting against a wall, sitting quietly, or hand near chest); unposed and emotionally honest."
        rel_dynamics = "Introspective solitude, self-reckoning, and quiet dialogue between the narrator and the surrounding space."

    lighting_str = (
        f"Soft practical light, {weather_list[0]} atmosphere with gentle shadows."
        if weather_list
        else "Soft motivated natural light with gentle ambient highlights and subtle film shadows."
    )
    atmosphere_str = (
        f"Sensory {weather_list[0]} environment with authentic weather texture and quiet emotional truth."
        if weather_list
        else "Intimate, atmospheric sensory environment with soft natural light and quiet emotional truth."
    )

    if stype == StoryType.meditation:
        mood_str = (
            f"Tranquil, deeply mindful, calm, and serene connection touching on {', '.join(emotions_list[:3])}."
            if emotions_list
            else "Tranquil, deeply mindful, calm, and inner stillness."
        )
        emotional_state_str = "Quiet, mindful presence, release of tension, and deep inner peace."
        key_events_str = "A quiet, centering breath and a gentle return to stillness and presence."
        narrative_focus_str = "A quiet, centering breath and a gentle return to inner peace and stillness."
    elif stype == StoryType.transformation:
        mood_str = (
            f"Empowering, courageous, and liberating shift touching on {', '.join(emotions_list[:3])}."
            if emotions_list
            else "Empowered, liberating, breakthrough clarity, and newfound confidence."
        )
        emotional_state_str = "Liberating self-realization, courageous clarity, and breaking through past limitations."
        key_events_str = "A pivotal breakthrough moment of stepping boldly into one's own truth and freedom."
        narrative_focus_str = "A pivotal breakthrough moment of stepping boldly into one's own truth and freedom."
    else:
        mood_str = (
            f"Intimate, reflective, nuanced tension touching on {', '.join(emotions_list[:3])}."
            if emotions_list
            else "Intimate, reflective, subtle tension, and quiet emotional connection."
        )
        emotional_state_str = (
            f"Vulnerable emotional reckoning touching on {', '.join(emotions_list[:3])}."
            if emotions_list
            else "Intimate vulnerability, unspoken truth, quiet processing of emotion, and authentic personal honesty."
        )
        situation = (story.situation or "").strip()
        key_events_str = (
            f"The private moment of {situation.rstrip('.').lower()}."
            if situation
            else "A quiet, private beat of shared honesty and understated emotional release."
        )
        narrative_focus_str = "A quiet, private beat of shared honesty and understated emotional release."

    color_palette_str = "Monochrome tones: rich charcoal blacks, soft silvery grays, gentle ivory highlights, authentic film tonal range."
    visual_style_str = "Strictly black-and-white vintage 35mm analogue snapshot, visible organic film grain, soft focus, faded blacks, muted contrast, documentary editorial realism."
    polaroid_scene_str = _heuristic_v2_photograph_description(story)

    return {
        "setting": setting_str,
        "characters": characters_str,
        "composition": comp_str,
        "mood": mood_str,
        "lighting": lighting_str,
        "color_palette": color_palette_str,
        "visual_style": visual_style_str,
        "narrative_focus": narrative_focus_str,
        "polaroid_scene": polaroid_scene_str,
        "emotional_state": emotional_state_str,
        "key_events": key_events_str,
        "relationship_dynamics": rel_dynamics,
        "atmosphere": atmosphere_str,
    }


def refine_story_visual_art_direction(story: Story, *, use_llm: bool = True) -> str:
    """Step 1 of V2: Transform the story into a concise editorial visual brief.

    Instructs the LLM (or deterministic heuristic) to extract:
    - Characters, Setting, Emotional State, Key Events, Relationship Dynamics, Atmosphere
    - Excludes dialogue, internal monologue, and explicit sexual acts.
    """
    from app.model.story import StoryType
    from app.utils.prompts import STORY_VISUAL_REFINEMENT_SYSTEM

    if use_llm and (settings.XAI_API_KEY or "").strip():
        stype = getattr(story, "story_type", None)
        kind = stype.value if hasattr(stype, "value") else (str(stype) if stype else "confession")
        full_text = (story.story_text or story.story_input or "").strip()[:6000]
        title = (story.title or story.member_title or getattr(story, "ai_generated_title", None) or "Untitled").strip()
        author = (story.first_name or "Anonymous").strip()
        location = (story.location or story.city or "unspecified").strip()
        situation = (story.situation or "n/a").strip()
        background = (story.background or "n/a").strip()
        hook = (getattr(story, "hero_hook", None) or "n/a").strip()
        emotional_state = portrait_emotional_state(story)
        narrative_moment = portrait_narrative_moment(story)

        try:
            llm = get_story_llm(temperature=0.35)
            response = llm.invoke(
                f"{STORY_VISUAL_REFINEMENT_SYSTEM}\n\n"
                f"STORY METADATA & 6-DIMENSION ANALYSIS:\n"
                f"- Story Type: {kind.capitalize()}\n"
                f"- Title: {title}\n"
                f"- Narrator: {author}, {story.age if story.age is not None else 'unspecified'}yo, {story.gender or 'unspecified'}, {location}\n"
                f"- Characters / Companions: {background}\n"
                f"- Setting / Locale: {location} (Situation: {situation})\n"
                f"- Emotional State Arc: {emotional_state}\n"
                f"- Key Events / Narrative Beat: {narrative_moment}\n"
                f"- Hero Hook: {hook}\n\n"
                f"STORY TEXT:\n{full_text or situation or hook}\n\n"
                f"MANDATE: Analyze the story's emotional truth across characters, setting, emotional state, and atmosphere. "
                f"The image should create an immediate feeling of recognition and emotional intimacy — as if the viewer has unexpectedly witnessed a real private moment. "
                f"Focus on the emotional truth of the story: Person + genuine emotion + natural environment + an authentic moment that feels naturally photographed. "
                f"Capture genuine human emotion, quiet vulnerability, personal honesty, and authentic presence. "
                f"Natural expression, subtle varied gestures (e.g. hand near chest, holding an object, touching hair, resting against a wall, looking through a window, sitting quietly, or walking alone; never forcing a single pose), authentic imperfections, soft natural light, and film texture. "
                f"Use the actual location or environment implied by the story; do not substitute a visually attractive location simply because it looks cinematic. "
                f"Any subject shown must be naturally readable within the frame; framing may be close, medium, or environmental depending on the emotional moment. "
                f"STRICTLY FORBIDDEN: never depict someone sitting behind a computer, working at a desk, typing on a laptop, or in an office. "
                f"Even if the text mentions work, a callcenter, or an office, visualize the private emotional moment (e.g. standing quietly near a window processing the feeling, a quiet walk at night, or looking out at the sky). "
                f"Create a story-specific scene reflecting the actual narrative and emotional tone. "
                f"Strictly avoid generic stock-photo compositions such as happy friends at a bar, posed group shots, or repetitive social scenes. "
                f"Produce distinct visual compositions, locations, lighting, emotions, character relationships, and atmospheres."
            )
            content = (getattr(response, "content", None) or str(response) or "").strip().strip('"').strip("'")
            content = _sanitize_v2_scene_text(content)
            if len(content) >= 40:
                logger.info("V2 visual refinement path=llm story=%s chars=%s", getattr(story, "id", None), len(content))
                return content
        except Exception:
            logger.warning(
                "V2 visual refinement path=heuristic story=%s reason=llm_failed",
                getattr(story, "id", None),
                exc_info=True,
            )

    art = _heuristic_v2_visual_art_direction(story)
    return (
        f"An intimate documentary portrait set in {art['setting']} {art['characters']} {art['composition']} "
        f"Emotional state reflects {art.get('emotional_state', art['mood'])}. "
        f"Relationship dynamics: {art.get('relationship_dynamics', 'intimate and grounded')}. "
        f"The atmosphere is {art.get('atmosphere', art['lighting'])}. "
        f"The visual mood is quiet, authentic, and reflective rather than cinematic. "
        f"{art['color_palette']} {art['narrative_focus']}"
    )


def extract_v2_visual_art_direction(
    story: Story,
    visual_brief: str | None = None,
    *,
    use_llm: bool = True,
) -> dict[str, str]:
    """Step 2 of V2: Extract structured visual art direction from the visual brief.

    Returns a dictionary with keys:
    - "setting"
    - "characters"
    - "composition"
    - "mood"
    - "lighting"
    - "color_palette"
    - "visual_style"
    - "narrative_focus"
    - "polaroid_scene"
    - "emotional_state"
    - "key_events"
    - "relationship_dynamics"
    - "atmosphere"
    """
    from app.utils.prompts import VISUAL_ART_DIRECTION_EXTRACTION_SYSTEM

    brief = visual_brief or refine_story_visual_art_direction(story, use_llm=use_llm)

    if use_llm and (settings.XAI_API_KEY or "").strip():
        try:
            llm = get_story_llm(temperature=0.2)
            response = llm.invoke(
                f"{VISUAL_ART_DIRECTION_EXTRACTION_SYSTEM}\n\n"
                f"EDITORIAL VISUAL BRIEF:\n{brief}\n\n"
                f"STORY METADATA & CONTEXT:\n"
                f"Story Type: {story.story_type.value.capitalize() if getattr(story, 'story_type', None) else 'Confession'}\n"
                f"Narrator: {story.first_name or 'Anonymous'}, {story.age if story.age is not None else 'unspecified'}yo, {story.gender or 'unspecified'}, {story.location or 'unspecified'}\n"
                f"Title: {story.title or 'Untitled'}\n"
                f"Emotional Arc: {portrait_emotional_state(story)}\n"
                f"Pivotal Beat: {portrait_narrative_moment(story)}\n\n"
                f"Extract all dimensions (characters, setting, emotional state, key events, relationship dynamics, atmosphere, "
                f"composition, lighting, color palette, visual style, narrative focus, and polaroid scene) into valid JSON. "
                f"The scene must capture emotional intimacy, genuine human truth, and quiet vulnerability — creating an immediate feeling of recognition, as if witnessing a real private moment. "
                f"Focus on the core visual idea: Person + genuine emotion + natural environment + an authentic moment that feels naturally photographed. "
                f"Use the actual location or environment implied by the story; do not substitute a visually attractive location simply because it looks cinematic. "
                f"Any subject shown must be naturally readable within the frame; framing may be close, medium, or environmental depending on the emotional moment. "
                f"Use subtle varied gestures appropriate to the story (hand near chest, holding an object, touching hair, resting against a wall, looking through a window, sitting quietly, walking alone; never forcing a single pose). "
                f"Never create theatrical movie stills, artificial melodrama, dull pictures, or sterile modern realism. "
                f"Strictly forbidden: never depict someone sitting behind a computer, at a desk, or in an office. "
                f"Strictly avoid generic stock-photo compositions such as happy friends at a bar, posed group shots, or repetitive social scenes."
            )
            raw = (getattr(response, "content", None) or str(response) or "").strip()
            if "```" in raw:
                raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
                raw = re.sub(r"\s*```$", "", raw)
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(raw[start : end + 1])
                if isinstance(parsed, dict):
                    normalized: dict[str, str] = {}
                    key_map = {
                        "setting": "setting",
                        "characters": "characters",
                        "composition": "composition",
                        "mood": "mood",
                        "lighting": "lighting",
                        "time_and_lighting": "lighting",
                        "color_palette": "color_palette",
                        "visual_style": "visual_style",
                        "narrative_focus": "narrative_focus",
                        "polaroid_scene": "polaroid_scene",
                        "emotional_state": "emotional_state",
                        "key_events": "key_events",
                        "relationship_dynamics": "relationship_dynamics",
                        "atmosphere": "atmosphere",
                    }
                    for k, v in parsed.items():
                        norm_k = key_map.get(k.lower())
                        if norm_k and isinstance(v, str) and v.strip():
                            normalized[norm_k] = _sanitize_v2_scene_text(v.strip())

                    fallback = _heuristic_v2_visual_art_direction(story, visual_brief=brief)
                    for required_key in [
                        "setting",
                        "characters",
                        "composition",
                        "mood",
                        "lighting",
                        "color_palette",
                        "visual_style",
                        "narrative_focus",
                        "polaroid_scene",
                        "emotional_state",
                        "key_events",
                        "relationship_dynamics",
                        "atmosphere",
                    ]:
                        if not normalized.get(required_key):
                            normalized[required_key] = fallback.get(required_key, "")

                    logger.info("V2 structured visual art direction path=llm story=%s", getattr(story, "id", None))
                    return normalized
        except Exception:
            logger.warning(
                "V2 structured visual art direction path=heuristic story=%s reason=llm_or_json_failed",
                getattr(story, "id", None),
                exc_info=True,
            )

    return _heuristic_v2_visual_art_direction(story, visual_brief=brief)


def build_v2_photograph_description(
    story: Story,
    *,
    use_llm: bool = True,
    art_direction: dict[str, str] | None = None,
) -> str:
    """Generate a concise 1-2 sentence description of the subjects and scene inside the Polaroid."""
    if art_direction and art_direction.get("polaroid_scene"):
        return _sanitize_v2_scene_text(art_direction["polaroid_scene"].strip())

    if use_llm and (settings.XAI_API_KEY or "").strip():
        try:
            art_dir = extract_v2_visual_art_direction(story, use_llm=True)
            if art_dir.get("polaroid_scene"):
                return _sanitize_v2_scene_text(art_dir["polaroid_scene"].strip())
        except Exception:
            logger.warning(
                "V2 photograph description via art direction failed for story %s, falling back",
                getattr(story, "id", None),
                exc_info=True,
            )

    return _sanitize_v2_scene_text(_heuristic_v2_photograph_description(story))


def build_v2_cover_prompt(
    story: Story,
    *,
    photograph_description: str | None = None,
    art_direction: dict[str, str] | None = None,
    use_llm_scene: bool = True,
) -> str:
    """Build the V2 prompt matching client design specifications.

    Generates a full story introduction page with warm ivory paper background,
    black text with raspberry pink (#D72655) accents, expressive brush lettering,
    and a vintage monochrome Polaroid photograph on the right.
    """
    from app.model.story import StoryType
    from app.utils.prompts import (
        V2_COVER_ANALOGUE_TREATMENT,
        V2_COVER_CLOSING_CONSTRAINTS,
        V2_COVER_PROMPT_TEMPLATE,
    )
    from app.utils.story_cover import _description_for_story, _split_location

    is_meditation = story.story_type == StoryType.meditation
    is_transformation = story.story_type == StoryType.transformation

    if is_meditation:
        category_title = "Meditations"
        category_upper = "MEDITATIONS"
        kind_singular = "meditation"
        button_label = "READ MEDITATION →"
    elif is_transformation:
        category_title = "Transformations"
        category_upper = "TRANSFORMATIONS"
        kind_singular = "transformation"
        button_label = "READ STORY →"
    else:
        category_title = "Confessions"
        category_upper = "CONFESSIONS"
        kind_singular = "confession"
        button_label = "READ CONFESSION →"

    raw_title = (story.title or story.member_title or getattr(story, "ai_generated_title", None) or "Untitled").strip()
    title = raw_title.replace('"', '').replace('“', '').replace('”', '').strip() or "Untitled"
    title_words = title.split()
    if len(title_words) > 4:
        title = " ".join(title_words[:4])

    hook = (getattr(story, "hero_hook", None) or "").strip()
    if hook:
        body = hook
    else:
        body = _description_for_story(story)
    body_text = body.replace('"', "'").replace('“', "'").replace('”', "'").strip()
    norm_text = re.sub(r'\.{2,}', '…', body_text)
    if "." in norm_text:
        first_sentence = norm_text.split(".")[0].strip() + "."
        if len(first_sentence) > 5:
            body_text = first_sentence.replace('…', '...')
    words = body_text.split()
    if len(words) > 10:
        body_text = " ".join(words[:9]).rstrip(",;:") + "."
    if body_text and not body_text.endswith((".", "!", "?")):
        body_text += "."

    city, country = _split_location(story)
    if city and country:
        location_text = f"{city}, {country}".upper()
    elif city or country:
        location_text = (city or country).upper()
    elif (story.location or "").strip():
        location_text = story.location.strip().upper()
    else:
        location_text = "WALES, UK"

    demo_parts = []
    if story.age is not None:
        demo_parts.append(f"{story.age} YEARS")
    if story.gender:
        demo_parts.append(story.gender.strip().upper())
    orientation = (getattr(story, "sexual_orientation", None) or "").strip().upper()
    if orientation and not any(kw in orientation for kw in ["HOMOSEXUAL", "GAY", "LESBIAN", "QUEER", "SAME-SEX"]):
        demo_parts.append(orientation)
    demographics_text = " / ".join(demo_parts) or "ADULT"

    is_explicit = bool(getattr(story, "high_intensity", False))
    if is_explicit:
        explicit_section = '\nAdd a bold outlined raspberry-pink label:\n\n"EXPLICIT"\n'
        explicit_bullet = "- EXPLICIT label\n"
        explicit_numbered_item = "9. EXPLICIT\n"
    else:
        explicit_section = ""
        explicit_bullet = ""
        explicit_numbered_item = ""

    if photograph_description:
        photo_desc = _sanitize_v2_scene_text(photograph_description.strip().rstrip("."))
    elif art_direction and art_direction.get("polaroid_scene"):
        photo_desc = _sanitize_v2_scene_text(art_direction["polaroid_scene"].strip().rstrip("."))
    else:
        photo_desc = _sanitize_v2_scene_text(build_v2_photograph_description(story, use_llm=use_llm_scene).strip().rstrip("."))

    author_name = (story.first_name or "Anonymous").strip().upper()

    prompt = V2_COVER_PROMPT_TEMPLATE.format(
        category_title=category_title,
        category_upper=category_upper,
        kind_singular=kind_singular,
        title=title,
        body_text=body_text,
        location_text=location_text,
        demographics_text=demographics_text,
        explicit_section=explicit_section,
        explicit_bullet=explicit_bullet,
        explicit_numbered_item=explicit_numbered_item,
        button_label=button_label,
        photo_desc=photo_desc,
        author_name=author_name,
    )
    return prompt


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
