from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.entities import DayStatus, EnrollmentStatus, LiberationDayProgress, LiberationEnrollment


DAY_TITLES = [
    "Awakening",
    "Softening",
    "Releasing",
    "Grounding",
    "Flowing",
    "Radiating",
    "Full Bloom",
]


def create_day_progress_rows(db: Session, enrollment_id: str, days_count: int) -> list[LiberationDayProgress]:
    rows: list[LiberationDayProgress] = []
    for day in range(1, days_count + 1):
        rows.append(
            LiberationDayProgress(
                enrollment_id=enrollment_id,
                day_number=day,
                title=DAY_TITLES[day - 1] if day - 1 < len(DAY_TITLES) else f"Day {day}",
                status=DayStatus.ready if day == 1 else DayStatus.locked,
            )
        )
    db.add_all(rows)
    db.commit()
    return rows


def complete_day(db: Session, day: LiberationDayProgress, energy_level: int, reflection_note: str | None, carry_forward: str | None) -> LiberationDayProgress:
    day.status = DayStatus.completed
    day.energy_level = energy_level
    day.reflection_note = reflection_note
    day.carry_forward = carry_forward
    day.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(day)

    next_day = (
        db.query(LiberationDayProgress)
        .filter(
            LiberationDayProgress.enrollment_id == day.enrollment_id,
            LiberationDayProgress.day_number == day.day_number + 1,
        )
        .first()
    )
    if next_day and next_day.status == DayStatus.locked:
        next_day.status = DayStatus.ready
        db.commit()

    enrollment = db.query(LiberationEnrollment).filter(LiberationEnrollment.id == day.enrollment_id).first()
    if enrollment:
        total = (
            db.query(LiberationDayProgress)
            .filter(LiberationDayProgress.enrollment_id == day.enrollment_id)
            .count()
        )
        completed = (
            db.query(LiberationDayProgress)
            .filter(
                LiberationDayProgress.enrollment_id == day.enrollment_id,
                LiberationDayProgress.status == DayStatus.completed,
            )
            .count()
        )
        if total == completed and total > 0:
            enrollment.status = EnrollmentStatus.completed
            enrollment.completed_at = datetime.now(timezone.utc)
            db.commit()

    return day
