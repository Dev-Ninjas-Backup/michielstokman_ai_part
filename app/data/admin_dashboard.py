from sqlalchemy.orm import Session
from sqlalchemy import func, desc, select, Float
from datetime import datetime, timedelta, timezone

from app.model.story import Story
from app.model.liberation import UserJourney, JourneyStatus

def calculate_delta(current: float, previous: float, is_absolute_diff: bool = False) -> dict:
    if is_absolute_diff:
        change = current - previous
    else:
        if previous == 0:
            change = 100.0 if current > 0 else 0.0
        else:
            change = ((current - previous) / previous) * 100.0

    trend = "up" if change > 0 else "down" if change < 0 else "neutral"
    sign = "+" if change > 0 else ""
    pct_str = f"{sign}{change:.1f}%" if abs(change) < 10 and not change.is_integer() else f"{sign}{int(change)}%"
    
    if is_absolute_diff:
        pct_str = f"{sign}{change:.1f}" if not change.is_integer() else f"{sign}{int(change)}"
        
    return {"percentage": pct_str, "trend": trend}

def get_figma_dashboard_stats(db: Session):
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)
    
    # --- Top Stats (Figma Row: All, Confessions, Meditations, Journey) ---
    from app.model.story import StoryType, GenerationStatus
    
    def get_counts(start=None, end=None):
        base = db.query(Story).filter(Story.generation_status == GenerationStatus.completed)
        if start:
            base = base.filter(Story.created_at >= start)
        if end:
            base = base.filter(Story.created_at < end)
            
        total = base.count()
        confessions = base.filter(Story.story_type == StoryType.confession).count()
        meditations = base.filter(Story.story_type == StoryType.meditation).count()
        journey = base.filter(Story.story_type == StoryType.transformation).count()
        return total, confessions, meditations, journey

    overall_all, overall_conf, overall_med, overall_jour = get_counts()
    cw_all, cw_conf, cw_med, cw_jour = get_counts(seven_days_ago, now)
    pw_all, pw_conf, pw_med, pw_jour = get_counts(fourteen_days_ago, seven_days_ago)

    top_stats = {
        "all": {
            "value": f"{overall_all:,}",
            **calculate_delta(cw_all, pw_all)
        },
        "confessions": {
            "value": f"{overall_conf:,}",
            **calculate_delta(cw_conf, pw_conf)
        },
        "meditations": {
            "value": f"{overall_med:,}",
            **calculate_delta(cw_med, pw_med)
        },
        "journey": {
            "value": f"{overall_jour:,}",
            **calculate_delta(cw_jour, pw_jour)
        }
    }
    
    # --- Weekly Trends (Keep views/pulse/shares for the chart) ---
    weekly_trends = []
    labels = ["This Week", "Last Week", "2 Weeks Ago", "3 Weeks Ago"]
    for i in range(4):
        start_date = now - timedelta(days=(i+1)*7)
        end_date = now - timedelta(days=i*7)
        week_stats = db.query(
            func.sum(Story.views_count).label("views"),
            func.avg(Story.pulse_score).label("pulse"),
            func.sum(Story.shares_count).label("shares")
        ).filter(Story.created_at >= start_date, Story.created_at < end_date).first()
        weekly_trends.append({
            "label": labels[i],
            "views": int(week_stats.views or 0),
            "pulse": float(week_stats.pulse or 0.0),
            "shares": int(week_stats.shares or 0)
        })
    
    # --- Top Resonance Content ---
    top_content_query = db.query(Story).filter(
        Story.pulse_score.isnot(None),
        Story.title.isnot(None)
    ).order_by(desc(Story.pulse_score)).limit(5).all()
    
    top_resonance_content = []
    for story in top_content_query:
        top_resonance_content.append({
            "id": str(story.id),
            "title": story.title or "Untitled",
            "pulse": float(story.pulse_score),
            "reflections": int(getattr(story, 'reflections_count', 0))
        })
        
    # --- Latest Activity ---
    from app.model.user import User
    latest_stories = db.query(Story).join(User, Story.user_id == User.id).order_by(desc(Story.created_at)).limit(5).all()
    latest_activity = []
    for s in latest_stories:
        latest_activity.append({
            "user_email": s.user.email if s.user else "Anonymous",
            "action": f"generated a {str(s.story_type).replace('StoryType.', '')}",
            "time_ago": "Recently" # Frontend usually calculates this from ISO date
        })

    return {
        "top_stats": top_stats,
        "weekly_trends": weekly_trends,
        "top_resonance_content": top_resonance_content,
        "latest_activity": latest_activity
    }
