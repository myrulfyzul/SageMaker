"""UTC timestamps and month bucketing in the configured application time zone."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def to_local(value: datetime | str, tz_name: str) -> datetime:
    dt = parse_iso(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(tz_name))


def month_bucket(value: datetime | str, tz_name: str) -> str:
    """'YYYY-MM' of the instant in the application time zone."""
    local = to_local(value, tz_name)
    return f'{local.year:04d}-{local.month:02d}'


def today_local(tz_name: str) -> date:
    return utc_now().astimezone(ZoneInfo(tz_name)).date()
