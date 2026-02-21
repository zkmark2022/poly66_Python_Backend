"""UTC datetime utilities."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(UTC)
