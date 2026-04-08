from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


SUPPORTED_INPUT_FORMATS = (
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%m-%d %H:%M",
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def to_local(dt: datetime, timezone_name: str) -> datetime:
    return dt.astimezone(ZoneInfo(timezone_name))


def format_local(dt: datetime, timezone_name: str) -> str:
    local_dt = to_local(dt, timezone_name)
    return local_dt.strftime("%Y-%m-%d %H:%M %Z")


def parse_user_datetime(value: str, timezone_name: str) -> datetime:
    zone = ZoneInfo(timezone_name)
    for fmt in SUPPORTED_INPUT_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if fmt == "%m-%d %H:%M":
            parsed = parsed.replace(year=datetime.now(zone).year)
        return parsed.replace(tzinfo=zone).astimezone(UTC)
    raise ValueError("日時は YYYY-MM-DDTHH:MM 形式で指定してください。")
