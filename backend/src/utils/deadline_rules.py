from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


def inclusive_calendar_day_offset(days: int) -> int:
    """Return the timedelta offset for a deadline that includes the start day."""
    if days <= 0:
        return 0
    return days - 1


def add_inclusive_calendar_days(base_date: Optional[datetime], days: int) -> Optional[datetime]:
    """Add calendar days to a base date while counting the base date as day 1."""
    if not base_date:
        return None
    return base_date + timedelta(days=inclusive_calendar_day_offset(days))
