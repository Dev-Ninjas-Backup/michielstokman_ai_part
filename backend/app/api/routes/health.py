from fastapi import APIRouter

from app.schemas.dto import MessageResponse


router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=MessageResponse)
def health_check():
    return MessageResponse(message="ok")
