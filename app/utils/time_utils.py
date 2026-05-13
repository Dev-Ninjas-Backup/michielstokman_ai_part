from datetime import datetime, timezone

def format_relative_time(dt: datetime) -> str:
    """
    Returns a human-readable relative time string (e.g., '2 mins ago', '3 hours ago').
    """
    now = datetime.now(timezone.utc)
    # Ensure dt is timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        
    diff = now - dt
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "Just now"
    
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min{'s' if minutes > 1 else ''} ago"
    
    hours = int(minutes // 60)
    if hours < 24:
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    
    days = int(hours // 24)
    if days < 7:
        return f"{days} day{'s' if days > 1 else ''} ago"
    
    return dt.strftime("%d %b %Y")
