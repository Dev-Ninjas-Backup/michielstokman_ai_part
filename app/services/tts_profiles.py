"""
app/services/tts_profiles.py

Per-story-type TTS voice profiles and text preparation for Transform to Liberation.
Provides tunable emotional delivery settings for ElevenLabs and natural text preparation.
"""

from dataclasses import dataclass
import re
from typing import Optional, Union
from app.core.config import settings
from app.schemas.schema_ai import StoryType


@dataclass(frozen=True)
class TTSProfile:
    story_type: str
    stability: float
    similarity_boost: float
    style: float
    speed: float
    pause_ms: int
    paragraph_break_s: float
    seam_gap_ms: int = 800
    seam_paragraph_gap_ms: int = 800

    def __post_init__(self):
        # ElevenLabs accepts speed in [0.7, 1.2]
        if not (0.7 <= self.speed <= 1.2):
            raise ValueError(f"Speed {self.speed} out of allowed ElevenLabs range [0.7, 1.2]")
        if not (0.0 <= self.stability <= 1.0):
            raise ValueError(f"Stability {self.stability} out of range [0.0, 1.0]")
        if not (0.0 <= self.similarity_boost <= 1.0):
            raise ValueError(f"Similarity boost {self.similarity_boost} out of range [0.0, 1.0]")
        if not (0.0 <= self.style <= 1.0):
            raise ValueError(f"Style {self.style} out of range [0.0, 1.0]")
        if (
            self.paragraph_break_s < 0.0
            or self.pause_ms < 0
            or self.seam_gap_ms < 0
            or self.seam_paragraph_gap_ms < 0
        ):
            raise ValueError("Pause durations must be non-negative")


# Default profiles per story type (tunable)
TTS_PROFILES: dict[str, TTSProfile] = {
    "confession": TTSProfile(
        story_type="confession",
        stability=0.35,
        similarity_boost=0.75,
        style=0.45,
        speed=0.95,
        pause_ms=300,
        paragraph_break_s=0.7,
    ),
    "meditation": TTSProfile(
        story_type="meditation",
        stability=0.65,
        similarity_boost=0.80,
        style=0.15,
        speed=0.85,
        pause_ms=500,
        paragraph_break_s=1.2,
    ),
    "transformation": TTSProfile(
        story_type="transformation",
        stability=0.45,
        similarity_boost=0.75,
        style=0.35,
        speed=0.92,
        pause_ms=350,
        paragraph_break_s=0.8,
    ),
}

DEFAULT_PROFILE = TTSProfile(
    story_type="default",
    stability=0.45,
    similarity_boost=0.75,
    style=0.35,
    speed=0.95,
    pause_ms=350,
    paragraph_break_s=0.8,
)


# Voice-specific tuning overrides for calibrated pacing, volume consistency, and emotional delivery
VOICE_TUNING_OVERRIDES = {
    "calen": {
        "speed": 1.15,
        "speed_meditation": 1.08,
        "stability": 0.52,
        "stability_meditation": 0.60,
        "similarity_boost": 0.85,
        "style": 0.40,
        "style_meditation": 0.35,
    },
    "victoria": {
        "speed": 1.00,
        "speed_meditation": 0.90,
        "stability": 0.55,
        "stability_meditation": 0.60,
        "similarity_boost": 0.85,
        "style": 0.18,
        "style_meditation": 0.15,
    },
    "anja": {
        "speed": 1.02,
        "speed_meditation": 0.92,
        "stability": 0.52,
        "stability_meditation": 0.58,
        "similarity_boost": 0.86,
        "style": 0.42,
        "style_meditation": 0.35,
    },
}

VOICE_ID_NAME_MAP = {
    "calen": "calen",
    "s44kq3olfckbxgykfold": "calen",
    "victoria": "victoria",
    "weaawkycs06vmxw086yz": "victoria",
    "anja": "anja",
    "ytio1w3m21pipjpr44fo": "anja",
}


def get_tts_profile(
    story_type: Optional[Union[str, StoryType]] = None,
    voice_id: Optional[str] = None,
) -> TTSProfile:
    """
    Resolves TTSProfile for a given story_type string or enum.
    When voice_id is supplied, applies per-voice calibrated overrides for
    pacing (e.g. Calen speed boost), stability, volume consistency, and emotion (e.g. Victoria, Anja).
    When voice_id is None, returns the base story profile.
    """
    base_profile = DEFAULT_PROFILE
    if story_type:
        key = str(story_type.value if isinstance(story_type, StoryType) else story_type).lower().strip()
        for profile_key, profile in TTS_PROFILES.items():
            if profile_key in key:
                base_profile = profile
                break

    if not voice_id:
        return base_profile

    v_key = VOICE_ID_NAME_MAP.get(str(voice_id).strip().lower())
    if not v_key or v_key not in VOICE_TUNING_OVERRIDES:
        return base_profile

    overrides = VOICE_TUNING_OVERRIDES[v_key]
    is_meditation = "meditation" in base_profile.story_type.lower()

    tuned_speed = overrides.get("speed_meditation" if is_meditation else "speed", base_profile.speed)
    tuned_stability = overrides.get("stability_meditation" if is_meditation else "stability", base_profile.stability)
    tuned_similarity = overrides.get("similarity_boost", base_profile.similarity_boost)
    tuned_style = overrides.get("style_meditation" if is_meditation else "style", base_profile.style)

    return TTSProfile(
        story_type=base_profile.story_type,
        stability=tuned_stability,
        similarity_boost=tuned_similarity,
        style=tuned_style,
        speed=tuned_speed,
        pause_ms=base_profile.pause_ms,
        paragraph_break_s=base_profile.paragraph_break_s,
        seam_gap_ms=base_profile.seam_gap_ms,
        seam_paragraph_gap_ms=base_profile.seam_paragraph_gap_ms,
    )


# Emoji removal pattern (broad Unicode ranges covering emojis and symbols)
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess, symbols
    "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-a
    "]+",
    flags=re.UNICODE,
)


def prepare_text_for_tts(
    text: str,
    story_type: Optional[Union[str, StoryType]] = None,
    smooth_audio: Optional[bool] = None,
) -> str:
    """
    Prepares story text for ElevenLabs TTS when TTS_PIPELINE_V2 is enabled.
    - Strips markdown, emojis, and parentheses.
    - Removes existing manual pause/break tags to avoid redundant pauses.
    - Normalizes whitespace.
    - Preserves natural punctuation and ellipses without intrusive tags.
    - When smooth_audio (or TTS_SMOOTH_AUDIO) is enabled, sends NO <break> tags (paragraphs joined with newlines).
    - Otherwise inserts a single profile-tuned <break> tag ONLY at paragraph ends.
    - The original text in the database is NOT modified; this only formats the TTS payload.
    """
    if not text:
        return ""

    profile = get_tts_profile(story_type)

    if smooth_audio is None:
        smooth_audio = getattr(settings, "TTS_SMOOTH_AUDIO", False) and getattr(settings, "TTS_PIPELINE_V2", False)

    # 1. Strip existing break/pause tags (e.g. from prompts or manual insertions)
    cleaned = re.sub(r'<break\s+time="[^"]*"\s*/>', " ", text)
    cleaned = re.sub(r'\[(?:pause\s+)?(\d+)(?:\s*s|\s*sec|\s*seconds)?(?:\s+pause)?\]', " ", cleaned, flags=re.IGNORECASE)

    # 2. Strip emojis
    cleaned = _EMOJI_PATTERN.sub("", cleaned)

    # 3. Strip parentheses (remove opening and closing parentheses, keeping the inner text)
    cleaned = cleaned.replace("(", "").replace(")", "")

    # 4. Strip markdown formatting:
    # Headers (# Title)
    cleaned = re.sub(r'^#{1,6}\s+', '', cleaned, flags=re.MULTILINE)
    # Bold / Italics (**text**, *text*, __text__, _text_)
    cleaned = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', cleaned)
    cleaned = re.sub(r'_{1,3}(.*?)_{1,3}', r'\1', cleaned)
    # Blockquotes (> text)
    cleaned = re.sub(r'^>\s+', '', cleaned, flags=re.MULTILINE)
    # Code blocks (``` or `)
    cleaned = re.sub(r'```.*?```', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
    # Bullet lists (- item or * item)
    cleaned = re.sub(r'^\s*[-*+]\s+', '', cleaned, flags=re.MULTILINE)

    # 5. Normalize ellipses to standard '...' with a following space
    cleaned = re.sub(r'\.{3,}', '...', cleaned)

    # 6. Split into paragraphs (separated by two or more newlines)
    paragraphs = re.split(r'\n\s*\n+', cleaned)
    processed_paragraphs = []

    for para in paragraphs:
        # Normalize internal whitespace: replace single newlines with space, multiple spaces with single space
        para_clean = re.sub(r'\s*\n\s*', ' ', para)
        para_clean = re.sub(r'[ \t]+', ' ', para_clean).strip()
        if para_clean:
            processed_paragraphs.append(para_clean)

    if not processed_paragraphs:
        return ""

    if smooth_audio:
        # When smooth audio is enabled: send NO <break> tags; use natural punctuation and '...' only
        final_text = "\n\n".join(processed_paragraphs)
        final_text = re.sub(r'<break\s+time="[^"]*"\s*/>', '', final_text)
        return final_text.strip()

    # 7. Join paragraphs with double newlines and a single break tag with profile duration
    break_tag = f'<break time="{profile.paragraph_break_s:.1f}s" />'
    final_text = f"\n\n{break_tag}\n\n".join(processed_paragraphs)

    # 8. Ensure no double break tags or leading/trailing break tags
    final_text = re.sub(r'(<break\s+time="[^"]*"\s*/>\s*)+', r'\1', final_text)
    final_text = re.sub(r'^\s*<break\s+time="[^"]*"\s*/>\s*', '', final_text)
    final_text = re.sub(r'\s*<break\s+time="[^"]*"\s*/>\s*$', '', final_text)

    return final_text.strip()

