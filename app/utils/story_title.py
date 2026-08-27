"""
Helpers for member-submitted vs AI-generated story titles.

`title` is the active display title (feeds, cards, share package).
`member_title` is what the member typed; `ai_generated_title` comes from the LLM.
`use_ai_title` selects which source drives `title` when both exist.
"""
from typing import Optional

from app.model.story import Story


def sync_active_title(story: Story) -> None:
    """Recompute `story.title` from member/AI sources and `use_ai_title`."""
    member = _clean(story.member_title)
    ai = _clean(story.ai_generated_title)

    if story.use_ai_title and ai:
        story.title = ai
    elif member:
        story.title = member
    elif ai:
        story.title = ai


def _clean(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    stripped = value.strip()
    return stripped or None
