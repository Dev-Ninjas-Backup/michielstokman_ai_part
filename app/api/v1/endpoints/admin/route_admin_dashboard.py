from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.model.user import User
from app.data.user import count_total_users, count_active_users_30d, count_verified_users
from app.data.billing import (
    count_active_subscriptions,
    get_total_revenue_today,
    count_failed_payments_today,
)
from app.data.story import (
    count_stories_today,
    count_failed_stories_today,
    get_stories_by_type_today,
)

router = APIRouter()


@router.get("/admin/dashboard/stats")
def admin_dashboard_stats(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Fetch real admin dashboard statistics from database.
    Only accessible to admin users.
    """
    return {
        "admin_user_id": str(current_user.id),
        "admin_email": current_user.email,
        "stats": {
            "total_users": count_total_users(db),
            "active_users_30d": count_active_users_30d(db),
            "verified_users": count_verified_users(db),
            "active_subscriptions": count_active_subscriptions(db),
            "stories_generated_today": count_stories_today(db),
            "failed_stories_today": count_failed_stories_today(db),
            "revenue_today_cents": get_total_revenue_today(db),
            "failed_payments_today": count_failed_payments_today(db),
        },
        "breakdown": {
            "stories_by_type_today": get_stories_by_type_today(db),
        },
    }


@router.get("/admin/dashboard/demo")
def admin_dashboard_demo(current_user: User = Depends(get_current_admin_user)):
    """Legacy demo route (kept for backward compatibility)."""
    return {
        "message": "Admin dashboard demo route is working",
        "admin_user_id": str(current_user.id),
    }