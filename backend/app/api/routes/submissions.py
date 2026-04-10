from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import Submission, User
from app.schemas.dto import SubmissionCreateRequest, SubmissionResponse


router = APIRouter(prefix="/submissions", tags=["Submissions"])


@router.post("", response_model=SubmissionResponse)
def create_submission(
    payload: SubmissionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = Submission(user_id=current_user.id, **payload.model_dump())
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return SubmissionResponse.model_validate(submission, from_attributes=True)


@router.get("/me", response_model=list[SubmissionResponse])
def my_submissions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    submissions = (
        db.query(Submission)
        .filter(Submission.user_id == current_user.id)
        .order_by(Submission.created_at.desc())
        .all()
    )
    return [SubmissionResponse.model_validate(item, from_attributes=True) for item in submissions]
