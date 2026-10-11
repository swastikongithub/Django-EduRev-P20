"""Time helpers. The database stores UTC; India Standard Time is used only for "which day is it"."""

from datetime import UTC, date, datetime, timedelta, timezone

# India has no daylight saving, so a fixed offset is exact (and needs no timezone database on Windows).
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def utcnow() -> datetime:
    return datetime.now(UTC)


def today_ist() -> date:
    return datetime.now(IST).date()


def start_of_today_ist() -> datetime:
    return datetime.combine(today_ist(), datetime.min.time(), tzinfo=IST)
