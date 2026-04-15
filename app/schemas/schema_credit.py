"""
app/schemas/schema_credit.py
Pydantic models for the credit system endpoints.
"""
from pydantic import BaseModel


class CreditStatusResponse(BaseModel):
    is_premium: bool
    daily_credits_remaining: int
    max_daily_credits: int
    message: str
