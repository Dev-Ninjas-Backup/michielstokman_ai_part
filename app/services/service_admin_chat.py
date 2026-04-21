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
    def answer(query: str, db: Session) -> tuple[str, dict]:
        """
        Fetches the metrics snapshot, builds the LLM prompt, invokes the model,
        and returns the answer string alongside the raw snapshot for transparency.
        """
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

        logger.info(f"[AdminChat] Query answered: '{query[:80]}'")
        return answer, metrics_snapshot
