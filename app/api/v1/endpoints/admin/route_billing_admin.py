from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.data import billing as billing_data
from app.schemas.schema_billing import AdminOrderHistoryResponse, AdminOrderListItem, AdminBillingStatsResponse

router = APIRouter()

@router.get(
    "/admin/orders/stats",
    response_model=ApiResponse[AdminBillingStatsResponse],
    summary="Admin: get complete order summary and revenue aggregates",
)
def admin_get_billing_stats(
    db: Session = Depends(get_db),
    admin_user = Depends(get_current_admin_user),
):
    """
    Returns total revenue cents, total revenue in standard currency, and total order count.
    """
    total_revenue, total_orders = billing_data.get_admin_order_stats(db)
    
    data = AdminBillingStatsResponse(
        total_revenue_cents=total_revenue,
        total_revenue=total_revenue / 100.0,
        total_orders=total_orders
    )
    return success_response("Billing statistics fetched successfully", 200, data)


import math
from app.schemas.schema_system import PaginationMeta

@router.get(
    "/admin/orders",
    response_model=ApiResponse[AdminOrderHistoryResponse],
    summary="Admin: get complete order history list",
)
def admin_get_order_history(
    search: str | None = Query(None, description="Search by journey/plan name"),
    days_back: int | None = Query(None, description="Filter by last N days"),
    limit: int = 50,
    offset: int = 0,
    page: int | None = Query(None, description="1-indexed page number"),
    db: Session = Depends(get_db),
    admin_user = Depends(get_current_admin_user),
):
    """
    Returns a paginated list of successful orders aligned with the Figma 'Order History' dashboard.
    """
    if page is not None and page > 0:
        offset = (page - 1) * limit
    else:
        page = (offset // limit) + 1 if limit > 0 else 1

    # Get filtered list
    results, total_filtered = billing_data.list_admin_orders(
        db, 
        search=search, 
        days_back=days_back, 
        limit=limit, 
        offset=offset
    )
    
    # Map to response
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
    
    total_pages = math.ceil(total_filtered / limit) if limit > 0 else 1
    if total_pages == 0:
        total_pages = 1

    pagination_meta = PaginationMeta(
        total=total_filtered,
        page=page,
        limit=limit,
        totalPages=total_pages
    )

    data = AdminOrderHistoryResponse(
        orders=orders,
        total_filtered=total_filtered,
        meta=pagination_meta
    )
    
    return success_response("Order history fetched successfully", 200, data)

