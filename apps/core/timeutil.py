from datetime import date, datetime, time, timedelta

from django.utils import timezone
from psycopg.types.range import Range

ONE_MINUTE = timedelta(minutes=1)


def local_now():
    return timezone.localtime()


def aware(d: date, t: time) -> datetime:
    return timezone.make_aware(datetime.combine(d, t), timezone.get_current_timezone())


def trange(start: datetime, end: datetime) -> Range:
    """Half-open [start, end) timestamp range."""
    return Range(start, end, "[)")


def minutes_between(a: datetime, b: datetime) -> int:
    return max(0, int((b - a).total_seconds() // 60))


def overlap_minutes(a_start, a_end, b_start, b_end) -> int:
    return minutes_between(max(a_start, b_start), min(a_end, b_end)) if a_start < b_end and b_start < a_end else 0


def day_bounds(d: date):
    start = aware(d, time.min)
    return start, start + timedelta(days=1)


def floor_to(dt: datetime, minutes: int) -> datetime:
    discard = timedelta(minutes=dt.minute % minutes, seconds=dt.second, microseconds=dt.microsecond)
    return dt - discard


def ceil_to(dt: datetime, minutes: int) -> datetime:
    floored = floor_to(dt, minutes)
    return floored if floored == dt else floored + timedelta(minutes=minutes)
