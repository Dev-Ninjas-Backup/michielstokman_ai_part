"""
app/services/service_liberation.py

Business logic for the Liberation Journey (premium flow).
Handles purchase gating, day generation via SuperGrok, and progression.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.data import liberation as lib_data
from app.data import liberation_catalog as catalog_data
from app.data.billing import check_user_has_plan_code
from app.model.liberation import (
    JourneyStatus,
    StepStatus,
    JOURNEY_DAY_THEMES,
)
from app.utils.prompts import (
    build_liberation_exercise_system,
    LIBERATION_EXERCISE_HUMAN,
)

logger = logging.getLogger(__name__)


class LiberationService:

    # ── Purchase Gate ───────────────────────────────────────────────────────

    @staticmethod
    def _verify_purchase(db: Session, user_id: UUID, journey_code: str) -> None:
        """Raises 403 if user does not own the specific journey code."""
        from app.utils.messages import LIBERATION_PURCHASE_REQUIRED
        has_access = check_user_has_plan_code(db, user_id, plan_code=journey_code)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=LIBERATION_PURCHASE_REQUIRED.format(journey_code=journey_code),
            )

    # ── Enroll ──────────────────────────────────────────────────────────────

    @staticmethod
    def enroll(db: Session, user_id: UUID, journey_code: str, total_days: int, reminder_preference: Optional[str] = None) -> dict:
        """
        Create a new journey for the user after payment verification.
        Pulls day themes from the catalog definition when available.
        If they already have an active journey for that code, returns its current status.
        """
        LiberationService._verify_purchase(db, user_id, journey_code)

        existing = lib_data.get_active_journey(db, user_id, journey_code)
        if existing:
            return LiberationService._build_status_dict(existing)

        # Look up the catalog definition for day themes
        definition = catalog_data.get_definition_by_code(db, journey_code)
        definition_id = definition.id if definition else None

        # Build day themes from catalog or fallback to legacy dict
        day_themes = {}
        if definition and definition.day_definitions:
            for dd in definition.day_definitions:
                day_themes[dd.day_number] = dd.day_theme
        else:
            day_themes = JOURNEY_DAY_THEMES

        journey = lib_data.create_journey(
            db, user_id, journey_code, total_days, reminder_preference,
            definition_id=definition_id,
            day_themes=day_themes,
        )
        logger.info(f"[Liberation] User {user_id} enrolled in journey {journey.id}")
        return LiberationService._build_status_dict(journey)

    # ── Journey Status ──────────────────────────────────────────────────────

    @staticmethod
    def get_status(db: Session, user_id: UUID) -> dict:
        """Return the full journey status with all summaries for the most recent journey."""
        from app.utils.messages import LIBERATION_ENROLL_REQUIRED
        journey = lib_data.get_active_journey(db, user_id)
        if not journey:
            journey = lib_data.get_any_journey_for_user(db, user_id)
        if not journey:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=LIBERATION_ENROLL_REQUIRED,
            )

        LiberationService._verify_purchase(db, user_id, journey.journey_code)

        return LiberationService._build_status_dict(journey)

    # ── Generate Daily Exercise ─────────────────────────────────────────────

    @staticmethod
    def generate_day(db: Session, user_id: UUID, day: int, morning_feeling: str) -> dict:
        """
        1. Verify the day is 'available'.
        2. Verify purchase based on active journey.
        3. Save the morning feeling.
        4. Call SuperGrok with the Liberation prompt.
        5. Save AI content to the step row.
        """
        journey = lib_data.get_active_journey(db, user_id)
        if not journey:
            raise HTTPException(status_code=404, detail="No active journey found.")

        LiberationService._verify_purchase(db, user_id, journey.journey_code)

        step = lib_data.get_step(db, journey.id, day)
        if not step:
            raise HTTPException(status_code=404, detail=f"Day {day} does not exist.")

        if step.status == StepStatus.locked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Day {day} is still locked. Complete the previous day first.",
            )

        if step.status == StepStatus.completed:
            return {
                "day_number": step.day_number,
                "day_theme": step.day_theme,
                "ai_greeting": step.ai_greeting,
                "ai_exercise_text": step.ai_exercise_text,
                "ai_why_text": step.ai_why_text,
            }

        # Save morning feeling
        lib_data.save_morning_feeling(db, step, morning_feeling)

        # Resolve journey title from catalog or fallback
        journey_title = journey.journey_code.replace("_", " ").title()
        if journey.definition:
            journey_title = journey.definition.title

        # Generate AI content
        greeting, exercise_text, why_text = LiberationService._generate_exercise_content(
            journey_title=journey_title,
            total_days=journey.total_days,
            day_number=day,
            day_theme=step.day_theme or JOURNEY_DAY_THEMES.get(day, f"Day {day}"),
            morning_feeling=morning_feeling,
        )

        # Save everything to the step
        lib_data.save_ai_content(db, step, greeting, exercise_text, why_text)

        logger.info(f"[Liberation] User {user_id} generated Day {day} exercise.")

        return {
            "day_number": step.day_number,
            "day_theme": step.day_theme,
            "ai_greeting": greeting,
            "ai_exercise_text": exercise_text,
            "ai_why_text": why_text,
        }

    # ── Complete Day ────────────────────────────────────────────────────────

    @staticmethod
    def complete_day(db: Session, user_id: UUID, day: int, energy_level: int, what_opened: str, key_takeaway: str) -> dict:
        """
        Save the user's post-exercise reflection, mark the day completed,
        and unlock the next day.
        """
        journey = lib_data.get_active_journey(db, user_id)
        if not journey:
            raise HTTPException(status_code=404, detail="No active journey found.")

        LiberationService._verify_purchase(db, user_id, journey.journey_code)

        step = lib_data.get_step(db, journey.id, day)
        if not step:
            raise HTTPException(status_code=404, detail=f"Day {day} does not exist.")

        if step.status == StepStatus.completed:
            return {
                "day_number": day,
                "status": "completed",
                "message": f"Day {day} was already completed.",
                "next_day_available": day < journey.total_days,
            }

        if step.status == StepStatus.locked:
            raise HTTPException(status_code=403, detail=f"Day {day} is locked.")

        # Save reflection and mark completed
        lib_data.complete_step(db, step, energy_level, what_opened, key_takeaway)

        # Unlock the next day
        next_day_available = False
        if day < journey.total_days:
            lib_data.unlock_next_step(db, journey.id, day)
            next_day_available = True
        else:
            # Final day — mark the entire journey as completed
            lib_data.mark_journey_completed(db, journey)
            logger.info(f"[Liberation] User {user_id} completed the full journey!")

        from app.utils.messages import LIBERATION_DAY_COMPLETE, LIBERATION_JOURNEY_COMPLETE
        return {
            "day_number": day,
            "status": "completed",
            "message": LIBERATION_DAY_COMPLETE.format(day=day) if day < journey.total_days else LIBERATION_JOURNEY_COMPLETE,
            "next_day_available": next_day_available,
        }

    # ── Get Step Detail (for revisiting a completed day) ────────────────────

    @staticmethod
    def get_day_detail(db: Session, user_id: UUID, day: int) -> dict:
        """Return the full detail of a specific day (for playback or review)."""
        journey = lib_data.get_active_journey(db, user_id)
        if not journey:
            journey = lib_data.get_any_journey_for_user(db, user_id)
        if not journey:
            raise HTTPException(status_code=404, detail="No journey found.")

        LiberationService._verify_purchase(db, user_id, journey.journey_code)

        step = lib_data.get_step(db, journey.id, day)
        if not step:
            raise HTTPException(status_code=404, detail=f"Day {day} does not exist.")

        return {
            "day_number": step.day_number,
            "day_theme": step.day_theme,
            "status": step.status.value,
            "morning_feeling": step.morning_feeling,
            "ai_greeting": step.ai_greeting,
            "ai_exercise_text": step.ai_exercise_text,
            "ai_why_text": step.ai_why_text,
            "energy_level_after": step.energy_level_after,
            "reflection_opened": step.reflection_opened,
            "reflection_takeaway": step.reflection_takeaway,
            "completed_at": step.completed_at.isoformat() if step.completed_at else None,
        }

    # ── Discovery feed helper ───────────────────────────────────────────────

    @staticmethod
    def get_feed_card(db: Session, user_id: UUID) -> dict:
        """
        Build the premium journey card for the discovery grid.
        - Not enrolled → teaser with price from catalog
        - Enrolled → progress card with current day
        """
        from app.model.liberation import LiberationDefinition, DefinitionStatus

        journey = lib_data.get_any_journey_for_user(db, user_id)

        if not journey:
            # Look for the most recent approved catalog definition to show as a teaser
            definition = db.query(LiberationDefinition).filter(
                LiberationDefinition.moderation_status == DefinitionStatus.approved,
                LiberationDefinition.is_active == True
            ).order_by(LiberationDefinition.created_at.desc()).first()

            if not definition:
                # No approved journey in catalog to show as teaser
                return None

            return {
                "card_type": "liberation_journey",
                "journey_code": definition.journey_code,
                "title": definition.title,
                "description": definition.description or f"A {definition.total_days}-day path to transformation.",
                "cover_image_url": definition.cover_image_url,
                "price_display": definition.price_cents // 100,
                "price_cents": definition.price_cents,
                "total_days": definition.total_days,
                "rating": definition.rating,
                "what_to_expect": definition.what_to_expect or [],
                "setup_instructions": definition.setup_instructions or [],
                "is_enrolled": False,
                "current_day": None,
                "journey_status": None,
                "journey_id": None,
            }

        from app.utils.messages import LIBERATION_CONTINUE_DESC
        # Resolve title from catalog
        title = journey.journey_code.replace("_", " ").title()
        description = LIBERATION_CONTINUE_DESC.format(days=journey.total_days)
        cover_image_url = None
        price_display = 0
        price_cents = 0

        if journey.definition:
            title = journey.definition.title
            description = journey.definition.description or description
            cover_image_url = journey.definition.cover_image_url
            price_display = journey.definition.price_cents // 100
            price_cents = journey.definition.price_cents

        # Calculate current day (highest available or completed)
        current_day = 1
        for step in journey.steps:
            if step.status in (StepStatus.available, StepStatus.completed):
                current_day = step.day_number

        return {
            "card_type": "liberation_journey",
            "journey_code": journey.journey_code,
            "title": title,
            "description": description,
            "cover_image_url": cover_image_url,
            "price_display": price_display,
            "price_cents": price_cents,
            "total_days": journey.total_days,
            "rating": journey.definition.rating if journey.definition else None,
            "what_to_expect": journey.definition.what_to_expect if journey.definition else [],
            "setup_instructions": journey.definition.setup_instructions if journey.definition else [],
            "is_enrolled": True,
            "current_day": current_day,
            "journey_status": journey.status.value,
            "journey_id": journey.id,
        }

    # ── Private helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _build_status_dict(journey) -> dict:
        """Convert a journey ORM object into the status response dict."""
        current_day = 1
        steps = []
        for step in journey.steps:
            if step.status in (StepStatus.available, StepStatus.completed):
                current_day = step.day_number
            steps.append({
                "day_number": step.day_number,
                "day_theme": step.day_theme,
                "status": step.status.value,
                "completed_at": step.completed_at,
            })

        return {
            "journey_id": journey.id,
            "journey_code": journey.journey_code,
            "status": journey.status.value,
            "total_days": journey.total_days,
            "current_day": current_day,
            "steps": steps,
        }

    @staticmethod
    def _generate_exercise_content(
        journey_title: str,
        total_days: int,
        day_number: int,
        day_theme: str,
        morning_feeling: str,
    ) -> tuple[str, str, str]:
        """
        Call SuperGrok to generate the daily liberation exercise.
        Returns (greeting, exercise_text, why_text).
        """
        from app.core.llm import get_story_llm
        from langchain_core.prompts import (
            ChatPromptTemplate,
            SystemMessagePromptTemplate,
            HumanMessagePromptTemplate,
        )

        llm = get_story_llm(temperature=0.7)

        system_prompt = build_liberation_exercise_system(
            journey_title=journey_title,
            total_days=total_days,
            day_number=day_number,
            day_theme=day_theme,
            morning_feeling=morning_feeling,
        )

        chat_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(system_prompt),
            HumanMessagePromptTemplate.from_template(LIBERATION_EXERCISE_HUMAN),
        ])

        formatted = chat_prompt.format_prompt().to_messages()
        response = llm.invoke(formatted)
        content = response.content.strip()

        # Parse the three sections
        greeting = ""
        exercise_text = ""
        why_text = ""

        if "GREETING:" in content and "EXERCISE:" in content and "WHY:" in content:
            parts = content.split("EXERCISE:")
            greeting = parts[0].replace("GREETING:", "").strip()
            rest = parts[1]
            parts2 = rest.split("WHY:")
            exercise_text = parts2[0].strip()
            why_text = parts2[1].strip()
        else:
            # Fallback: treat everything as the exercise text
            from app.utils.messages import AI_FALLBACK_GREETING, AI_FALLBACK_WHY
            logger.warning(f"[Liberation] AI response did not follow expected format for Day {day_number}")
            greeting = AI_FALLBACK_GREETING.format(day=day_number, theme=day_theme)
            exercise_text = content
            why_text = AI_FALLBACK_WHY.format(theme=day_theme)

        return greeting, exercise_text, why_text
