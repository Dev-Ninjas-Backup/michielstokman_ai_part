"""Tests for COVER_GENERATION_METHOD routing (dalle default vs template)."""
from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.model.story import ImageSource, StoryType
from app.utils import story_cover
from app.utils.prompts import (
    CONFESSION_COVER_ANTI_AI_LOOK,
    CONFESSION_COVER_BRAND_COLLECTION,
    CONFESSION_COVER_ENERGY,
    CONFESSION_COVER_PHOTOGRAPHY_LOOK,
    CONFESSION_COVER_PHOTOGRAPHY_LOOK_V2,
)
from app.utils.story_image_prompt import (
    brief_story_mood_scene,
    build_portrait_only_prompt,
    portrait_cast_instruction,
    portrait_pose_instruction,
    portrait_scene_detail,
    portrait_story_analysis,
)


def _story(**kwargs):
    defaults = dict(
        id="00000000-0000-0000-0000-000000000001",
        story_type=StoryType.confession,
        title="To Wasteland On My Own",
        member_title=None,
        ai_generated_title=None,
        first_name="Lisa",
        gender="female",
        age=28,
        sexual_orientation="bisexual",
        city="Barcelona",
        country="Spain",
        location="Barcelona, Spain",
        high_intensity=True,
        hero_hook="A confession about shame, desire and finally choosing me.",
        hero_tagline="A Night That\nLiberated My Essence",
        situation="Leaving a relationship that kept her small.",
        background="Grew up between cities.",
        story_text="Longer story body here.",
        story_input=None,
        image_source=None,
        cover_image_url=None,
        cover_image_key=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _meditation_story(**kwargs):
    """Meditation fixture with zero confession wording in any story field."""
    defaults = dict(
        story_type=StoryType.meditation,
        title="Morning Light Settles",
        high_intensity=False,
        hero_hook="A quiet morning of returning to myself.",
        hero_tagline="Breath And Soft Light",
        situation="Early light across a wooden floor in a still room.",
        background="Years of rushing finally slowed into presence.",
        # No pose-keyword matches — exercises the type-aware pose fallback.
        story_text="The room held a soft hush while warmth reached the floorboards.",
    )
    defaults.update(kwargs)
    return _story(**defaults)


def test_cover_generation_method_defaults_to_dalle():
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "dalle"):
        assert story_cover.cover_generation_method() == "dalle"
        assert story_cover.uses_template_pipeline(_story()) is False


def test_template_flag_applies_to_confession_and_meditation():
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "template"):
        assert story_cover.uses_template_pipeline(_story()) is True
        assert (
            story_cover.uses_template_pipeline(
                _story(story_type=StoryType.meditation)
            )
            is True
        )
        assert (
            story_cover.uses_template_pipeline(
                _story(story_type=StoryType.transformation)
            )
            is False
        )


def test_story_to_cover_template_payload_maps_fields():
    payload = story_cover.story_to_cover_template_payload(_story())
    assert payload["author_name"] == "Lisa"
    assert payload["gender"] == "female"
    assert payload["orientation"] == "bisexual"
    assert payload["age"] == "28"
    assert payload["city"] == "Barcelona"
    assert payload["country"] == "Spain"
    assert payload["is_explicit"] is True
    assert "shame" in payload["description"]
    # Title packs complete words for fluid wrap (≤3 visual lines in the beige column).
    assert "To" in payload["title"]
    assert "Wasteland" in payload["title"]
    assert payload["photo_url"] is None


def test_build_portrait_only_prompt_is_not_collage_and_reuses_style():
    prompt = build_portrait_only_prompt(_story(), use_llm_brief=False)
    assert CONFESSION_COVER_PHOTOGRAPHY_LOOK_V2 in prompt
    assert "arms outstretched" not in prompt
    assert "28-year-old female" in prompt
    assert "Barcelona" in prompt
    assert "no collage" in prompt.lower()
    assert "no text" in prompt.lower()
    assert "Do not default to a generic triumphant arms-out pose" in prompt
    assert "CONFESSION banner" not in prompt
    assert "[INSERT GENERATED TITLE HERE]" not in prompt
    mood = brief_story_mood_scene(_story())
    assert "Leaving a relationship" in mood


def test_portrait_pose_follows_story_physical_action():
    holding = portrait_pose_instruction(
        _story(
            situation="On a winter Berlin U-Bahn platform holding a letter after goodbye."
        )
    )
    assert "holding a letter" in holding.lower()
    assert "Do not default to a generic triumphant arms-out pose" in holding

    dock = portrait_pose_instruction(
        _story(
            situation="Standing alone on a cold harbour dock at dusk, looking out over the water."
        )
    )
    assert "standing" in dock.lower()
    assert "gaze directed" in dock.lower() or "looking out" in dock.lower()

    balcony = portrait_pose_instruction(
        _story(
            situation="On a Lagos balcony at night, eyes closed in a quiet contemplative moment."
        )
    )
    assert "leaning" in balcony.lower() or "balcony" in balcony.lower()
    assert "contemplative" in balcony.lower()


def test_cover_description_truncates_long_hero_hook_without_mutating_source():
    """Details page keeps the full hook; cover description clamps to hard limit."""
    long_hook = (
        "The October fog pressed against the corrugated walls like a living thing "
        "while my scarred hands moved without thought, brushing another slow layer "
        "of darkening wax onto the forged baluster. Then the voice answered and the "
        "brush stopped mid-stroke. His palm settled on my shoulder, firm and lingering, "
        "the leather warm from his body, and something inside me loosened with a slow, "
        "spreading warmth that had no name."
    )
    assert len(long_hook) > story_cover.CONFESSION_DESCRIPTION_HARD_LIMIT
    story = _story(hero_hook=long_hook)
    payload = story_cover.story_to_cover_template_payload(story)
    assert story.hero_hook == long_hook
    assert len(payload["description"]) <= story_cover.CONFESSION_DESCRIPTION_HARD_LIMIT
    assert long_hook.startswith(payload["description"][:20]) or payload["description"] in long_hook
    assert payload["description"].endswith((".", "!", "?"))


def test_description_truncates_at_last_complete_word():
    long_hook = (
        "Standing alone on a cold harbour dock at dusk, looking out over the water "
        "after finally telling the truth."
    )
    # Old buggy cut landed mid-word on "aft" at the prior 77-char hard limit.
    assert long_hook[:77].endswith("aft")
    payload = story_cover.story_to_cover_template_payload(_story(hero_hook=long_hook))
    desc = payload["description"]
    assert len(desc) <= story_cover.CONFESSION_DESCRIPTION_HARD_LIMIT
    assert desc.endswith((".", "!", "?"))
    assert not desc.endswith(("aft", "co", "the", "a", "in", ","))
    dangling = (
        "On a Lagos balcony at night with city lights behind her, eyes closed in a "
        "quiet moment of choosing herself after the last ferry left the pier tonight."
    )
    trimmed = story_cover.truncate_at_last_word(dangling)
    assert len(trimmed) <= story_cover.CONFESSION_DESCRIPTION_HARD_LIMIT
    assert not trimmed.endswith(("in a", " in", " a", "of", "the", "to"))
    assert "eyes closed" in trimmed


def test_first_complete_sentence_never_ships_fragment():
    """Overlong first sentence must become a complete understandable sentence."""
    # No terminal punctuation and over hard limit — still ends as a sentence.
    overlong = (
        "Standing alone on a cold harbour dock at dusk looking out over the water "
        "after finally telling the truth to everyone who waited there"
    )
    assert "." not in overlong
    assert len(overlong) > story_cover.CONFESSION_DESCRIPTION_HARD_LIMIT
    desc = story_cover.first_complete_sentence(overlong)
    assert desc.endswith(".")
    assert len(desc) <= story_cover.CONFESSION_DESCRIPTION_HARD_LIMIT
    assert len(desc) >= 12
    assert not desc.rstrip(".").endswith(("the", "a", "in", "and", "to", "who"))

    # Multi-sentence helper still returns the first sentence only.
    assert (
        story_cover.first_complete_sentence(
            "I paused at the door. Everything after that still burns."
        )
        == "I paused at the door."
    )

    # Overlong first sentence — prefer a complete clause/sentence, not a fragment.
    multi = (
        "The October fog pressed against the corrugated walls like a living thing "
        "while my scarred hands moved without thought across the cold rail. I left."
    )
    out = story_cover.first_complete_sentence(multi)
    assert out.endswith((".", "!", "?"))
    assert len(out) <= story_cover.CONFESSION_DESCRIPTION_HARD_LIMIT
    assert len(out) >= 12
    assert "scarred." not in out
    assert "living thing" in out.lower() or out == "I left."


def test_pack_cover_confession_keeps_human_readable_prose():
    """Cover body packs consecutive complete sentences — not a short stub."""
    # Second sentence fits under hard → include both (fills the empty band).
    short_pair = (
        "Her amber eyes met mine across the table once more. "
        "Then the room went quiet around us."
    )
    packed = story_cover.pack_cover_confession(short_pair)
    assert packed == short_pair
    assert packed.count(".") == 2
    payload = story_cover.story_to_cover_template_payload(_story(hero_hook=short_pair))
    assert payload["description"] == short_pair

    # Second sentence would exceed hard → keep first only.
    long_second = (
        "I paused at the door. Everything after that still burns when I remember "
        "it now across every quiet hallway and every long winter that followed us "
        "through the city and back again without mercy."
    )
    assert len(long_second) > story_cover.CONFESSION_DESCRIPTION_HARD_LIMIT
    only_first = story_cover.pack_cover_confession(long_second)
    assert only_first == "I paused at the door."

    # Overlong single sentence → complete sense-cut, still ends with .!?
    fog = (
        "The October fog pressed against the corrugated walls like a living thing "
        "while my scarred hands moved without thought across the cold rail forever."
    )
    assert len(fog) > story_cover.CONFESSION_DESCRIPTION_HARD_LIMIT
    cut = story_cover.pack_cover_confession(fog)
    assert cut.endswith((".", "!", "?"))
    assert len(cut) <= story_cover.CONFESSION_DESCRIPTION_HARD_LIMIT
    assert "scarred." not in cut


def test_description_prefers_complete_sentence_within_soft_limit():
    hook = (
        "I paused at the door. Everything after that still burns when I remember "
        "it now across every quiet hallway and every long winter that followed us."
    )
    assert len(hook) > story_cover.CONFESSION_DESCRIPTION_SOFT_LIMIT
    desc = story_cover.truncate_at_sentence(hook)
    assert desc == "I paused at the door."
    assert len(desc) <= story_cover.CONFESSION_DESCRIPTION_SOFT_LIMIT


def test_description_strips_trailing_comma_and_prefers_earlier_sentence():
    """Comma-ending mid-clause must not ship; prefer prior .!? when present."""
    hook = (
        "The silence found me first. Salt settled heavy, like a weight I could not "
        "name while the workshop hummed past any soft limit under cold winter light."
    )
    assert len(hook) > story_cover.CONFESSION_DESCRIPTION_SOFT_LIMIT
    desc = story_cover.truncate_at_sentence(hook)
    assert desc == "The silence found me first."
    assert not desc.endswith(",")

    mid = (
        "Salt settled heavy, fog on the glass and tools on the bench under cold light "
        "while the workshop hummed past any soft limit and every window stayed shut"
    )
    cut = story_cover.truncate_at_sentence(mid)
    assert len(cut) <= story_cover.CONFESSION_DESCRIPTION_HARD_LIMIT
    assert not cut.endswith((",", ";", "and", "the", "a"))
    assert "salt" in cut.lower() or "settled" in cut.lower()


def test_salt_description_prefers_semicolon_clause_over_trailing_comma():
    """The Salt cover copy: semicolon clause → clean sentence, no dangling comma."""
    hook = "Her wrist smelled of salt; the wanting settled heavy,"
    desc = story_cover.truncate_at_sentence(hook)
    assert desc == "Her wrist smelled of salt."
    assert not desc.endswith(",")
    payload = story_cover.story_to_cover_template_payload(
        _story(hero_hook=hook, title="The Salt", hero_tagline="Salt stays on the wrist you")
    )
    assert payload["description"] == "Her wrist smelled of salt."
    assert payload["title"] == "The Salt"


def test_subtitle_wraps_and_truncates_to_hard_line_limit():
    long = "The memory stirred but my boundaries held"
    payload = story_cover.story_to_cover_template_payload(_story(hero_tagline=long))
    # Single span preferred — CSS wraps inside the beige column.
    sub = payload["subtitle"]
    budget = story_cover.SUBTITLE_LINE_HARD_LIMIT * story_cover.SUBTITLE_MAX_VISUAL_LINES
    assert len(sub) <= budget
    assert "\n" not in sub or all(
        len(ln) <= story_cover.SUBTITLE_LINE_HARD_LIMIT for ln in sub.split("\n") if ln
    )
    assert "memory" in sub.lower()
    assert not re.search(r"\bHEL$", sub, re.I)
    assert not re.search(r"\bBOUNDAR$", sub, re.I)


def test_subtitle_stays_within_torn_border_column():
    """Long taglines fill one span (CSS wraps) left of the torn photo edge."""
    long = "The hands that once trembled now rested"
    payload = story_cover.story_to_cover_template_payload(_story(hero_tagline=long))
    sub = payload["subtitle"]
    budget = story_cover.SUBTITLE_LINE_HARD_LIMIT * story_cover.SUBTITLE_MAX_VISUAL_LINES
    assert len(sub) <= budget
    assert "hands" in sub.lower()
    assert "trembled" in sub.lower()
    assert "trembl" not in sub.lower().replace("trembled", "")


def test_title_fills_beige_column_without_skinny_stacks():
    """Titles use a full-width span so CSS wraps — not THE / IRON one-word stacks."""
    payload = story_cover.story_to_cover_template_payload(
        _story(title="The Iron and the Grain")
    )
    title = payload["title"]
    assert title == "The Iron and the Grain"
    assert "\n" not in title
    budget = story_cover.TITLE_LINE_HARD_LIMIT * story_cover.TITLE_MAX_VISUAL_LINES
    assert len(title) <= budget

    long_title = story_cover.story_to_cover_template_payload(
        _story(title="On My Own Way Home Tonight Forever More Words")
    )["title"]
    assert "On" in long_title and "My" in long_title
    assert len(long_title) <= budget


def test_iron_subtitle_keeps_full_carried_tagline():
    """Long cellar tagline packs like public tagline gen (≤2 lines, no mid-word cut)."""
    tag = "A CELLAR TO LAY DOWN WHAT YOU'VE **CARRIED** TOO LONG"
    payload = story_cover.story_to_cover_template_payload(_story(hero_tagline=tag))
    sub = payload["subtitle"]
    assert "CARRIED" in sub.upper()
    assert "**" not in sub
    assert "LONG" in sub.upper()
    budget = story_cover.SUBTITLE_LINE_HARD_LIMIT * story_cover.SUBTITLE_MAX_VISUAL_LINES
    flat = sub.replace("\n", " ")
    assert len(flat) <= budget + 1  # newline join vs space
    for line in sub.split("\n"):
        if line:
            assert len(line) <= story_cover.SUBTITLE_LINE_HARD_LIMIT


def test_portrait_prompt_includes_framing_and_anti_repetition():
    prompt = build_portrait_only_prompt(_story(), use_llm_brief=False)
    assert "full head and shoulders" in prompt
    assert "4:5" in prompt
    assert "adequate headroom" in prompt
    assert "bent-neck" in prompt.lower() or "bent/crooked neck" in prompt.lower()
    assert "Anti-repetition" in prompt
    assert "Narrative moment to depict" in prompt


def test_retired_look_constant_stays_sepia_for_collage_and_meditation():
    """The pre-pivot LOOK is retired from the confession portrait path only.

    It must stay byte-identical because two other consumers still depend on it:
    CONFESSION_COVER_PHOTOGRAPHY_STYLE (→ dalle/collage) and the meditation alias.
    """
    look = CONFESSION_COVER_PHOTOGRAPHY_LOOK.lower()
    assert "sepia" in look
    assert "black-and-white" in look
    assert "film grain" in look
    assert "skin texture" in look
    assert "depth of field" in look
    assert "fabric folds" in look
    assert "amber" in look or "warm-brown" in look
    assert "plain grayscale" in look

    from app.utils.prompts import (
        CONFESSION_COVER_PHOTOGRAPHY_STYLE,
        MEDITATION_COVER_PHOTOGRAPHY_LOOK,
    )

    assert CONFESSION_COVER_PHOTOGRAPHY_STYLE.startswith(
        CONFESSION_COVER_PHOTOGRAPHY_LOOK
    )
    assert MEDITATION_COVER_PHOTOGRAPHY_LOOK is CONFESSION_COVER_PHOTOGRAPHY_LOOK

    from app.utils.prompts import CONFESSION_COVER_PORTRAIT_ENVIRONMENT

    env = CONFESSION_COVER_PORTRAIT_ENVIRONMENT.lower()
    assert "emotionally intimate" in env
    assert "clutter" in env


def test_confession_look_v2_is_full_color_and_drops_monochrome_language():
    """LOOK_V2 pivots confession portraits to warm golden-hour lifestyle color."""
    look = CONFESSION_COVER_PHOTOGRAPHY_LOOK_V2.lower()
    assert look.startswith("photography style (always apply, non-negotiable):")
    assert "full color" in look
    assert "golden-hour" in look
    assert "amber" in look and "honey" in look
    assert "documentary lifestyle photography" in look
    assert "editorial travel/festival photography" in look
    assert "never desaturated or monochrome" in look

    # Realism cues carried over from the retired LOOK — the color pivot must not
    # silently drop them again (they do real anti-AI work).
    assert "depth of field" in look
    assert "readable mid-ground" in look
    assert "fabric folds" in look

    # sepia / black-and-white survive only inside the closing prohibition — the
    # style language itself must carry no monochrome instruction.
    # ("monochrome" is excluded from this list: LOOK_V2 uses it only in the
    #  negated "never desaturated or monochrome" phrasing.)
    body, sep, prohibition = look.partition("avoid cold tones")
    assert sep, "expected the closing 'Avoid cold tones…' prohibition"
    for banned in ("sepia", "black-and-white", "grayscale", "greyscale"):
        assert banned not in body, f"{banned!r} leaked into LOOK_V2 style language"
    assert "desaturated/sepia/black-and-white" in prohibition


def test_build_portrait_only_prompt_always_requires_rich_environment():
    quiet = build_portrait_only_prompt(
        _story(
            situation="Sitting alone by a window at night in a quiet contemplative moment.",
            title="Second Draft",
        ),
        use_llm_brief=False,
    )
    assert "rich environmental detail" in quiet
    assert "never a flat, plain, or empty background" in quiet
    assert "at least two concrete background anchors" in quiet
    assert "Do not default to a generic triumphant arms-out pose" in quiet
    assert "arms outstretched" not in quiet
    assert "Physically ground the subject" in quiet
    assert "STORY ANALYSIS" in quiet
    assert "Emotional state" in quiet
    assert "Distinctive visual details from the confession" in quiet
    assert "Atmosphere:" in quiet
    assert CONFESSION_COVER_ENERGY in quiet
    assert CONFESSION_COVER_BRAND_COLLECTION in quiet
    assert CONFESSION_COVER_ANTI_AI_LOOK in quiet
    assert "Do NOT use a bent/crooked neck" in quiet
    assert "Narrator alone" in quiet


def test_quiet_lisbon_window_prompt_has_scene_richness_not_arms_out():
    """Quiet Lisbon confession: environmental richness, grounded pose, no arms-out."""
    story = _story(
        first_name="Elena",
        city="Lisbon",
        country="Portugal",
        location="Lisbon, Portugal",
        title="Second Draft",
        situation=(
            "Sitting by a rain-streaked apartment window at dusk in Lisbon, "
            "coat on the chair, notebook open, quiet contemplative moment."
        ),
        background="A writer rewriting the ending of her own life.",
        story_text=(
            "Rain on the window. The harbor lights below. She held the notebook "
            "and did not look at the camera."
        ),
        high_intensity=False,
    )
    detail = portrait_scene_detail(story)
    assert "Scene detail:" in detail
    assert "window" in detail.lower()
    assert "Lisbon" in detail

    analysis = portrait_story_analysis(story)
    assert "STORY ANALYSIS" in analysis
    assert "Emotional state" in analysis
    assert "window" in analysis.lower()
    assert "quiet" in analysis.lower() or "vulnerable" in analysis.lower()

    prompt = build_portrait_only_prompt(story, use_llm_brief=False)
    assert "STORY ANALYSIS" in prompt
    assert "Narrative moment to depict" in prompt
    assert "window" in prompt.lower()
    assert "rain" in prompt.lower() or "dusk" in prompt.lower()
    assert "at least two concrete background anchors" in prompt
    assert "practical light" in prompt
    # Skin realism comes from the anti-AI block (LOOK_V2 carries the depth-of-field
    # and fabric-folds cues; it does not restate skin texture).
    assert "skin must show natural texture" in prompt
    assert "depth of field" in prompt
    assert "fabric folds" in prompt
    assert "Physically ground the subject" in prompt
    assert "Do not default to a generic triumphant arms-out pose" in prompt
    assert "arms outstretched" not in prompt
    assert "triumphant arms-out / face-skyward pose is allowed" not in prompt
    assert "Do NOT use a bent/crooked neck" in prompt
    assert "do not force wild or provocative" in prompt.lower()
    assert CONFESSION_COVER_PHOTOGRAPHY_LOOK_V2 in prompt


def test_partner_story_allows_second_person_and_intimacy_when_intense():
    story = _story(
        high_intensity=True,
        situation="In bed with my partner after we finally told the truth.",
        story_text=(
            "We lay together in the hotel bedroom. I kissed him and felt the sheets "
            "rumple under my bare shoulder."
        ),
    )
    prompt = build_portrait_only_prompt(story, use_llm_brief=False)
    assert "second person" in prompt.lower()
    assert "partner" in prompt.lower() or "embrace" in prompt.lower()
    assert "tasteful editorial" in prompt.lower() or "bare shoulders" in prompt.lower()
    assert "Do NOT use a bent/crooked neck" in prompt
    pose = portrait_pose_instruction(story)
    assert "bent/crooked neck" in pose


def test_friendship_story_casts_a_small_group_without_intimacy_cues():
    """Connection themes beyond partner/intimacy now widen the frame."""
    story = _story(
        high_intensity=False,
        situation="A weekend at the festival with my oldest friends.",
        story_text="My friends and I laughed together until the lanterns came on.",
    )
    prompt = build_portrait_only_prompt(story, use_llm_brief=False)
    assert "small group" in prompt.lower()
    assert "two or three other people" in portrait_cast_instruction(story)
    # Group framing must not read as a crowd shot.
    assert "not an anonymous crowd" in prompt


def test_family_story_casts_more_than_one_person():
    story = _story(
        high_intensity=False,
        situation="Sunday lunch with my mother.",
        story_text="She set the table and we talked for hours.",
    )
    cast = portrait_cast_instruction(story)
    assert "second person" in cast or "small group" in cast


def test_solitude_outweighs_explicit_partner_wording():
    """'alone, remembering my husband' stays a solo portrait."""
    story = _story(
        high_intensity=False,
        situation="Alone in the empty house we used to share.",
        story_text="No one else knew. I was lonely and I missed my husband.",
    )
    prompt = build_portrait_only_prompt(story, use_llm_brief=False)
    assert "Narrator alone" in prompt
    assert "second person" not in prompt.lower()


def test_reflective_solo_story_stays_solo():
    story = _story(
        high_intensity=False,
        situation="Sitting alone by a window at night, quiet and contemplative.",
        story_text="I wrote in my notebook and watched the rain.",
    )
    assert "Narrator alone" in portrait_cast_instruction(story)


def test_brief_connection_theme_casts_even_when_story_is_neutral():
    """A STORY BRIEF naming connection widens the cast on its own."""
    neutral = _story(
        high_intensity=False,
        situation="An afternoon in the city.",
        story_text="The light changed over the rooftops.",
    )
    assert "Narrator alone" in portrait_cast_instruction(neutral)

    brief = (
        "STORY BRIEF (LLM analysis of the complete confession — invent nothing "
        "that contradicts the text):\n"
        "Emotional register: joyful and open.\n"
        "Setting: a rooftop at golden hour.\n"
        "Atmosphere: warm and hazy.\n"
        "Distinctive visuals: her friends laughing beside her.\n"
        "Do not invent: nothing beyond the text."
    )
    cast = portrait_cast_instruction(neutral, brief_text=brief)
    assert "second person" in cast or "small group" in cast


def test_brief_do_not_invent_clause_is_not_scanned_for_cast():
    """'Do not invent: other people' must not itself cast a second person."""
    story = _story(
        high_intensity=False,
        situation="A solitary morning.",
        story_text="I drank my coffee and listened to the street.",
    )
    brief = (
        "STORY BRIEF (LLM analysis of the complete confession):\n"
        "Emotional register: calm.\n"
        "Do not invent: other people, crowds, companions, or friends."
    )
    assert "Narrator alone" in portrait_cast_instruction(story, brief_text=brief)


def _quiet_vulnerable_story():
    return _story(
        first_name="Elena",
        gender="female",
        age=29,
        city="Lisbon",
        country="Portugal",
        location="Lisbon, Portugal",
        title="Second Draft",
        high_intensity=False,
        hero_hook="I sat with the shame and the quiet longing and did not look away.",
        situation=(
            "Sitting by a rain-streaked apartment window at dusk in Lisbon, "
            "coat on the chair, notebook open, quiet contemplative vulnerable moment."
        ),
        background="A writer rewriting the ending of her own life.",
        story_text=(
            "Rain on the window. The harbor lights below. I held the notebook with "
            "trembling hands, ashamed and tender, and did not look at the camera."
        ),
    )


def _bold_provocative_story():
    return _story(
        first_name="Mara",
        gender="female",
        age=31,
        city="Berlin",
        country="Germany",
        location="Berlin, Germany",
        title="Neon After the Door",
        high_intensity=True,
        hero_hook="I walked into the night daring and finally free.",
        situation=(
            "Dancing under neon club lights at midnight in Berlin, dress in motion, "
            "wild and liberating after telling the truth."
        ),
        background="A night of reckless release after years of careful silence.",
        story_text=(
            "The neon painted my face. I danced bold and euphoric, lipstick smeared, "
            "heels clicking, finally free — a thrill that felt provocative and alive."
        ),
    )


def _intimate_partner_story():
    return _story(
        first_name="Jonas",
        gender="male",
        age=34,
        city="Paris",
        country="France",
        location="Paris, France",
        title="After We Told the Truth",
        high_intensity=True,
        hero_hook="Desire settled between us after the confession.",
        situation=(
            "In a hotel bedroom at night with my partner after we finally told the truth, "
            "lamplight on rumpled sheets."
        ),
        background="Two people choosing honesty over performance.",
        story_text=(
            "We lay together in the hotel bedroom. I kissed him and felt the sheets "
            "rumple under my bare shoulder — intimate, sensual stillness after the truth."
        ),
    )


def test_portrait_prompts_differentiate_quiet_bold_intimate_energy():
    """Three confession registers: shared LOOK; differentiated emotion/energy/scene.

    Portrait size/model stay in image_generator.py (1024x1792 / 1024x1536) —
    this builder only emits prompt text and must not set model or size.
    """
    quiet = build_portrait_only_prompt(_quiet_vulnerable_story(), use_llm_brief=False)
    bold = build_portrait_only_prompt(_bold_provocative_story(), use_llm_brief=False)
    intimate = build_portrait_only_prompt(_intimate_partner_story(), use_llm_brief=False)

    for prompt in (quiet, bold, intimate):
        assert CONFESSION_COVER_PHOTOGRAPHY_LOOK_V2 in prompt
        assert CONFESSION_COVER_ENERGY in prompt
        assert CONFESSION_COVER_BRAND_COLLECTION in prompt
        assert CONFESSION_COVER_ANTI_AI_LOOK in prompt
        assert "STORY ANALYSIS" in prompt
        assert "Emotional state" in prompt
        assert "Distinctive visual details from the confession" in prompt
        assert "Atmosphere:" in prompt
        assert "OPENAI_IMAGE_MODEL" not in prompt
        assert "1024x1792" not in prompt
        assert "1024x1536" not in prompt

    # Quiet: soft register, rain/window atmosphere, no forced provocation.
    assert "do not force wild or provocative" in quiet.lower()
    assert "lisbon" in quiet.lower()
    assert "rain" in quiet.lower() or "window" in quiet.lower()
    assert "shame" in quiet.lower() or "tender" in quiet.lower() or "vulnerable" in quiet.lower()

    # Bold: outward/daring energy and night-out specifics.
    assert "outward, daring, and liberating" in bold.lower()
    assert "berlin" in bold.lower()
    assert "neon" in bold.lower() or "danc" in bold.lower()
    assert "liberat" in bold.lower() or "euphor" in bold.lower() or "thrill" in bold.lower()

    # Intimate: partner heat distinct from quiet solitude.
    assert "intimate" in intimate.lower()
    assert "partner" in intimate.lower() or "second person" in intimate.lower()
    assert "bed" in intimate.lower() or "sheet" in intimate.lower()
    assert "paris" in intimate.lower()

    # Prompts must diverge on story-specific content (not age/gender/location alone).
    assert quiet != bold
    assert bold != intimate
    assert quiet != intimate
    assert "do not force wild or provocative" in quiet.lower()
    assert "do not force wild or provocative" not in bold.lower()
    # Story-analysis blocks (not shared ENVIRONMENT examples) must differ by register.
    quiet_analysis = quiet.split("Confession energy:")[0]
    bold_analysis = bold.split("Confession energy:")[0]
    intimate_analysis = intimate.split("Confession energy:")[0]
    assert "lisbon" in quiet_analysis.lower() and "notebook" in quiet_analysis.lower()
    assert "berlin" in bold_analysis.lower() and (
        "neon" in bold_analysis.lower() or "club" in bold_analysis.lower()
    )
    assert "paris" in intimate_analysis.lower() and (
        "sheet" in intimate_analysis.lower() or "bed" in intimate_analysis.lower()
    )
    assert "neon" not in quiet_analysis.lower()
    assert "lisbon" not in bold_analysis.lower()


def test_portrait_prompt_builder_does_not_configure_image_api():
    """Portrait prompt assembly must not set DALL-E model/size (template slot ratio)."""
    import inspect

    import app.utils.story_image_prompt as sip

    src = inspect.getsource(sip.build_portrait_only_prompt)
    assert "OPENAI_IMAGE_MODEL" not in src
    assert "1024x1792" not in src
    assert "1024x1536" not in src
    assert "images.generate" not in src
    assert "size=" not in src


def test_dalle_flag_delegates_to_unchanged_dalle_path():
    story = _story()
    db = MagicMock()
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "dalle"):
        with patch("app.utils.story_image_prompt.try_generate_story_cover") as dalle:
            story_cover.try_generate_story_cover(
                db, story, image_prompt="prompt-x", force_rebuild=True
            )
            dalle.assert_called_once()
            kwargs = dalle.call_args.kwargs
            assert kwargs["image_prompt"] == "prompt-x"
            assert kwargs["force_rebuild"] is True


def test_template_flag_uses_portrait_then_playwright():
    story = _story()
    db = MagicMock()
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "template"):
        with patch.object(story_cover.settings, "OPENAI_API_KEY", "sk-test"):
            with patch(
                "app.utils.story_image_prompt.build_portrait_only_prompt",
                return_value="portrait only prompt",
            ) as build_p:
                with patch(
                    "app.utils.image_generator.generate_ai_cover_image",
                    return_value=("https://cdn/portrait.jpg", "images/portrait.jpg"),
                ) as dalle:
                    with patch(
                        "app.cover_template.render.render_cover_png_sync",
                        return_value=b"fake-png",
                    ) as render:
                        with patch(
                            "app.utils.s3.upload_image_to_s3",
                            return_value=("https://cdn/cover.png", "images/cover.png"),
                        ):
                            with patch("app.utils.s3.delete_s3_object") as delete_obj:
                                with patch(
                                    "app.utils.story_image_prompt.try_generate_story_cover"
                                ) as collage:
                                    story_cover.try_generate_story_cover(
                                        db, story, image_prompt="ignored-collage"
                                    )
                                    build_p.assert_called_once()
                                    dalle.assert_called_once()
                                    assert (
                                        dalle.call_args.kwargs["image_prompt"]
                                        == "portrait only prompt"
                                    )
                                    render.assert_called_once()
                                    payload = render.call_args.args[0]
                                    assert (
                                        payload["photo_url"]
                                        == "https://cdn/portrait.jpg"
                                    )
                                    collage.assert_not_called()
                                    assert story.image_source == ImageSource.template_v1
                                    assert any(
                                        c.args and c.args[0] == "images/portrait.jpg"
                                        for c in delete_obj.call_args_list
                                    )


def test_template_flag_meditation_uses_template_pipeline():
    story = _story(story_type=StoryType.meditation)
    db = MagicMock()
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "template"):
        with patch.object(story_cover.settings, "OPENAI_API_KEY", "sk-test"):
            with patch(
                "app.utils.story_image_prompt.build_portrait_only_prompt",
                return_value="meditation portrait prompt",
            ):
                with patch(
                    "app.utils.image_generator.generate_ai_cover_image",
                    return_value=("https://cdn/portrait.jpg", "images/portrait.jpg"),
                ):
                    with patch(
                        "app.cover_template.render.render_cover_png_sync",
                        return_value=b"fake-png",
                    ) as render:
                        with patch(
                            "app.utils.s3.upload_image_to_s3",
                            return_value=("https://cdn/cover.png", "images/cover.png"),
                        ):
                            with patch("app.utils.s3.delete_s3_object"):
                                with patch(
                                    "app.utils.story_image_prompt.try_generate_story_cover"
                                ) as collage:
                                    story_cover.try_generate_story_cover(
                                        db, story, image_prompt=None
                                    )
                                    render.assert_called_once()
                                    collage.assert_not_called()
                                    assert story.image_source == ImageSource.template_v1


def test_member_upload_guard_skips_both_pipelines():
    story = _story(
        image_source=ImageSource.user_uploaded,
        cover_image_url="https://cdn/member.jpg",
    )
    db = MagicMock()
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "template"):
        with patch(
            "app.cover_template.render.render_cover_png_sync"
        ) as render:
            with patch("app.utils.story_image_prompt.try_generate_story_cover") as dalle:
                story_cover.try_generate_story_cover(
                    db, story, image_prompt=None, replace_member_cover=False
                )
                render.assert_not_called()
                dalle.assert_not_called()


def test_meditation_portrait_uses_inward_energy():
    from app.utils.prompts import (
        MEDITATION_COVER_ANTI_AI_LOOK,
        MEDITATION_COVER_ENERGY,
        MEDITATION_COVER_PHOTOGRAPHY_LOOK,
    )

    prompt = build_portrait_only_prompt(
        _meditation_story(
            situation="Breathing slowly on a sunlit bed by the window.",
            story_text="I place a hand on my chest and feel the breath settle.",
        ),
        use_llm_brief=False,
    )
    assert MEDITATION_COVER_ENERGY in prompt
    assert MEDITATION_COVER_PHOTOGRAPHY_LOOK in prompt
    assert MEDITATION_COVER_ANTI_AI_LOOK in prompt
    assert "CONFESSION — outward" not in prompt
    assert "STORY ANALYSIS" in prompt or "STORY BRIEF" in prompt
    assert "meditation" in prompt.lower()
    assert "confession" not in prompt.lower()


def test_portrait_brief_heuristic_without_llm():
    from app.utils.story_image_prompt import build_portrait_story_brief

    brief = build_portrait_story_brief(
        _story(
            situation="On a harbour dock at dusk with salt air.",
            story_text="The fog pressed against the corrugated walls like a living thing.",
        ),
        use_llm=False,
    )
    assert "STORY ANALYSIS" in brief
    assert "Emotional state" in brief or "Emotional" in brief
    assert "harbour" in brief.lower() or "fog" in brief.lower() or "dock" in brief.lower()


def test_openai_image_payload_uses_natural_style_for_dalle():
    with patch.object(story_cover.settings, "OPENAI_API_KEY", "sk-test"):
        with patch.object(story_cover.settings, "OPENAI_IMAGE_MODEL", "dall-e-3"):
            with patch("app.utils.image_generator.requests.post") as post:
                post.return_value.raise_for_status = MagicMock()
                post.return_value.json.return_value = {
                    "data": [{"b64_json": __import__("base64").b64encode(b"fake").decode()}]
                }
                with patch(
                    "app.utils.image_generator.upload_image_to_s3",
                    return_value=("https://cdn/x.jpg", "images/x.jpg"),
                ):
                    from app.utils.image_generator import generate_ai_cover_image

                    generate_ai_cover_image(
                        title="T",
                        story_type="confession",
                        author_name="Liam",
                        image_prompt="A portrait in warm light",
                        gender="male",
                    )
                    payload = post.call_args.kwargs.get("json") or post.call_args[1].get("json")
                    if payload is None:
                        payload = post.call_args.args[1] if len(post.call_args.args) > 1 else post.call_args.kwargs["json"]
                    # requests.post(url, json=payload, ...)
                    assert post.call_args.kwargs["json"]["style"] == "natural"
                    assert post.call_args.kwargs["json"]["model"] == "dall-e-3"


# ---------------------------------------------------------------------------
# Complete-story visual analysis + gpt-image-2 budgeting (portrait path)
# ---------------------------------------------------------------------------

def _fake_llm(response_text: str):
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content=response_text)
    return llm


_LONG_STORY = (
    "The rain started before I reached the harbour. " * 60
)  # ~4,800 chars — far beyond the old 3,500-char excerpt cap


def test_visual_analysis_receives_complete_story_not_excerpt():
    """The analysis model must see the COMPLETE story, not a 3,500-char slice."""
    from app.utils import story_image_prompt

    story = _story(story_text=_LONG_STORY, story_input=None)
    llm = _fake_llm(
        "Emotional register: raw and rising\n"
        "Setting: harbour wall at dusk\n"
        "Atmosphere: salt air, last light\n"
        "Distinctive visuals: rain-wet coat, harbour chain, folded letter\n"
        "Do not invent: other people, studio backdrop"
    )
    with patch.object(story_image_prompt.settings, "XAI_API_KEY", "xai-test"):
        with patch.object(story_image_prompt, "get_story_llm", return_value=llm):
            brief = story_image_prompt.build_portrait_story_brief(story)

    sent = llm.invoke.call_args.args[0]
    # The complete story text reached the analysis model.
    assert _LONG_STORY.strip() in sent
    assert "Complete confession text:" in sent
    # Structured context is included.
    assert "Title: To Wasteland On My Own" in sent
    assert "Hero hook:" in sent
    assert "Situation: Leaving a relationship that kept her small." in sent
    assert "Background: Grew up between cities." in sent
    # The brief (not the story) is what the portrait prompt consumes.
    assert "STORY BRIEF" in brief
    assert "Emotional register: raw and rising" in brief
    assert _LONG_STORY[:200] not in brief


def test_visual_analysis_prompt_is_concise_not_the_story():
    """The final portrait prompt carries the concise brief, not the full story."""
    from app.utils import story_image_prompt

    story = _story(story_text=_LONG_STORY)
    llm = _fake_llm(
        "Emotional register: raw and rising\n"
        "Setting: harbour wall at dusk\n"
        "Atmosphere: salt air, last light\n"
        "Distinctive visuals: rain-wet coat, harbour chain, folded letter\n"
        "Do not invent: other people, studio backdrop"
    )
    with patch.object(story_image_prompt.settings, "XAI_API_KEY", "xai-test"):
        with patch.object(story_image_prompt, "get_story_llm", return_value=llm):
            prompt = story_image_prompt.build_portrait_only_prompt(story)

    assert "Emotional register: raw and rising" in prompt
    assert "rain-wet coat" in prompt
    # Whole story must NOT be passed through to the image model.
    assert _LONG_STORY not in prompt
    # Portrait-only constraint stays explicit.
    assert "no text" in prompt
    assert "no typography" in prompt
    assert "no badges" in prompt
    assert "no frame" in prompt


def test_meditation_analysis_and_prompt_never_say_confession():
    """No 'confession' wording may leak into meditation analysis or prompts."""
    from app.utils import story_image_prompt
    from app.utils.prompts import (
        MEDITATION_COVER_ANTI_AI_LOOK,
        MEDITATION_COVER_ENERGY,
        MEDITATION_COVER_PHOTOGRAPHY_LOOK,
    )

    # Genuinely meditation-shaped fixture (no confession hero_hook) and no
    # pose keywords — so the type-aware pose fallback is exercised.
    meditation = _meditation_story()
    assert "confession" not in (meditation.hero_hook or "").lower()
    assert "confession" not in (meditation.situation or "").lower()
    assert "confession" not in (meditation.story_text or "").lower()
    assert "confession" not in (meditation.background or "").lower()

    pose = story_image_prompt.portrait_pose_instruction(meditation)
    assert "change it per meditation" in pose
    assert "confession" not in pose.lower()

    # Heuristic path must produce a full meditation portrait prompt with zero leaks.
    heuristic_prompt = story_image_prompt.build_portrait_only_prompt(
        meditation, use_llm_brief=False
    )
    assert "confession" not in heuristic_prompt.lower()
    assert "THIS meditation's scene" in heuristic_prompt
    assert "feeling arc of THIS meditation" in heuristic_prompt
    assert "change it per meditation" in heuristic_prompt
    assert "Anti-repetition: each meditation" in heuristic_prompt
    assert MEDITATION_COVER_ENERGY in heuristic_prompt
    assert MEDITATION_COVER_PHOTOGRAPHY_LOOK in heuristic_prompt
    assert MEDITATION_COVER_ANTI_AI_LOOK in heuristic_prompt
    assert "Guiding principle: use the specific details and emotional essence of THIS meditation" in heuristic_prompt
    # Story beat comes from the meditation situation (not the confession fixture hook).
    assert "Early light across a wooden floor" in heuristic_prompt
    assert "A confession about" not in heuristic_prompt

    # LLM brief path must ask for meditation energy and keep the final prompt clean.
    llm = _fake_llm(
        "Emotional register: inward and settling\n"
        "Setting: wooden floor in early light\n"
        "Atmosphere: soft hush, warm air\n"
        "Distinctive visuals: floorboards, pale morning light, still room\n"
        "Do not invent: crowds, night club"
    )
    with patch.object(story_image_prompt.settings, "XAI_API_KEY", "xai-test"):
        with patch.object(story_image_prompt, "get_story_llm", return_value=llm):
            brief = story_image_prompt.build_portrait_story_brief(meditation)
            llm_prompt = story_image_prompt.build_portrait_only_prompt(meditation)
    sent = llm.invoke.call_args.args[0]
    assert "Story type: meditation" in sent
    assert "Complete meditation text:" in sent
    assert "inward, reflective, contemplative" in sent
    assert "Hero hook: A quiet morning of returning to myself." in sent
    assert "confession" not in sent.lower()
    assert "STORY BRIEF" in brief
    assert "complete meditation" in brief
    assert "confession" not in brief.lower()
    assert "confession" not in llm_prompt.lower()
    assert "Emotional register: inward and settling" in llm_prompt
    assert "change it per meditation" in llm_prompt


def test_llm_analysis_failure_falls_back_type_aware():
    """Grok failure degrades to the heuristic — still correct story-type wording."""
    from app.utils import story_image_prompt

    meditation = _meditation_story(
        situation="Early hush in a room with pale curtains.",
        story_text="The fog pressed against the glass while warmth reached the floor.",
    )
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("provider outage")
    with patch.object(story_image_prompt.settings, "XAI_API_KEY", "xai-test"):
        with patch.object(story_image_prompt, "get_story_llm", return_value=llm):
            brief = story_image_prompt.build_portrait_story_brief(meditation)
    assert "STORY ANALYSIS" in brief
    assert "confession" not in brief.lower()
    assert "meditation" in brief.lower()

    confession = _story(
        situation="Telling the truth at dinner after twenty years.",
        story_text="The candle guttered and I said it plainly.",
    )
    with patch.object(story_image_prompt.settings, "XAI_API_KEY", "xai-test"):
        with patch.object(story_image_prompt, "get_story_llm", return_value=llm):
            brief = story_image_prompt.build_portrait_story_brief(confession)
    assert "STORY ANALYSIS" in brief
    assert "confession" in brief.lower()


def test_gpt_image_model_needs_no_prompt_trimming():
    """gpt-image-2 accepts long prompts — no aggressive truncation."""
    from app.utils import story_image_prompt

    story = _story(
        story_text=_LONG_STORY,
        situation="Standing at the harbour wall while the rain came in.",
    )
    with patch.object(story_image_prompt.settings, "OPENAI_IMAGE_MODEL", "gpt-image-2"):
        assert story_image_prompt._portrait_prompt_char_budget() is None
        prompt = story_image_prompt.build_portrait_only_prompt(story, use_llm_brief=False)
        # Untrimmed: full brand + story blocks intact.
        assert "Anti-repetition" in prompt
        assert len(prompt) > 4000  # gpt-image-2 budget would have clipped nothing


def test_dalle_model_still_budgets_prompt():
    """Legacy dall-e-3 configuration keeps the 4,000-char safety budget."""
    from app.utils import story_image_prompt

    with patch.object(story_image_prompt.settings, "OPENAI_IMAGE_MODEL", "dall-e-3"):
        assert story_image_prompt._portrait_prompt_char_budget() == 3900
        story = _story(
            story_text=_LONG_STORY,
            situation="Standing at the harbour wall while the rain came in.",
        )
        prompt = story_image_prompt.build_portrait_only_prompt(story, use_llm_brief=False)
        assert len(prompt) <= 3900
        # Story-specific blocks survive; boilerplate drops first.
        assert "Narrative moment to depict" in prompt
        assert "STORY ANALYSIS" in prompt


def test_image_generator_guard_trims_only_for_dalle_models():
    """generate_ai_cover_image trims >4,000 chars for dall-e, never for gpt-image."""
    import base64

    long_prompt = "Rain on the harbour wall. " * 300  # ~7,500 chars

    with patch.object(story_cover.settings, "OPENAI_API_KEY", "sk-test"):
        with patch.object(story_cover.settings, "OPENAI_IMAGE_MODEL", "dall-e-3"):
            with patch("app.utils.image_generator.requests.post") as post:
                post.return_value.raise_for_status = MagicMock()
                post.return_value.json.return_value = {
                    "data": [{"b64_json": base64.b64encode(b"fake").decode()}]
                }
                with patch(
                    "app.utils.image_generator.upload_image_to_s3",
                    return_value=("https://cdn/x.jpg", "images/x.jpg"),
                ):
                    from app.utils.image_generator import generate_ai_cover_image

                    generate_ai_cover_image(
                        title="T",
                        story_type="confession",
                        author_name="Liam",
                        image_prompt=long_prompt,
                        gender="male",
                    )
                    sent_prompt = post.call_args.kwargs["json"]["prompt"]
                    assert len(sent_prompt) <= 4000

        with patch.object(story_cover.settings, "OPENAI_IMAGE_MODEL", "gpt-image-2"):
            with patch("app.utils.image_generator.requests.post") as post:
                post.return_value.raise_for_status = MagicMock()
                post.return_value.json.return_value = {
                    "data": [{"b64_json": base64.b64encode(b"fake").decode()}]
                }
                with patch(
                    "app.utils.image_generator.upload_image_to_s3",
                    return_value=("https://cdn/x.jpg", "images/x.jpg"),
                ):
                    from app.utils.image_generator import generate_ai_cover_image

                    generate_ai_cover_image(
                        title="T",
                        story_type="confession",
                        author_name="Liam",
                        image_prompt=long_prompt,
                        gender="male",
                    )
                    sent_prompt = post.call_args.kwargs["json"]["prompt"]
                    # Identity lock prefix + full prompt, untrimmed.
                    assert sent_prompt.startswith("The person depicted MUST be")
                    assert len(sent_prompt) > 7000
                    # gpt-image models must not send the dall-e "style" param.
                    assert "style" not in post.call_args.kwargs["json"]


def test_v1_and_v2_cover_generation_method_routing():
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "v1"):
        assert story_cover.is_v1_method() is True
        assert story_cover.is_v2_method() is False
        assert story_cover.uses_template_pipeline(_story()) is True
        assert story_cover.uses_v2_pipeline(_story()) is False

    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "template"):
        assert story_cover.is_v1_method() is True
        assert story_cover.is_v2_method() is False
        assert story_cover.uses_template_pipeline(_story()) is True
        assert story_cover.uses_v2_pipeline(_story()) is False

    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "v2"):
        assert story_cover.is_v1_method() is False
        assert story_cover.is_v2_method() is True
        assert story_cover.uses_template_pipeline(_story()) is False
        assert story_cover.uses_v2_pipeline(_story()) is True

    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "dalle"):
        assert story_cover.is_v1_method() is False
        assert story_cover.is_v2_method() is False
        assert story_cover.uses_template_pipeline(_story()) is False
        assert story_cover.uses_v2_pipeline(_story()) is False


def test_build_v2_cover_prompt_matches_client_specification_exactly():
    from app.utils.story_image_prompt import build_v2_cover_prompt

    story = _story(
        story_type=StoryType.confession,
        title="Two Men and Nia",
        hero_hook="They took a little GHB in Bacardi cola.",
        location="Wales, UK",
        city="Wales",
        country="UK",
        age=23,
        gender="male",
        sexual_orientation="heterosexual",
        high_intensity=True,
        first_name="Rory",
    )
    custom_photo_desc = (
        "Two adult men and one adult Black woman sitting closely together, "
        "enjoying cocktails in an intimate, dimly lit bar. Relaxed conversation, "
        "subtle smiles, candid expressions. All three clearly visible"
    )

    prompt = build_v2_cover_prompt(story, photograph_description=custom_photo_desc)

    expected = (
        "Create a TTL Confessions story introduction page matching the attached design. "
        "Style: Warm ivory paper background, generous whitespace, handmade editorial aesthetic. "
        "Black text with raspberry pink (#D72655) as the only accent colour. "
        "Typography: Expressive brush lettering for the title, category and author name. "
        "Clean sans-serif for body text and personal details. "
        "Layout and exact text: "
        "Top left: black TTL logo with a pink brush underline. "
        "Top right: “CONFESSIONS” in pink. "
        "Left column, large pink title: “Two Men and Nia”. "
        "Below, black body text: “They took a little GHB in Bacardi cola.” No subtitle. "
        "Bottom left: “WALES, UK”, followed by “23 YEARS / MALE / HETEROSEXUAL”, and a small pink outlined “EXPLICIT” label. "
        "Bottom: wide pink button reading “READ CONFESSION →” in white. "
        "Photograph: A large, slightly rotated Polaroid on the right. Two adult men and one adult Black woman sitting closely together, enjoying cocktails in an intimate, dimly lit bar. Relaxed conversation, subtle smiles, candid expressions. All three clearly visible. "
        "Analogue treatment: Strictly black-and-white, authentic vintage 35mm snapshot. "
        "Visible organic film grain, soft focus, faded blacks, muted contrast, gentle highlight bloom, "
        "subtle dust and fine scratches. Atmospheric, intimate and slightly mysterious. "
        "Avoid a polished digital or cheerful stock-photo look. "
        "Polaroid caption: “RORY” with “AUTHOR” underneath and a small raspberry hand-drawn heart. "
        "Keep all photography monochrome. No additional accent colours, gradients or decorative stickers. "
        "Render the complete portrait page straight-on, without a device frame."
    )
    assert prompt == expected


def test_build_v2_cover_prompt_heuristic_fallback():
    from app.utils.story_image_prompt import build_v2_cover_prompt

    story = _story(
        story_type=StoryType.confession,
        title="Alone In Berlin",
        hero_hook="I finally walked out of that apartment.",
        location="Berlin, Germany",
        city="Berlin",
        country="Germany",
        age=30,
        gender="female",
        sexual_orientation="bisexual",
        high_intensity=False,
        first_name="Elena",
        situation="Standing alone by the doorway at night.",
        story_text="A quiet night in Berlin.",
    )

    prompt = build_v2_cover_prompt(story, use_llm_scene=False)
    assert "Create a TTL Confessions story introduction page" in prompt
    assert "Top right: “CONFESSIONS” in pink." in prompt
    assert "Left column, large pink title: “Alone In Berlin”." in prompt
    assert "Below, black body text: “I finally walked out of that apartment.” No subtitle." in prompt
    assert "Bottom left: “BERLIN, GERMANY”, followed by “30 YEARS / FEMALE / BISEXUAL”." in prompt
    assert "EXPLICIT" not in prompt
    assert "Polaroid caption: “ELENA” with “AUTHOR” underneath and a small raspberry hand-drawn heart." in prompt
    assert "Photograph: A large, slightly rotated Polaroid on the right." in prompt
    assert "Analogue treatment: Strictly black-and-white, authentic vintage 35mm snapshot." in prompt


def test_build_v2_cover_prompt_meditation():
    from app.utils.story_image_prompt import build_v2_cover_prompt

    story = _meditation_story(
        title="Soft Stillness",
        hero_hook="Returning to the breath in morning light.",
        location="Kyoto, Japan",
        city="Kyoto",
        country="Japan",
        age=35,
        gender="female",
        sexual_orientation=None,
        high_intensity=False,
        first_name="Aoi",
    )

    prompt = build_v2_cover_prompt(story, use_llm_scene=False)
    assert "Create a TTL Meditations story introduction page" in prompt
    assert "Top right: “MEDITATIONS” in pink." in prompt
    assert "Left column, large pink title: “Soft Stillness”." in prompt
    assert "READ MEDITATION →" in prompt
    assert "Polaroid caption: “AOI” with “AUTHOR” underneath" in prompt


def test_v1_method_executes_template_pipeline():
    story = _story()
    db = MagicMock()
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "v1"):
        with patch.object(story_cover.settings, "OPENAI_API_KEY", "sk-test"):
            with patch(
                "app.utils.story_image_prompt.build_portrait_only_prompt",
                return_value="portrait only prompt",
            ):
                with patch(
                    "app.utils.image_generator.generate_ai_cover_image",
                    return_value=("https://cdn/portrait.jpg", "images/portrait.jpg"),
                ):
                    with patch(
                        "app.cover_template.render.render_cover_png_sync",
                        return_value=b"fake-png",
                    ) as render:
                        with patch(
                            "app.utils.s3.upload_image_to_s3",
                            return_value=("https://cdn/cover.png", "images/cover.png"),
                        ):
                            with patch("app.utils.s3.delete_s3_object"):
                                story_cover.try_generate_story_cover(
                                    db, story, image_prompt=None
                                )
                                render.assert_called_once()
                                assert story.image_source == ImageSource.template_v1


def test_v2_method_executes_v2_editorial_prompt_pipeline():
    story = _story()
    db = MagicMock()
    with patch.object(story_cover.settings, "COVER_GENERATION_METHOD", "v2"):
        with patch.object(story_cover.settings, "OPENAI_API_KEY", "sk-test"):
            with patch(
                "app.utils.story_image_prompt.build_v2_cover_prompt",
                return_value="V2 editorial prompt test",
            ) as mock_prompt:
                with patch(
                    "app.utils.image_generator.generate_ai_cover_image",
                    return_value=("https://cdn/v2_cover.jpg", "images/v2_cover.jpg"),
                ) as mock_gen:
                    with patch("app.cover_template.render.render_cover_png_sync") as render:
                        story_cover.try_generate_story_cover(
                            db, story, image_prompt=None
                        )
                        mock_prompt.assert_called_once_with(story)
                        mock_gen.assert_called_once()
                        assert mock_gen.call_args.kwargs["image_prompt"] == "V2 editorial prompt test"
                        assert mock_gen.call_args.kwargs["lock_identity"] is False
                        render.assert_not_called()
                        assert story.image_source == ImageSource.template_v2
                        assert story.cover_image_url == "https://cdn/v2_cover.jpg"
                        assert story.cover_image_key == "images/v2_cover.jpg"

