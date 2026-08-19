"""
app/utils/text.py
Small text helpers shared by the discovery feed and the member story library so
both render story previews the same way.
"""
import re
from typing import Optional

# Matches the length the discovery feed cards were already built around.
DEFAULT_EXCERPT_CHARS = 120

_WHITESPACE = re.compile(r"\s+")
_SSML_BREAK = re.compile(r'<break\s+time="[^"]*"\s*/>', re.IGNORECASE)


def build_excerpt(text: Optional[str], max_chars: int = DEFAULT_EXCERPT_CHARS) -> Optional[str]:
    """
    Condenses story text into a single-line preview for feed and library cards.

    Narration text carries paragraph breaks and, on some rows, leftover SSML
    pause markers; both are stripped so the preview reads as one clean sentence.
    Truncation lands on a word boundary and the ellipsis is only added when
    something was actually cut.
    """
    if not text:
        return None

    flat = _WHITESPACE.sub(" ", _SSML_BREAK.sub(" ", text)).strip()
    if not flat:
        return None
    if len(flat) <= max_chars:
        return flat

    clipped = flat[:max_chars]
    boundary = clipped.rfind(" ")
    # Fall back to a hard cut when the text has no spaces to break on, rather
    # than returning a stub that says nothing.
    if boundary > max_chars * 0.5:
        clipped = clipped[:boundary]
    return clipped.rstrip(" ,;:.!?—-") + "…"
