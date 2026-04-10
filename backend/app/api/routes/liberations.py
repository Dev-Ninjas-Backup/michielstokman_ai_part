from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import (
    DayStatus,
    LiberationDayProgress,
    LiberationEnrollment,
    LiberationPlan,
    User,
)
from app.schemas.dto import (
    CompleteDayRequest,
    CompletionSummaryResponse,
    DayProgressResponse,
    LiberationEnrollmentResponse,
    LiberationPlanResponse,
    StartCheckoutRequest,
    StartCheckoutResponse,
    WebhookRequest,
)
from app.services.liberation_service import complete_day, create_day_progress_rows


router = APIRouter(prefix="/liberations", tags=["Liberations"])


def _get_user_enrollment(db: Session, user_id: str, enrollment_id: str) -> LiberationEnrollment:
    enrollment = (
        db.query(LiberationEnrollment)
        .filter(LiberationEnrollment.id == enrollment_id, LiberationEnrollment.user_id == user_id)
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return enrollment


@router.get("/plans", response_model=list[LiberationPlanResponse])
def plans(db: Session = Depends(get_db)):
    plans_data = db.query(LiberationPlan).filter(LiberationPlan.is_active.is_(True)).all()
    return [LiberationPlanResponse.model_validate(item, from_attributes=True) for item in plans_data]


@router.post("/start-checkout", response_model=StartCheckoutResponse)
def start_checkout(
    payload: StartCheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = db.query(LiberationPlan).filter(LiberationPlan.id == payload.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    enrollment = LiberationEnrollment(user_id=current_user.id, plan_id=plan.id, payment_status="paid")
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)

    create_day_progress_rows(db, enrollment.id, plan.days_count)

    return StartCheckoutResponse(
        enrollment_id=enrollment.id,
        checkout_status="created",
        payment_status=enrollment.payment_status,
    )


@router.post("/webhook", response_model=LiberationEnrollmentResponse)
def webhook(payload: WebhookRequest, db: Session = Depends(get_db)):
    enrollment = db.query(LiberationEnrollment).filter(LiberationEnrollment.id == payload.enrollment_id).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    if payload.event == "payment_succeeded":
        enrollment.payment_status = "paid"
    elif payload.event == "payment_failed":
        enrollment.payment_status = "failed"
    db.commit()
    db.refresh(enrollment)
    return LiberationEnrollmentResponse.model_validate(enrollment, from_attributes=True)


@router.get("/me/current", response_model=LiberationEnrollmentResponse | None)
def current_liberation(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    enrollment = (
        db.query(LiberationEnrollment)
        .filter(LiberationEnrollment.user_id == current_user.id)
        .order_by(LiberationEnrollment.start_date.desc())
        .first()
    )
    if not enrollment:
        return None
    return LiberationEnrollmentResponse.model_validate(enrollment, from_attributes=True)


@router.get("/{enrollment_id}/days", response_model=list[DayProgressResponse])
def list_days(enrollment_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _get_user_enrollment(db, current_user.id, enrollment_id)
    days = (
        db.query(LiberationDayProgress)
        .filter(LiberationDayProgress.enrollment_id == enrollment_id)
        .order_by(LiberationDayProgress.day_number.asc())
        .all()
    )
    return [DayProgressResponse.model_validate(item, from_attributes=True) for item in days]


@router.get("/{enrollment_id}/days/{day_number}", response_model=DayProgressResponse)
def get_day(
    enrollment_id: str,
    day_number: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_user_enrollment(db, current_user.id, enrollment_id)
    day = (
        db.query(LiberationDayProgress)
        .filter(
            LiberationDayProgress.enrollment_id == enrollment_id,
            LiberationDayProgress.day_number == day_number,
        )
        .first()
    )
    if not day:
        raise HTTPException(status_code=404, detail="Day not found")
    return DayProgressResponse.model_validate(day, from_attributes=True)


@router.post("/{enrollment_id}/days/{day_number}/complete", response_model=DayProgressResponse)
def complete_day_route(
    enrollment_id: str,
    day_number: int,
    payload: CompleteDayRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_user_enrollment(db, current_user.id, enrollment_id)
    day = (
        db.query(LiberationDayProgress)
        .filter(
            LiberationDayProgress.enrollment_id == enrollment_id,
            LiberationDayProgress.day_number == day_number,
        )
        .first()
    )
    if not day:
        raise HTTPException(status_code=404, detail="Day not found")
    if day.status == DayStatus.locked:
        raise HTTPException(status_code=400, detail="Day is locked")

    completed = complete_day(db, day, payload.energy_level, payload.reflection_note, payload.carry_forward)
    return DayProgressResponse.model_validate(completed, from_attributes=True)


@router.get("/{enrollment_id}/completion", response_model=CompletionSummaryResponse)
def completion(enrollment_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _get_user_enrollment(db, current_user.id, enrollment_id)
    total = (
        db.query(LiberationDayProgress)
        .filter(LiberationDayProgress.enrollment_id == enrollment_id)
        .count()
    )
    completed = (
        db.query(LiberationDayProgress)
        .filter(
            LiberationDayProgress.enrollment_id == enrollment_id,
            LiberationDayProgress.status == DayStatus.completed,
        )
        .count()
    )
    return CompletionSummaryResponse(
        enrollment_id=enrollment_id,
        total_days=total,
        completed_days=completed,
        is_complete=total > 0 and completed == total,
    )
