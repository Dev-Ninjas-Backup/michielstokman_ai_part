"""
tests/test_confession_processing.py

Tests for the AI/backend processing of confession input text:
Verifies that Grok is instructed with strict fidelity to:
- Read and understand the complete original story carefully
- Not summarize, shorten, compress, or unnecessarily remove any part of the story
- Keep main story, context, meaning, events, emotions, characters, and important details unchanged
- Not invent new information, events, emotions, characters, facts, or details
- Make only minimal grammar, spelling, sentence-structure, or wording improvements
- Improve unclear portions only when necessary to preserve intended meaning
- Maintain approximately the same length as the original input (1,000–1,800 words)
- Configure lower temperature (0.35) and large token limits (8192) to prevent truncation/hallucination
"""
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from app.core.config import settings
from app.model.story import StoryType
from app.schemas.schema_ai import StoryGenerateRequest, StoryType as StoryTypeSchema
from app.services.service_ai import AIService
from app.utils.prompts import (
    STORY_TYPE_INSTRUCTIONS,
    STORY_HUMAN_TEMPLATE,
    CONFESSION_USER_CONTEXT_INJECTION,
    USER_CONTEXT_INJECTION,
    build_story_system_template,
    build_user_context,
    cover_identity_template_vars,
)


def test_confession_instructions_require_strict_preservation():
    """Confession instruction must forbid summarizing, shortening, and inventing facts."""
    instruction = STORY_TYPE_INSTRUCTIONS[StoryType.confession]
    
    # Must forbid summarizing or shortening
    assert "DO NOT SUMMARIZE OR SHORTEN" in instruction
    assert "You MUST NOT summarize, shorten, compress, condense, or unnecessarily remove" in instruction

    # Must preserve full length matching input (1,000-1,800 words)
    assert "PRESERVE ORIGINAL LENGTH" in instruction
    assert "1,000–1,800 words" in instruction
    assert "Under NO circumstances should you truncate, compress, or shorten the story to approximately 1,000 words" in instruction

    # Must preserve story, context, events, emotions, details
    assert "PRESERVE STORY & CONTEXT" in instruction
    assert "main story, context, meaning, sequence of events, emotional arc" in instruction

    # Must forbid inventing new information, characters, or facts
    assert "NO INVENTED INFORMATION" in instruction
    assert "Do not introduce new characters, do not alter existing character names, and do not change settings or locations" in instruction

    # Must specify minimal grammar/clarity improvements only
    assert "MINIMAL IMPROVEMENTS ONLY" in instruction
    assert "minor grammar, spelling, punctuation, sentence-structure, or wording issues" in instruction

    # Must improve unclear portions only to preserve intended meaning
    assert "IMPROVE UNCLEAR PORTIONS ONLY TO PRESERVE MEANING" in instruction
    assert "ONLY when necessary to preserve and express the intended meaning" in instruction


def test_confession_user_context_injection():
    """Confession-specific context injection must contain top-priority fidelity rules."""
    assert "CRITICAL CONFESSION PROCESSING REQUIREMENTS (STRICT FIDELITY)" in CONFESSION_USER_CONTEXT_INJECTION
    assert "DO NOT Summarize or Shorten" in CONFESSION_USER_CONTEXT_INJECTION
    assert "1,000–1,800 words" in CONFESSION_USER_CONTEXT_INJECTION
    assert "NO Invented Information" in CONFESSION_USER_CONTEXT_INJECTION
    assert "Core Objective: Preserve the user's original confession" in CONFESSION_USER_CONTEXT_INJECTION


def test_build_story_system_template_for_confession_uses_confession_injection():
    """build_story_system_template uses CONFESSION_USER_CONTEXT_INJECTION for confession."""
    system = build_story_system_template(StoryType.confession, gender=None)
    assert "CONFESSION PROCESSING & REFINEMENT INSTRUCTIONS" in system
    assert "CRITICAL CONFESSION PROCESSING REQUIREMENTS (STRICT FIDELITY)" in system
    assert "Under NO circumstances should you truncate, compress, or shorten the story to approximately 1,000 words" in system


def test_build_story_system_template_non_confession_unaffected():
    """Meditations and transformations continue to use their standard context injection."""
    med_system = build_story_system_template(StoryType.meditation, gender=None)
    assert "Write a MEDITATION" in med_system
    assert "CONFESSION PROCESSING & REFINEMENT INSTRUCTIONS" not in med_system
    assert "Use this profile to make the story feel unmistakably personal" in med_system

    trans_system = build_story_system_template(StoryType.transformation, gender=None)
    assert "Write a TRANSFORMATION story" in trans_system
    assert "CONFESSION PROCESSING & REFINEMENT INSTRUCTIONS" not in trans_system


def test_build_user_context_labels_confession_story_distinctly():
    """build_user_context must label confession story as complete original story to be preserved."""
    sample_story = "This is my complete confession of 1200 words. " * 50
    req_confession = StoryGenerateRequest(
        story_type=StoryTypeSchema.confession,
        story_input=sample_story,
        first_name="Elena",
    )
    context_confession = build_user_context(req_confession)
    assert "User's complete original confession story (MUST BE PRESERVED IN FULL — DO NOT SUMMARIZE, CONDENSE, OR SHORTEN)" in context_confession
    assert sample_story in context_confession

    req_meditation = StoryGenerateRequest(
        story_type=StoryTypeSchema.meditation,
        story_input="Breathe in deeply and exhale slowly.",
        first_name="Elena",
    )
    context_meditation = build_user_context(req_meditation)
    assert "User's raw story/meditation input: Breathe in deeply" in context_meditation
    assert "User's complete original confession story" not in context_meditation


def test_story_human_template_confession_directive():
    """STORY_HUMAN_TEMPLATE reminds the model to preserve complete confession in full."""
    assert "FOR CONFESSIONS: Carefully read the complete original story and preserve it in full — do NOT summarize, shorten, compress, or rewrite" in STORY_HUMAN_TEMPLATE
    assert "output must remain approximately the same length as the original input (1,000–1,800 words)" in STORY_HUMAN_TEMPLATE

    # Can be formatted cleanly
    vars_ = cover_identity_template_vars("Elena", "female", "Paris")
    filled = STORY_HUMAN_TEMPLATE.format(story_type="confession", **vars_)
    assert "Elena" in filled
    assert "Paris" in filled


def test_settings_confession_temperature_and_token_budget():
    """Settings include LLM_TEMPERATURE_CONFESSION and LLM_MAX_TOKENS."""
    assert hasattr(settings, "LLM_TEMPERATURE_CONFESSION")
    assert settings.LLM_TEMPERATURE_CONFESSION <= 0.5  # Controlled temperature for fidelity
    assert hasattr(settings, "LLM_MAX_TOKENS")
    assert settings.LLM_MAX_TOKENS >= 4096


def test_generate_story_uses_confession_temperature_and_max_tokens():
    """AIService.generate_story calls get_story_llm with confession temperature and max_tokens."""
    mock_llm_instance = MagicMock()
    mock_llm_instance.invoke.return_value = SimpleNamespace(
        content=(
            "TITLE: Midnight Echoes\n"
            "IMAGE_PROMPT: A beautiful collage cover depicting Elena.\n"
            "STORY:\n"
            "This is the polished confession text preserving all 1500 words intact."
        )
    )

    req = StoryGenerateRequest(
        story_type=StoryTypeSchema.confession,
        story_input="My raw 1500 word confession story here...",
        first_name="Elena",
        title="Midnight Echoes",
    )

    with patch("app.services.service_ai.get_story_llm", return_value=mock_llm_instance) as mock_get_llm:
        title, story_text, image_prompt = AIService.generate_story(req, gender="female")

        mock_get_llm.assert_called_once_with(
            temperature=settings.LLM_TEMPERATURE_CONFESSION,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
        assert title == "Midnight Echoes"
        assert "This is the polished confession text" in story_text
        assert image_prompt == "A beautiful collage cover depicting Elena."


def test_generate_story_strips_markdown_wrappers():
    """AIService.generate_story strips markdown code block wrappers if Grok wraps response."""
    mock_llm_instance = MagicMock()
    mock_llm_instance.invoke.return_value = SimpleNamespace(
        content=(
            "```markdown\n"
            "TITLE: Whisper in the Dark\n"
            "IMAGE_PROMPT: Vintage photo cover.\n"
            "STORY:\n"
            "Full story text without reduction.\n"
            "```"
        )
    )

    req = StoryGenerateRequest(
        story_type=StoryTypeSchema.confession,
        story_input="Original confession text...",
        first_name="Sophia",
    )

    with patch("app.services.service_ai.get_story_llm", return_value=mock_llm_instance):
        title, story_text, image_prompt = AIService.generate_story(req)
        assert title == "Whisper in the Dark"
        assert story_text == "Full story text without reduction."
        assert image_prompt == "Vintage photo cover."
