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
    
    # --- Top Stats (Figma Row: Total Views, Avg Resonance, Completion Rate, Share Clicks) ---
    def get_metrics(start=None, end=None):
        # 1. Stories metrics
        story_query = db.query(Story)
        if start:
            story_query = story_query.filter(Story.created_at >= start)
        if end:
            story_query = story_query.filter(Story.created_at < end)
            
        story_stats = story_query.with_entities(
            func.sum(Story.views_count).label("views"),
            func.avg(Story.pulse_score).label("pulse"),
            func.sum(Story.shares_count).label("shares")
        ).first()
        
        # 2. Completion metrics
        journey_query = db.query(UserJourney)
        if start:
            journey_query = journey_query.filter(UserJourney.created_at >= start)
        if end:
            journey_query = journey_query.filter(UserJourney.created_at < end)
            
        all_journeys = journey_query.count()
        completed_journeys = journey_query.filter(UserJourney.status == JourneyStatus.completed).count()
        completion_rate = (completed_journeys / all_journeys * 100.0) if all_journeys > 0 else 0.0
        
        return {
            "views": int(story_stats.views or 0),
            "pulse": float(story_stats.pulse or 0.0),
            "shares": int(story_stats.shares or 0),
            "completion": completion_rate
        }

    # Overall totals for the big numbers
    overall = get_metrics()
    # Current week (cw) and Previous week (pw) for the deltas
    cw = get_metrics(seven_days_ago, now)
    pw = get_metrics(fourteen_days_ago, seven_days_ago)

    top_stats = {
        "views": {
            "value": f"{overall['views']:,}",
            **calculate_delta(cw['views'], pw['views'])
        },
        "resonance": {
            "value": f"{overall['pulse']:.1f}",
            **calculate_delta(cw['pulse'], pw['pulse'], is_absolute_diff=True)
        },
        "completion": {
            "value": f"{int(overall['completion'])}%",
            **calculate_delta(cw['completion'], pw['completion'])
        },
        "shares": {
            "value": f"{overall['shares']:,}",
            **calculate_delta(cw['shares'], pw['shares'])
        }
    }
    
    # --- Weekly Trends (Chart) ---
    weekly_trends = []
    labels = ["This Week", "Last Week", "2 Weeks Ago", "3 Weeks Ago"]
    for i in range(4):
        start_date = now - timedelta(days=(i+1)*7)
        end_date = now - timedelta(days=i*7)
        week_metrics = get_metrics(start_date, end_date)
        weekly_trends.append({
            "label": labels[i],
            "views": week_metrics["views"],
            "pulse": week_metrics["pulse"],
            "shares": week_metrics["shares"]
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
            "time_ago": "Recently" 
        })

    return {
        "top_stats": top_stats,
        "weekly_trends": weekly_trends,
        "top_resonance_content": top_resonance_content,
        "latest_activity": latest_activity
    }

