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
