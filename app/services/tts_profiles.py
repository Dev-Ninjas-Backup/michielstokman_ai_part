"""
app/services/tts_profiles.py

Per-story-type TTS voice profiles and text preparation for Transform to Liberation.
Provides tunable emotional delivery settings for ElevenLabs and natural text preparation.
"""

from dataclasses import dataclass
import re
from typing import Optional, Union
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
    seam_paragraph_gap_ms: int = 1200

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


def get_tts_profile(story_type: Optional[Union[str, StoryType]] = None) -> TTSProfile:
    """Resolves TTSProfile for a given story_type string or enum."""
    if not story_type:
        return DEFAULT_PROFILE
    key = str(story_type.value if isinstance(story_type, StoryType) else story_type).lower().strip()
    for profile_key, profile in TTS_PROFILES.items():
        if profile_key in key:
            return profile
    return DEFAULT_PROFILE


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


def prepare_text_for_tts(text: str, story_type: Optional[Union[str, StoryType]] = None) -> str:
    """
    Prepares story text for ElevenLabs TTS when TTS_PIPELINE_V2 is enabled.
    - Strips markdown, emojis, and parentheses.
    - Removes existing manual pause/break tags to avoid redundant pauses.
    - Normalizes whitespace.
    - Preserves natural punctuation and ellipses without intrusive tags.
    - Inserts a single profile-tuned <break> tag ONLY at paragraph ends.
    - The original text in the database is NOT modified; this only formats the TTS payload.
    """
    if not text:
        return ""

    profile = get_tts_profile(story_type)

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

    # 7. Join paragraphs with double newlines and a single break tag with profile duration
    break_tag = f'<break time="{profile.paragraph_break_s:.1f}s" />'
    final_text = f"\n\n{break_tag}\n\n".join(processed_paragraphs)

    # 8. Ensure no double break tags or leading/trailing break tags
    final_text = re.sub(r'(<break\s+time="[^"]*"\s*/>\s*)+', r'\1', final_text)
    final_text = re.sub(r'^\s*<break\s+time="[^"]*"\s*/>\s*', '', final_text)
    final_text = re.sub(r'\s*<break\s+time="[^"]*"\s*/>\s*$', '', final_text)

    return final_text.strip()
