"""Refresh scheduling helpers for Cardiff Bin Collections."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .const import REFRESH_WINDOW_MINUTES, REFRESH_WINDOW_START_HOUR

SUNDAY = 6


def refresh_time_for_uprn(uprn: int) -> time:
    """Return a stable refresh time between 05:00 and 08:59 for a UPRN."""
    offset = uprn % REFRESH_WINDOW_MINUTES
    hour, minute = divmod(offset, 60)
    return time(hour=REFRESH_WINDOW_START_HOUR + hour, minute=minute)


def next_sunday_refresh(now: datetime, timezone_info: ZoneInfo, uprn: int) -> datetime:
    """Return the next scheduled Sunday refresh in UTC."""
    local_now = now.astimezone(timezone_info)
    days_until_sunday = (SUNDAY - local_now.weekday()) % 7
    candidate = datetime.combine(
        local_now.date() + timedelta(days=days_until_sunday),
        refresh_time_for_uprn(uprn),
        tzinfo=timezone_info,
    )
    if candidate <= local_now:
        candidate += timedelta(days=7)
    return candidate.astimezone(UTC)
