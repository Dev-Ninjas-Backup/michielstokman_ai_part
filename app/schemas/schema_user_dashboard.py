from pydantic import BaseModel, UUID4
from typing import Optional, List, Union
from app.schemas.schema_liberation import LiberationFeedCard

class StoryFeedItem(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    story_type: str  # "confession", "meditation", "transformation"
    cover_image_url: Optional[str] = None
    audio_path: Optional[str] = None
    rating: float = 4.3
    listened_count: int = 0
    is_explicit: bool = False

class HeroStats(BaseModel):
    total_users: str = "85,000"
    total_countries: int = 18

class DiscoveryFeedResponse(BaseModel):
    hero_stats: HeroStats
    items: List[Union[StoryFeedItem, LiberationFeedCard]]
