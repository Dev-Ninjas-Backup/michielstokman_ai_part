"""Helpers for the legacy `location` string vs city / country columns."""

from typing import Optional


def split_location(location: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Split a legacy single-string place into city / country on the last comma."""
    if not location or not str(location).strip():
        return None, None
    text = str(location).strip()
    if "," not in text:
        return text, None
    city, _, country = text.rpartition(",")
    city = city.strip() or None
    country = country.strip() or None
    return city, country


def join_location(city: Optional[str], country: Optional[str]) -> Optional[str]:
    """Rebuild the legacy `location` string public responses still read."""
    parts = [part for part in [(city or "").strip(), (country or "").strip()] if part]
    return ", ".join(parts) or None
