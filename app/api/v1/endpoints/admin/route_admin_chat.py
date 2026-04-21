"""
app/api/v1/endpoints/admin/route_admin_chat.py

Admin Metrics Chat — POST /v1/admin/chat

Accepts a natural-language query from the admin, fetches a real-time
metrics snapshot from the database, and returns an LLM-generated answer.
Only accessible to admin users.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.model.user import User
from app.schemas.schema_admin_chat import AdminChatRequest, AdminChatResponse
from app.services.service_admin_chat import AdminChatService

router = APIRouter()


@router.post("/admin/chat", response_model=ApiResponse[AdminChatResponse])
def admin_metrics_chat(
    payload: AdminChatRequest,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Natural-language metrics chat for admins.

    Ask about:
    - Top resonance content this week
    - Growth area averages (by life phase)
    - Journey completion rates
    - Pending moderation items
    - Platform overview (stories, feedback, ratings)

    The LLM is grounded with a real-time data snapshot — it never invents numbers.
    """
    answer, metrics_snapshot = AdminChatService.answer(query=payload.query, db=db)
    return success_response(
        "Metrics chat response generated",
        status.HTTP_200_OK,
        {
            "answer": answer,
            "metrics_snapshot": metrics_snapshot,
        },
    )
