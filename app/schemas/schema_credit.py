from datetime import datetime
from pydantic import BaseModel


class CreditStatusResponse(BaseModel):
    is_premium: bool
    daily_credits_remaining: int
    max_daily_credits: int
    next_reset_at: datetime | None = None
    message: str
