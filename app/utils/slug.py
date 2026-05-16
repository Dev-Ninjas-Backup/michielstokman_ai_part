import re
import unicodedata

def generate_slug(text: str) -> str:
    """
    Simplifies a string into a URL-friendly slug.
    Example: "The Path to Inner Peace" -> "the-path-to-inner-peace"
    """
    # Normalize unicode characters to ASCII
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    # Remove non-word characters (excluding spaces and hyphens)
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    # Replace spaces and multiple hyphens with a single hyphen
    return re.sub(r'[-\s]+', '-', text)
