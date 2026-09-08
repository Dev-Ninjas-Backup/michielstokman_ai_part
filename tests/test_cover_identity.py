"""Cover identity: lock, placeholders, PERSPECTIVE, and prompt reuse."""
from types import SimpleNamespace

from app.utils.image_generator import prepend_cover_identity_lock
from app.utils.prompts import (
    BASE_PERSONA,
    STORY_HUMAN_TEMPLATE,
    build_story_system_template,
    cover_identity_template_vars,
)
from app.schemas.schema_ai import StoryType
from app.utils.story_image_prompt import resolve_image_prompt, substitute_cover_placeholders


def test_identity_lock_uses_submitted_name_and_gender():
    grok = "collage cover with Elena in a pink sweater, tape saying Elena"
    locked = prepend_cover_identity_lock(
        grok, author_name="Liam", gender="Male"
    )
    assert locked.startswith("The person depicted MUST be Liam, a Male.")
    assert "Elena" in locked
    assert locked.index("Liam") < locked.index("Elena")


def test_identity_lock_empty_gender_does_not_say_woman():
    locked = prepend_cover_identity_lock(
        "a scrapbook collage", author_name="Liam", gender=None
    )
    assert "a person." in locked
    assert "woman" not in locked.lower()
    assert "female" not in locked.lower()


def test_identity_lock_does_not_double_prefix():
    once = prepend_cover_identity_lock("scene", author_name="Liam", gender="Male")
    twice = prepend_cover_identity_lock(once, author_name="Liam", gender="Male")
    assert twice.count("The person depicted MUST be") == 1


def test_placeholder_sub_uses_story_first_name_not_story_text():
    prompt = "tape saying [INSERT AUTHOR NAME HERE] next to Elena"
    out = substitute_cover_placeholders(
        prompt, title="The Harbour", author_name="Liam"
    )
    assert "Liam" in out
    assert "[INSERT AUTHOR NAME HERE]" not in out
    assert "Elena" in out


def test_perspective_unspecified_is_not_female_default():
    system = build_story_system_template(StoryType.confession, gender=None)
    assert "female narrator" not in system
    assert "Do not assume the narrator is a woman or a man" in system


def test_perspective_male_still_male():
    system = build_story_system_template(StoryType.confession, gender="Male")
    assert "male narrator" in system


def test_rule_9_carve_out_mentions_cover_tape():
    assert "cover art author-name tape" in BASE_PERSONA
    assert "real submitted name" in BASE_PERSONA


def test_story_human_template_has_bound_cover_vars():
    vars_ = cover_identity_template_vars("Liam", "Male", "Deer Isle, Maine, USA")
    filled = STORY_HUMAN_TEMPLATE.format(story_type="confession", **vars_)
    assert "{cover_author_name}" not in filled
    assert "tape text MUST read exactly: Liam" in filled
    assert "portrait MUST depict a Male person" in filled
    assert "Deer Isle, Maine, USA" in filled


def test_cover_art_direction_fills_same_vars_as_p1():
    from app.model.story import StoryType as StoryTypeEnum
    from app.utils.story_image_prompt import _cover_art_direction

    story = SimpleNamespace(
        first_name="Liam",
        gender="Male",
        location="Deer Isle, Maine, USA",
        story_type=StoryTypeEnum.confession,
    )
    direction = _cover_art_direction(story)
    assert "{cover_author_name}" not in direction
    assert "tape text MUST read exactly: Liam" in direction
    assert "portrait MUST depict a Male person" in direction

    from langchain_core.prompts import (
        ChatPromptTemplate,
        HumanMessagePromptTemplate,
        SystemMessagePromptTemplate,
    )

    chat = ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template("{user_context}"),
        HumanMessagePromptTemplate.from_template(STORY_HUMAN_TEMPLATE),
    ])
    vars_ = cover_identity_template_vars("Liam", "Male", "Deer Isle, Maine, USA")
    messages = chat.format_prompt(
        user_context="Name: Liam",
        story_type="confession",
        **vars_,
    ).to_messages()
    human = messages[1].content
    assert "{cover_author_name}" not in human
    assert "Liam" in human
    assert "Male" in human


def test_public_schemas_do_not_expose_image_prompt():
    from app.schemas.schema_member_story import MemberStoryDetail, MemberStoryListItem
    from app.schemas.schema_story import StoryDetailResponse, StoryListItemResponse

    for schema in (
        MemberStoryDetail,
        MemberStoryListItem,
        StoryDetailResponse,
        StoryListItemResponse,
    ):
        assert "image_prompt" not in schema.model_fields


def test_resolve_reuses_stored_prompt_unless_force_rebuild(monkeypatch):
    story = SimpleNamespace(
        title="The Harbour",
        member_title=None,
        first_name="Liam",
        image_prompt="stored collage with [INSERT AUTHOR NAME HERE]",
        story_text="I walked the shore at Deer Isle.",
        id="unused",
    )
    reused = resolve_image_prompt(story, None)
    assert reused is not None
    assert "Liam" in reused
    assert "[INSERT AUTHOR NAME HERE]" not in reused

    monkeypatch.setattr(
        "app.utils.story_image_prompt.build_image_prompt_from_story",
        lambda _story: "rebuilt P2 prompt with [INSERT AUTHOR NAME HERE]",
    )
    rebuilt = resolve_image_prompt(story, None, force_rebuild=True)
    assert rebuilt is not None
    assert "rebuilt P2 prompt" in rebuilt
    assert "Liam" in rebuilt
    assert "stored collage" not in rebuilt
