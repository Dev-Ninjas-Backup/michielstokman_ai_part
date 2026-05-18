from app.core.config import settings

def format_media_url(url: str | None) -> str | None:
    """
    Prepends the BACKEND_URL to local media paths (e.g., 'media/images/...').
    Returns the full URL or the original URL if it's already absolute (e.g., S3 URL).
    """
    if not url:
        return url
    
    if url.startswith("media/"):
        return f"{settings.BACKEND_URL}/{url}"
        
    return url
