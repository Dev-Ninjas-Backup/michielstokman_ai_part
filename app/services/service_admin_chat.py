"""
app/services/service_admin_chat.py

Business logic for the Admin Metrics Chat feature.

Fetches a real-time metrics snapshot from the DB (via app/data/admin_chat.py),
builds a structured context block, and sends it together with the admin's
query to the LLM. All prompt templates live in app/utils/prompts.py.
"""
import json
import logging
from sqlalchemy.orm import Session

from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)

from app.core.llm import get_story_llm
import app.data.admin_chat as admin_chat_data
from app.utils.prompts import ADMIN_CHAT_SYSTEM, ADMIN_CHAT_HUMAN

logger = logging.getLogger(__name__)


class AdminChatService:

    @staticmethod
    def build_metrics_snapshot(db: Session) -> dict:
        """
        Aggregates all relevant platform data into a single structured snapshot.
        This dict is serialised to JSON and injected into the LLM prompt as
        grounding context so the model never has to guess or hallucinate numbers.
        """
        return {
            "top_resonance_content_this_week": admin_chat_data.get_top_resonance_stories(db),
            "growth_area_averages": admin_chat_data.get_growth_area_averages(db),
            "journey_completion_rates": admin_chat_data.get_journey_completion_rates(db),
            "pending_moderation_count": admin_chat_data.get_pending_moderation_count(db),
            "platform_overview": admin_chat_data.get_platform_overview(db),
        }

    @staticmethod
    def get_deterministic_answer(query: str, db: Session) -> tuple[str | None, dict]:
        """
        Detects standard queries and returns a deterministic, instant response.
        Returns (answer_string, metrics_snapshot) if matched, else (None, snapshot).
        """
        import re
        norm = re.sub(r'[^\w\s]', '', query.lower().strip())
        
        # 1. Top Resonance Content
        if norm in ("top resonance content this week", "top resonance content", "top resonance"):
            from app.data.admin_chat import get_top_resonance_stories
            snapshot = {"top_resonance_content_this_week": get_top_resonance_stories(db)}
            if not snapshot["top_resonance_content_this_week"]:
                return "No stories have received feedback yet this week.", snapshot
            
            lines = ["Here is the top resonance content this week:"]
            for i, item in enumerate(snapshot["top_resonance_content_this_week"], 1):
                lines.append(f"{i}. \"{item['title']}\" — {item['avg_pulse']} pulse ({item['reflection_count']} reflections)")
            return "\n".join(lines), snapshot
            
        # 2. Growth Area Averages
        if norm in ("growth area averages by life phase", "growth area averages", "growth areas", "life phases"):
            from app.data.admin_chat import get_growth_area_averages
            snapshot = {"growth_area_averages": get_growth_area_averages(db)}
            if not snapshot["growth_area_averages"]:
                return "Not enough feedback samples yet (minimum 3 per phase required) to calculate growth area averages.", snapshot
            
            lines = ["Here are the average pulse scores grouped by growth area (life phase):"]
            for item in snapshot["growth_area_averages"]:
                lines.append(f"- {item['growth_area']}: {item['avg_score']} average based on {item['sample_count']} samples")
            return "\n".join(lines), snapshot
            
        # 3. Journey Completion Rates
        if norm in ("journey completion rates", "journey completion", "completion rates"):
            from app.data.admin_chat import get_journey_completion_rates
            snapshot = {"journey_completion_rates": get_journey_completion_rates(db)}
            stats = snapshot["journey_completion_rates"]
            
            by_status = stats.get("journeys_by_status", {})
            status_lines = [f"  * {status.capitalize()}: {count}" for status, count in by_status.items()]
            status_str = "\n".join(status_lines) if status_lines else "  * No active enrollments."
            
            answer = (
                "Here are the current journey completion statistics:\n\n"
                f"**Journey Status Counts:**\n{status_str}\n\n"
                f"**Step Completion Metrics:**\n"
                f"- Total Steps Opened: {stats.get('total_steps', 0)}\n"
                f"- Completed Steps: {stats.get('completed_steps', 0)}\n"
                f"- Step Completion Rate: {stats.get('step_completion_rate_pct', 0.0)}%"
            )
            return answer, snapshot
            
        # 4. Pending Moderation Items
        if norm in ("pending moderation items", "pending moderation", "moderation items", "moderation queue"):
            from app.data.admin_chat import get_pending_moderation_count
            count = get_pending_moderation_count(db)
            snapshot = {"pending_moderation_count": count}
            if count == 0:
                return "There are currently 0 completed stories awaiting moderation review.", snapshot
            return f"There are currently {count} completed stories awaiting moderation review.", snapshot
            
        # 5. Platform Overview
        if norm in ("platform overview stories feedback ratings", "platform overview", "overview"):
            from app.data.admin_chat import get_platform_overview
            snapshot = {"platform_overview": get_platform_overview(db)}
            overview = snapshot["platform_overview"]
            
            avg_touch = overview.get("avg_touch_score")
            avg_star = overview.get("avg_star_rating")
            
            answer = (
                "Here is a high-level overview of the platform's performance metrics:\n"
                f"- **Total Completed Stories**: {overview.get('total_completed_stories', 0)}\n"
                f"- **Total Feedback Reflections**: {overview.get('total_feedback_entries', 0)}\n"
                f"- **Average Pulse Score**: {f'{avg_touch}/10' if avg_touch else 'N/A'}\n"
                f"- **Average Rating**: {f'{avg_star} stars' if avg_star else 'N/A'}"
            )
            return answer, snapshot
            
        return None, {}

    @staticmethod
    def answer(query: str, db: Session) -> tuple[str, dict]:
        """
        Attempts deterministic answering for standard metrics.
        If no exact match is found, falls back to the LLM.
        """
        # 1. Try deterministic match
        det_answer, det_snapshot = AdminChatService.get_deterministic_answer(query, db)
        if det_answer is not None:
            logger.info(f"[AdminChat] Instant deterministic match for query: '{query[:80]}'")
            return det_answer, det_snapshot

        # 2. Fallback to LLM for custom questions
        metrics_snapshot = AdminChatService.build_metrics_snapshot(db)
        metrics_context_str = json.dumps(metrics_snapshot, indent=2, default=str)

        # Lower temperature for factual, data-grounded responses
        llm = get_story_llm(temperature=0.3)

        chat_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(ADMIN_CHAT_SYSTEM),
            HumanMessagePromptTemplate.from_template(ADMIN_CHAT_HUMAN),
        ])

        formatted_messages = chat_prompt.format_prompt(
            metrics_context=metrics_context_str,
            query=query,
        ).to_messages()

        response = llm.invoke(formatted_messages)
        answer = response.content.strip()

        logger.info(f"[AdminChat] Custom query answered by LLM: '{query[:80]}'")
        return answer, metrics_snapshot
