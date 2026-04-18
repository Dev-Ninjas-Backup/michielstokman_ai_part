from pydantic import BaseModel, UUID4
from typing import Optional, List, Union
from app.schemas.schema_liberation import LiberationFeedCard

class StoryFeedItem(BaseModel):
    id: str
    title: str
    story_type: str  # "confession", "meditation", "transformation"
    audio_path: Optional[str] = None
    rating: float = 4.3  # Mock or real if available
    listened_count: int = 53057  # Mock or real if available
    is_explicit: bool = False

class DiscoveryFeedResponse(BaseModel):
    # This list will contain a mix of Story items and the special Liberation card
    items: List[Union[StoryFeedItem, LiberationFeedCard]]
