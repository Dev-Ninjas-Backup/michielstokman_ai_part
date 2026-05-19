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
from app.utils.media import format_media_url
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
        has_access = check_user_has_plan_code(db, user_id, plan_code=f"journey_{journey_code}")
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=LIBERATION_PURCHASE_REQUIRED.format(journey_code=journey_code),
            )

    # ── Enroll ──────────────────────────────────────────────────────────────

    @staticmethod
    def enroll(db: Session, user_id: UUID, journey_code: str, total_days: int = 7, reminder_preference: Optional[str] = None) -> dict:
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
    def get_status(db: Session, user_id: UUID, journey_code: str) -> dict:
        """Return the full journey status with all summaries for the specified journey."""
        from app.utils.messages import LIBERATION_ENROLL_REQUIRED
        journey = lib_data.get_active_journey(db, user_id, journey_code)
        if not journey:
            journey = lib_data.get_any_journey_for_user(db, user_id, journey_code)
        if not journey:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=LIBERATION_ENROLL_REQUIRED,
            )

        LiberationService._verify_purchase(db, user_id, journey.journey_code)

        return LiberationService._build_status_dict(journey)

    @staticmethod
    def get_purchased_journeys(db: Session, user_id: UUID) -> dict:
        """
        Return a list of all journeys the user has purchased.
        Merges catalog definition data with the user's progress (if enrolled).
        """
        from app.model.billing import UserSubscription, SubscriptionPlan, SubscriptionStatus
        from app.model.liberation import UserJourney
        
        # 1. Find all purchased journey codes for this user
        subscriptions = (
            db.query(SubscriptionPlan.code)
            .join(UserSubscription, UserSubscription.plan_id == SubscriptionPlan.id)
            .filter(
                UserSubscription.user_id == user_id,
                UserSubscription.status == SubscriptionStatus.active,
                SubscriptionPlan.code.startswith("journey_")
            )
            .all()
        )
        
        purchased_codes = [sub.code.replace("journey_", "") for sub in subscriptions]
        if not purchased_codes:
            return {"journeys": [], "total": 0}

        # 2. Find enrolled journeys to get progress
        enrolled_journeys = (
            db.query(UserJourney)
            .filter(
                UserJourney.user_id == user_id,
                UserJourney.journey_code.in_(purchased_codes)
            )
            .all()
        )
        
        enrollment_map = {j.journey_code: j for j in enrolled_journeys}

        # 3. Build the response list
        results = []
        for code in purchased_codes:
            # Fetch catalog definition for title/image
            definition = catalog_data.get_definition_by_code(db, code)
            if not definition:
                continue
                
            enrolled = enrollment_map.get(code)
            
            is_enrolled = enrolled is not None
            current_day = None
            status = "purchased"
            
            if is_enrolled:
                status = enrolled.status.value
                current_day = 1
                for step in enrolled.steps:
                    if step.status in (StepStatus.available, StepStatus.completed):
                        current_day = step.day_number

            results.append({
                "journey_code": code,
                "title": definition.title,
                "description": definition.description,
                "cover_image_url": definition.cover_image_url,
                "total_days": definition.total_days,
                "is_enrolled": is_enrolled,
                "current_day": current_day,
                "status": status
            })

        return {"journeys": results, "total": len(results)}

    # ── Generate Daily Exercise ─────────────────────────────────────────────

    @staticmethod
    def generate_day(db: Session, user_id: UUID, journey_code: str, day: int, morning_feeling: str) -> dict:
        """
        1. Verify the day is 'available'.
        2. Verify purchase based on active journey.
        3. Save the morning feeling.
        4. Return admin-written content. Falls back to AI if content is missing.
        """
        journey = lib_data.get_active_journey(db, user_id, journey_code)
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

        # Check if there is pre-written content for this day
        pre_written_exercise = None
        pre_written_why = None
        if journey.definition and journey.definition.day_definitions:
            for d_def in journey.definition.day_definitions:
                if d_def.day_number == day:
                    pre_written_exercise = d_def.exercise_text
                    pre_written_why = d_def.why_text
                    break
        
        if pre_written_exercise and pre_written_why:
            from app.utils.messages import AI_FALLBACK_GREETING
            theme = step.day_theme or f"Day {day}"
            greeting = AI_FALLBACK_GREETING.format(day=day, theme=theme)
            exercise_text = pre_written_exercise
            why_text = pre_written_why
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Content for Day {day} is not configured/written yet (AI fallback is disabled)."
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
    def complete_day(db: Session, user_id: UUID, journey_code: str, day: int, energy_level: float, what_opened: str, key_takeaway: str) -> dict:
        """
        Save the user's post-exercise reflection, mark the day completed,
        and unlock the next day.
        """
        journey = lib_data.get_active_journey(db, user_id, journey_code)
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
    def get_day_detail(db: Session, user_id: UUID, journey_code: str, day: int) -> dict:
        """Return the full detail of a specific day (for playback or review)."""
        journey = lib_data.get_active_journey(db, user_id, journey_code)
        if not journey:
            journey = lib_data.get_any_journey_for_user(db, user_id, journey_code)
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
    def get_feed_card(db: Session, user_id: UUID, journey_code: str) -> dict:
        """
        Build the premium journey card for a specific journey.
        """
        from app.model.liberation import LiberationDefinition, DefinitionStatus

        journey = lib_data.get_any_journey_for_user(db, user_id, journey_code)

        if not journey:
            # Look for the definition to show as a teaser
            definition = db.query(LiberationDefinition).filter(
                LiberationDefinition.journey_code == journey_code,
                LiberationDefinition.moderation_status == DefinitionStatus.approved,
                LiberationDefinition.is_active == True,
                LiberationDefinition.is_admin_created == True
            ).first()

            if not definition:
                # No such journey exists in catalog
                return None

            return {
                "card_type": "liberation_journey",
                "journey_code": definition.journey_code,
                "title": definition.title,
                "description": definition.description or f"A {definition.total_days}-day path to transformation.",
                "cover_image_url": format_media_url(definition.cover_image_url),
                "price_display": definition.price_cents // 100,
                "price_cents": definition.price_cents,
                "total_days": definition.total_days,
                "rating": definition.rating,
                "what_to_expect": definition.what_to_expect or [],
                "setup_instructions": definition.setup_instructions or [],
                "is_enrolled": False,
                "has_access": check_user_has_plan_code(db, user_id, f"journey_{definition.journey_code}"),
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
            "cover_image_url": format_media_url(cover_image_url),
            "price_display": price_display,
            "price_cents": price_cents,
            "total_days": journey.total_days,
            "rating": journey.definition.rating if journey.definition else None,
            "what_to_expect": journey.definition.what_to_expect if journey.definition else [],
            "setup_instructions": journey.definition.setup_instructions if journey.definition else [],
            "is_enrolled": True,
            "has_access": True, # If they are enrolled, they definitely have access
            "current_day": current_day,
            "journey_status": journey.status.value,
            "journey_id": journey.id,
        }

    @staticmethod
    def get_all_feed_cards(db: Session, user_id: UUID) -> list[dict]:
        """
        Builds premium journey cards for ALL active/approved journeys in the catalog.
        Injects the user's progress if they are enrolled, and access status.
        """
        from app.model.liberation import LiberationDefinition, DefinitionStatus, UserJourney
        from app.utils.messages import LIBERATION_CONTINUE_DESC

        # 1. Get all active catalog definitions (Admin-created only)
        definitions = db.query(LiberationDefinition).filter(
            LiberationDefinition.moderation_status == DefinitionStatus.approved,
            LiberationDefinition.is_active == True,
            LiberationDefinition.is_admin_created == True
        ).order_by(LiberationDefinition.created_at.desc()).all()

        # 2. Get all of the user's enrolled journeys
        if user_id:
            enrolled_journeys = db.query(UserJourney).filter(UserJourney.user_id == user_id).all()
        else:
            enrolled_journeys = []
        enrollment_map = {j.journey_code: j for j in enrolled_journeys}

        cards = []
        for d in definitions:
            enrolled = enrollment_map.get(d.journey_code)
            
            is_enrolled = enrolled is not None
            current_day = None
            journey_status = None
            journey_id = None
            
            # Use catalog details as base
            title = d.title
            description = d.description or f"A {d.total_days}-day path to transformation."
            
            if is_enrolled:
                description = LIBERATION_CONTINUE_DESC.format(days=enrolled.total_days)
                journey_status = enrolled.status.value
                journey_id = enrolled.id
                current_day = 1
                for step in enrolled.steps:
                    if step.status in (StepStatus.available, StepStatus.completed):
                        current_day = step.day_number

            cards.append({
                "card_type": "liberation_journey",
                "journey_code": d.journey_code,
                "title": title,
                "description": description,
                "cover_image_url": format_media_url(d.cover_image_url),
                "price_display": d.price_cents // 100,
                "price_cents": d.price_cents,
                "total_days": d.total_days,
                "rating": d.rating,
                "what_to_expect": d.what_to_expect or [],
                "setup_instructions": d.setup_instructions or [],
                "is_enrolled": is_enrolled,
                "has_access": check_user_has_plan_code(db, user_id, f"journey_{d.journey_code}"),
                "current_day": current_day,
                "journey_status": journey_status,
                "journey_id": journey_id,
            })
            
        return cards

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
