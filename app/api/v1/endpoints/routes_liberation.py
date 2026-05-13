"""
app/api/v1/endpoints/routes_liberation.py

Dedicated REST endpoints for the 7-Day Premium Liberation Journey.
Every endpoint is gated behind JWT auth + premium subscription check.
The story type is hardcoded to 'Transformation' — the frontend never chooses.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.api.deps import get_current_user
from app.model.user import User
from app.schemas.schema_liberation import (
    DayCheckinRequest,
    DayCompleteRequest,
    DayCompleteResponse,
    DayGenerateResponse,
    JourneyStatusResponse,
    StepDetail,
    LiberationFeedCard,
    EnrollJourneyRequest,
)
from app.services.service_liberation import LiberationService

router = APIRouter()


# ── Enroll in the journey (called after Stripe payment succeeds) ────────────

@router.post(
    "/liberation/enroll",
    response_model=ApiResponse[JourneyStatusResponse],
    summary="Start a new Liberation Journey after payment",
)
def enroll_journey(
    payload: EnrollJourneyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates a new N-day journey for the authenticated user.
    Requires an active premium subscription (verified inside the service).
    If the user already has an active journey for that code, returns its current status.
    """
    result = LiberationService.enroll(
        db=db,
        user_id=current_user.id,
        journey_code=payload.journey_code,
        total_days=payload.total_days,
        reminder_preference=payload.reminder_preference,
    )
    return success_response("Journey enrolled successfully", status.HTTP_200_OK, result)


# ── Journey status dashboard (Screen 9: the 7-day progress list) ───────────

@router.get(
    "/liberation/status",
    response_model=ApiResponse[JourneyStatusResponse],
    summary="Get current journey progress with all 7 day statuses",
)
def get_journey_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the full journey status including each day's lock/available/completed state.
    Used to render the progress dashboard (Screen 9 in the Figma).
    """
    result = LiberationService.get_status(db, current_user.id)
    return success_response("Journey status fetched", status.HTTP_200_OK, result)


# ── Generate daily exercise (Screen 4 → 5: check-in → AI exercise) ────────

@router.post(
    "/liberation/day/{day}/generate",
    response_model=ApiResponse[DayGenerateResponse],
    summary="Submit morning feeling and receive AI-generated daily exercise",
)
def generate_day(
    day: int,
    payload: DayCheckinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    1. Saves the user's morning feeling for the specified day.
    2. Calls SuperGrok with the 'Transformation' persona to generate
       a personalised greeting, exercise steps, and explanation.
    3. Returns the full exercise content.

    If the day was already generated, returns the cached version.
    """
    result = LiberationService.generate_day(
        db=db,
        user_id=current_user.id,
        day=day,
        morning_feeling=payload.morning_feeling,
    )
    return success_response("Daily exercise generated", status.HTTP_200_OK, result)


# ── Complete a day (Screen 7: post-exercise reflection) ─────────────────────

@router.post(
    "/liberation/day/{day}/complete",
    response_model=ApiResponse[DayCompleteResponse],
    summary="Submit post-exercise reflection and unlock the next day",
)
def complete_day(
    day: int,
    payload: DayCompleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Saves the energy slider and two reflection text fields.
    Marks the current day as 'completed' and unlocks the next day.
    On Day 7, marks the entire journey as 'completed'.
    """
    result = LiberationService.complete_day(
        db=db,
        user_id=current_user.id,
        day=day,
        energy_level=payload.energy_level,
        what_opened=payload.what_opened,
        key_takeaway=payload.key_takeaway,
    )
    return success_response("Day completed successfully", status.HTTP_200_OK, result)


# ── Get a specific day's detail (for playback / review) ────────────────────

@router.get(
    "/liberation/day/{day}",
    response_model=ApiResponse[StepDetail],
    summary="Get full detail of a specific day (for review or playback)",
)
def get_day_detail(
    day: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the complete data for a specific day — morning feeling,
    AI content, and post-exercise reflections.
    Useful for revisiting completed days.
    """
    result = LiberationService.get_day_detail(db, current_user.id, day)
    return success_response("Day detail fetched", status.HTTP_200_OK, result)


# ── Discovery feed card ────────────────────────────────────────────────────

@router.get(
    "/liberation/feed-card",
    response_model=ApiResponse[LiberationFeedCard],
    summary="Get the liberation journey card for the discovery grid",
)
def get_feed_card(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the premium journey card to inject into the story discovery grid.
    - If user is NOT enrolled: shows price + 'Begin Your Liberation' CTA.
    - If user IS enrolled: shows current progress + 'Continue' CTA.
    """
    result = LiberationService.get_feed_card(db, current_user.id)
    return success_response("Liberation feed card fetched", status.HTTP_200_OK, result)
