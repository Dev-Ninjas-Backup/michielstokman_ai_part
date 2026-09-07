"""Admin user management endpoints."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.model.user import User
from app.schemas.schema_admin_users import (
    AdminUserDeleteResponse,
    AdminUserDetail,
    AdminUserListResponse,
    AdminUserPatchRequest,
)
from app.services import service_admin_user as admin_users

router = APIRouter()


@router.get(
    "/admin/users",
    response_model=ApiResponse[AdminUserListResponse],
    summary="Admin: list users",
)
def list_users(
    q: Optional[str] = Query(None, description="Search email or display name"),
    is_active: Optional[bool] = Query(None),
    is_admin: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    data = admin_users.list_users(
        db,
        q=q,
        is_active=is_active,
        is_admin=is_admin,
        page=page,
        limit=limit,
    )
    return success_response("Users fetched", status.HTTP_200_OK, data)


@router.get(
    "/admin/users/{user_id}",
    response_model=ApiResponse[AdminUserDetail],
    summary="Admin: user detail",
)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    data = admin_users.get_user_detail(db, user_id)
    return success_response("User fetched", status.HTTP_200_OK, data)


@router.patch(
    "/admin/users/{user_id}",
    response_model=ApiResponse[AdminUserDetail],
    summary="Admin: ban/unban or promote/demote a user",
)
def patch_user(
    user_id: UUID,
    body: AdminUserPatchRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    data = admin_users.patch_user(
        db,
        actor=admin,
        user_id=user_id,
        is_active=body.is_active,
        is_admin=body.is_admin,
    )
    return success_response("User updated", status.HTTP_200_OK, data)


@router.delete(
    "/admin/users/{user_id}",
    response_model=ApiResponse[AdminUserDeleteResponse],
    summary="Admin: hard-delete a user and wipe owned stories",
)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    deleted_id, stories_deleted = admin_users.delete_user(
        db, actor=admin, user_id=user_id
    )
    data = AdminUserDeleteResponse(
        user_id=deleted_id,
        stories_deleted=stories_deleted,
        message="User deleted",
    )
    return success_response("User deleted", status.HTTP_200_OK, data)
