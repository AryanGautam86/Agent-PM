"""Time helpers.

Everything is stored in UTC. An engagement's IANA timezone exists only to
answer "has 08:00 happened for this pod yet" and "which working day is this
standup for". Centralised here so no module reaches for ``datetime.now()``
without a timezone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agent_pm.core.errors import ValidationError

WEEKEND = frozenset({5, 6})  # Saturday, Sunday


def utc_now() -> datetime:
    return datetime.now(UTC)


def resolve_zone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(f"Unknown timezone: {timezone_name!r}") from exc


def local_now(timezone_name: str) -> datetime:
    return utc_now().astimezone(resolve_zone(timezone_name))


def local_today(timezone_name: str) -> date:
    return local_now(timezone_name).date()


def to_utc(moment: datetime) -> datetime:
    """Normalise to UTC, treating a naive datetime as already UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def combine_local(day: date, at: time, timezone_name: str) -> datetime:
    """The UTC instant of a wall-clock time on a given day in a pod's zone."""
    return datetime.combine(day, at, tzinfo=resolve_zone(timezone_name)).astimezone(UTC)


def is_working_day(day: date) -> bool:
    """Mon–Fri. Engagement-specific holiday calendars are not modelled yet."""
    return day.weekday() not in WEEKEND


def previous_working_day(day: date) -> date:
    cursor = day - timedelta(days=1)
    while not is_working_day(cursor):
        cursor -= timedelta(days=1)
    return cursor


def age_in_days(since: datetime, *, now: datetime | None = None) -> float:
    return ((now or utc_now()) - to_utc(since)).total_seconds() / 86_400
