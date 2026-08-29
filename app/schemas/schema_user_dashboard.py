from pydantic import BaseModel, UUID4
from typing import Optional, List, Union
from app.schemas.schema_liberation import LiberationFeedCard

class StoryFeedItem(BaseModel):
    card_type: str = "story"
    id: str
    title: str
    excerpt: Optional[str] = None
    description: Optional[str] = None  # Legacy alias for `excerpt`
    story_type: str  # "confession", "meditation", "transformation"
    cover_image_url: Optional[str] = None
    audio_path: Optional[str] = None
    rating: Optional[float] = None
    listened_count: int = 0
    author_name: Optional[str] = None
    location: Optional[str] = None
    gender: Optional[str] = None
    sexual_orientation: Optional[str] = None
    occupation: Optional[str] = None
    age: Optional[int] = None
    audio_duration_seconds: Optional[int] = None
    is_explicit: bool = False

class HeroStats(BaseModel):
    total_users: int
    total_countries: int
    total_stories_generated: int

class DiscoveryFeedResponse(BaseModel):
    hero_stats: HeroStats
    items: List[Union[StoryFeedItem, LiberationFeedCard]]
