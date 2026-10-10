"""
tests/test_meditation_processing.py

Tests for the AI/backend processing of meditation input text and cover generation:
Verifies that:
- Grok is instructed to polish and preserve meditation text without truncation or summarization
- Natural meditative pacing break tags (<break time="3.0s" /> and <break time="2.0s" />) are enforced
- Meditation generation uses calibrated low temperature (0.35) and sufficient token limit
- V2 cover prompt incorporates category MEDITATIONS, warm amber gold accent colors (#EEA13D),
  and serene contemplative visual style
- TTS profile for meditation is correctly calibrated (stability=0.65, style=0.15, speed=0.85)
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.model.story import StoryType
from app.schemas.schema_ai import StoryGenerateRequest, StoryType as StoryTypeSchema
from app.services.service_ai import AIService
from app.services.tts_profiles import get_tts_profile
from app.utils.prompts import (
    STORY_HUMAN_TEMPLATE,
    STORY_TYPE_INSTRUCTIONS,
    build_story_system_template,
)
from app.utils.story_image_prompt import build_v2_cover_prompt


def test_meditation_instructions_require_strict_fidelity_and_soothing_pacing():
    """Meditation instruction must forbid summarization and require calm pacing breaks."""
    instruction = STORY_TYPE_INSTRUCTIONS[StoryType.meditation]

    assert "Write a MEDITATION" in instruction
    assert "DO NOT SUMMARIZE OR SHORTEN" in instruction
    assert "PRESERVE ORIGINAL LENGTH" in instruction
    assert "up to 1,800 words" in instruction
    assert "PRESERVE GUIDANCE & CONTEXT" in instruction
    assert "PACING & SILENCE" in instruction
    assert '<break time="3.0s" />' in instruction
    assert '<break time="2.0s" />' in instruction


def test_story_human_template_includes_meditation_directive():
    """STORY_HUMAN_TEMPLATE must include instructions for preserving meditation texts."""
    assert "FOR MEDITATIONS: Carefully read the complete meditation text and preserve it in full" in STORY_HUMAN_TEMPLATE
    assert "up to 1,800 words" in STORY_HUMAN_TEMPLATE


def test_settings_meditation_temperature_and_token_budget():
    """Settings must provide LLM_TEMPERATURE_MEDITATION and LLM_MAX_TOKENS."""
    assert hasattr(settings, "LLM_TEMPERATURE_MEDITATION")
    assert settings.LLM_TEMPERATURE_MEDITATION <= 0.5
    assert hasattr(settings, "LLM_MAX_TOKENS")
    assert settings.LLM_MAX_TOKENS >= 4096


def test_generate_story_uses_meditation_temperature():
    """AIService.generate_story calls get_story_llm with meditation temperature."""
    mock_llm_instance = MagicMock()
    mock_llm_instance.invoke.return_value = SimpleNamespace(
        content=(
            "TITLE: Morning Breath\n"
            "IMAGE_PROMPT: A serene meditation cover.\n"
            "STORY:\n"
            "Breathe in deeply... feel the calm settle in your body."
        )
    )

    req = StoryGenerateRequest(
        story_type=StoryTypeSchema.meditation,
        story_input="A guided meditation on finding peace in the morning.",
        first_name="Aoi",
        title="Morning Breath",
    )

    with patch("app.services.service_ai.get_story_llm", return_value=mock_llm_instance) as mock_get_llm:
        title, story_text, image_prompt = AIService.generate_story(req, gender="female")

        mock_get_llm.assert_called_once_with(
            temperature=settings.LLM_TEMPERATURE_MEDITATION,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
        assert title == "Morning Breath"
        assert "Breathe in deeply" in story_text
        assert image_prompt == "A serene meditation cover."


def test_meditation_v2_cover_prompt_accent_colors_and_layout():
    """build_v2_cover_prompt formats warm amber gold accents (#EEA13D) for meditations."""
    story = SimpleNamespace(
        story_type=StoryType.meditation,
        title="Still Waters",
        member_title=None,
        ai_generated_title=None,
        hero_hook="Rest your awareness on the gentle rise and fall of each breath.",
        location="Kyoto, Japan",
        city="Kyoto",
        country="Japan",
        age=32,
        gender="female",
        sexual_orientation=None,
        high_intensity=False,
        first_name="Mei",
        situation="",
        background="",
        personality="",
        lifestyle="",
        story_input="",
        story_text="",
        tags=[],
        growth_areas=[],
    )

    prompt = build_v2_cover_prompt(story, use_llm_scene=False)

    # Category and branding
    assert "Create a complete TTL Meditations story introduction page" in prompt
    assert "MEDITATIONS" in prompt
    assert '"Still Waters"' in prompt
    assert '"MEI"' in prompt
    assert '"AUTHOR"' in prompt

    # Warm amber gold styling
    assert "#EEA13D" in prompt
    assert "warm amber gold" in prompt

    # No button or CTA constraint
    assert "NO BUTTON / NO CTA" in prompt


def test_meditation_tts_profile():
    """get_tts_profile('meditation') returns slow, stable audio parameters."""
    profile = get_tts_profile("meditation")
    assert profile.stability == 0.65
    assert profile.style == 0.15
    assert profile.speed == 0.85
    assert profile.pause_ms == 500
    assert profile.paragraph_break_s == 1.2
