from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_admin_user
from app.model.user import User

router = APIRouter()


@router.get("/admin/dashboard/demo")
def admin_dashboard_demo(current_user: User = Depends(get_current_admin_user)):

    return {
        "message": "Admin dashboard demo route is working",
        "admin_user_id": str(current_user.id),
        "stats": {
            "total_users": 0,
            "active_subscriptions": 0,
            "stories_generated_today": 0,
        },
    }