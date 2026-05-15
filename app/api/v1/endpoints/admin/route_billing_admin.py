from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.data import billing as billing_data
from app.schemas.schema_billing import AdminOrderHistoryResponse, AdminOrderListItem

router = APIRouter()

@router.get(
    "/admin/orders",
    response_model=ApiResponse[AdminOrderHistoryResponse],
    summary="Admin: get complete order history and revenue stats",
)
def admin_get_order_history(
    search: str | None = Query(None, description="Search by journey/plan name"),
    days_back: int | None = Query(None, description="Filter by last N days"),
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    admin_user = Depends(get_current_admin_user),
):
    """
    Returns total revenue, total order count, and a paginated list of successful orders.
    Aligned with the Figma 'Order History' dashboard.
    """
    # 1. Get summary stats
    total_revenue, total_orders = billing_data.get_admin_order_stats(db)
    
    # 2. Get filtered list
    results, total_filtered = billing_data.list_admin_orders(
        db, 
        search=search, 
        days_back=days_back, 
        limit=limit, 
        offset=offset
    )
    
    # 3. Map to response
    orders = [
        AdminOrderListItem(
            id=r.id,
            plan_name=r.plan_name,
            amount_cents=r.amount_cents,
            amount=r.amount_cents / 100.0,
            currency=r.currency,
            user_email=r.user_email,
            paid_at=r.paid_at
        )
        for r in results
    ]
    
    data = AdminOrderHistoryResponse(
        total_revenue_cents=total_revenue,
        total_revenue=total_revenue / 100.0,
        total_orders=total_orders,
        orders=orders,
        total_filtered=total_filtered
    )
    
    return success_response("Order history fetched successfully", 200, data)
