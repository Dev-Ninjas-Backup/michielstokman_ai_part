from pydantic import BaseModel, EmailStr


class HelloResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    message: str
    version: str


class MessageResponse(BaseModel):
    message: str


class AdminDashboardStatsData(BaseModel):
    total_users: int
    active_users_30d: int
    verified_users: int
    active_subscriptions: int
    stories_generated_today: int
    failed_stories_today: int
    revenue_today_cents: int
    failed_payments_today: int


class AdminDashboardBreakdown(BaseModel):
    stories_by_type_today: dict[str, int]


class AdminDashboardStatsResponse(BaseModel):
    admin_user_id: str
    admin_email: EmailStr
    stats: AdminDashboardStatsData
    breakdown: AdminDashboardBreakdown


class AdminDashboardDemoResponse(BaseModel):
    message: str
    admin_user_id: str


# ── Figma UI Admin Dashboard Schemas ──

class StatDelta(BaseModel):
    value: str
    percentage: str
    trend: str  # "up", "down", "neutral"


class TopStats(BaseModel):
    views: StatDelta
    resonance: StatDelta
    completion: StatDelta
    shares: StatDelta


class WeeklyTrend(BaseModel):
    label: str
    views: int
    pulse: float
    shares: int


class TopResonanceContent(BaseModel):
    id: str
    title: str
    pulse: float
    reflections: int


class LatestActivity(BaseModel):
    user_email: str
    action: str
    time_ago: str


class AdminFigmaDashboardResponse(BaseModel):
    top_stats: TopStats
    weekly_trends: list[WeeklyTrend]
    top_resonance_content: list[TopResonanceContent]
    latest_activity: list[LatestActivity]
