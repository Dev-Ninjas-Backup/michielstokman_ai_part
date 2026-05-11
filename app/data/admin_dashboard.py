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
    
    # --- Top Stats Overall ---
    total_views = db.query(func.sum(Story.views_count)).scalar() or 0
    avg_pulse = db.query(func.avg(Story.pulse_score)).filter(Story.pulse_score > 0).scalar() or 0.0
    total_shares = db.query(func.sum(Story.shares_count)).scalar() or 0
    
    total_journeys = db.query(UserJourney).count()
    completed_journeys = db.query(UserJourney).filter(UserJourney.status == JourneyStatus.completed).count()
    completion_rate = (completed_journeys / total_journeys * 100) if total_journeys > 0 else 0.0

    # --- Current Week vs Previous Week for Deltas ---
    def get_period_stats(start, end):
        views = db.query(func.sum(Story.views_count)).filter(Story.created_at >= start, Story.created_at < end).scalar() or 0
        shares = db.query(func.sum(Story.shares_count)).filter(Story.created_at >= start, Story.created_at < end).scalar() or 0
        pulse = db.query(func.avg(Story.pulse_score)).filter(Story.created_at >= start, Story.created_at < end, Story.pulse_score > 0).scalar() or 0.0
        
        t_journeys = db.query(UserJourney).filter(UserJourney.created_at >= start, UserJourney.created_at < end).count()
        c_journeys = db.query(UserJourney).filter(UserJourney.created_at >= start, UserJourney.created_at < end, UserJourney.status == JourneyStatus.completed).count()
        c_rate = (c_journeys / t_journeys * 100) if t_journeys > 0 else 0.0
        
        return views, shares, pulse, c_rate

    cw_views, cw_shares, cw_pulse, cw_comp = get_period_stats(seven_days_ago, now)
    pw_views, pw_shares, pw_pulse, pw_comp = get_period_stats(fourteen_days_ago, seven_days_ago)

    top_stats = {
        "total_views": {
            "value": f"{int(total_views):,}",
            **calculate_delta(cw_views, pw_views)
        },
        "avg_resonance": {
            "value": f"{avg_pulse:.1f}",
            **calculate_delta(cw_pulse, pw_pulse, is_absolute_diff=True)
        },
        "completion_rate": {
            "value": f"{int(completion_rate)}%",
            **calculate_delta(cw_comp, pw_comp, is_absolute_diff=True)
        },
        "share_clicks": {
            "value": f"{int(total_shares):,}",
            **calculate_delta(cw_shares, pw_shares)
        }
    }
    
    # --- Weekly Trends ---
    weekly_trends = []
    labels = ["This Week", "Last Week", "2 Weeks Ago", "3 Weeks Ago"]
    
    for i in range(4):
        start_date = now - timedelta(days=(i+1)*7)
        end_date = now - timedelta(days=i*7)
        
        week_stats = db.query(
            func.sum(Story.views_count).label("views"),
            func.avg(Story.pulse_score).label("pulse"),
            func.sum(Story.shares_count).label("shares")
        ).filter(
            Story.created_at >= start_date,
            Story.created_at < end_date
        ).first()
        
        weekly_trends.append({
            "label": labels[i],
            "views": int(week_stats.views or 0),
            "pulse": float(week_stats.pulse or 0.0),
            "shares": int(week_stats.shares or 0)
        })
    
    # --- Top Resonance Content ---
    # Top 5 stories by pulse score this month
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    top_content_query = db.query(Story).filter(
        Story.created_at >= start_of_month,
        Story.title.isnot(None)
    ).order_by(
        desc(Story.pulse_score)
    ).limit(5).all()
    
    top_resonance_content = []
    for story in top_content_query:
        top_resonance_content.append({
            "id": str(story.id),
            "title": story.title or "Untitled",
            "pulse": float(story.pulse_score),
            "reflections": int(story.reflections_count)
        })
        
    return {
        "top_stats": top_stats,
        "weekly_trends": weekly_trends,
        "top_resonance_content": top_resonance_content
    }
