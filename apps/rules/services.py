"""
M2 service interface.

    policy_for(resource)                     -> EffectivePolicy
    opening_intervals(resource, day)         -> [(start_dt, end_dt), ...]
    blackouts_for(resource, start, end)      -> [Blackout]
    validate_request(...)                    -> None | raises BookingRejected
    check_quota(user, resource, start, end)  -> None | raises BookingRejected   (call under lock)
    quota_usage(user)                        -> [QuotaUse]
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.accounts.permissions import has_cap, is_campus_wide
from apps.core.errors import BookingRejected
from apps.core.timeutil import aware, minutes_between, trange

from .models import AvailabilityRule, Blackout, BookingPolicy, Quota, QuotaPeriod, Scope

DEFAULT_HOURS = {wd: [(time(8, 0), time(20, 0))] for wd in range(6)}  # Mon–Sat, when nothing is configured


@dataclass(frozen=True)
class EffectivePolicy:
    slot_minutes: int = 30
    min_duration_minutes: int = 30
    max_duration_minutes: int = 180
    lead_time_minutes: int = 0
    max_advance_days: int = 30
    requires_checkin: bool = True
    checkin_opens_minutes: int = 15
    checkin_grace_minutes: int = 15
    enforce_capacity: bool = True
    source: str = "default"


_POLICY_FIELDS = [f.name for f in fields(EffectivePolicy) if f.name != "source"]


def policy_for(resource) -> EffectivePolicy:
    """Most specific policy wins: resource > type > campus > built-in default."""
    candidates = list(
        BookingPolicy.objects.filter(institution_id=resource.institution_id).filter(
            Q(scope=Scope.RESOURCE, resource_id=resource.pk)
            | Q(scope=Scope.TYPE, resource_type_id=resource.type_id)
            | Q(scope=Scope.CAMPUS)
        )
    )
    rank = {Scope.RESOURCE: 0, Scope.TYPE: 1, Scope.CAMPUS: 2}
    candidates.sort(key=lambda p: rank[p.scope])
    if not candidates:
        return EffectivePolicy()
    p = candidates[0]
    return EffectivePolicy(**{f: getattr(p, f) for f in _POLICY_FIELDS}, source=p.scope_label)


def _hours_rules(resource):
    qs = AvailabilityRule.objects.filter(institution_id=resource.institution_id)
    for scope_q in (
        Q(scope=Scope.RESOURCE, resource_id=resource.pk),
        Q(scope=Scope.TYPE, resource_type_id=resource.type_id),
        Q(scope=Scope.CAMPUS),
    ):
        rules = list(qs.filter(scope_q))
        if rules:
            return rules
    return None


def weekly_hours(resource) -> dict[int, list[tuple[time, time]]]:
    rules = _hours_rules(resource)
    if rules is None:
        return DEFAULT_HOURS
    out: dict[int, list[tuple[time, time]]] = {}
    for r in rules:
        out.setdefault(r.weekday, []).append((r.opens, r.closes))
    for v in out.values():
        v.sort()
    return out


def opening_intervals(resource, day: date, hours=None) -> list[tuple[datetime, datetime]]:
    hours = hours if hours is not None else weekly_hours(resource)
    return [(aware(day, o), aware(day, c)) for o, c in hours.get(day.weekday(), [])]


def blackout_q(resource):
    return (
        Q(scope=Scope.CAMPUS, building__isnull=True)
        | Q(scope=Scope.CAMPUS, building_id=resource.building_id)
        | Q(scope=Scope.TYPE, resource_type_id=resource.type_id)
        | Q(scope=Scope.RESOURCE, resource_id=resource.pk)
    )


def blackouts_for(resource, start: datetime, end: datetime):
    return list(
        Blackout.objects.filter(institution_id=resource.institution_id, period__overlap=trange(start, end)).filter(
            blackout_q(resource)
        )
    )


def _fmt(dt: datetime) -> str:
    return timezone.localtime(dt).strftime("%H:%M")


def validate_request(
    *, requester, booked_for, resource, start: datetime, end: datetime, attendees: int = 1, now=None, policy=None
):
    """Raise BookingRejected (with a human sentence) if the request breaks any rule."""
    now = now or timezone.now()
    policy = policy or policy_for(resource)
    privileged = is_campus_wide(requester)

    if not has_cap(requester, "book_resources"):
        raise BookingRejected("Your account is not allowed to book resources.", code="forbidden")
    if not resource.is_bookable:
        raise BookingRejected(f"{resource.name} is not bookable online.", code="forbidden")
    if resource.status != "active":
        note = f" — {resource.status_note}" if resource.status_note else ""
        raise BookingRejected(f"{resource.name} is out of service{note}.", code="maintenance")
    if not resource.type.role_may_book(requester.role) and not privileged:
        raise BookingRejected(
            f"{resource.type.plural or resource.type.name} can't be booked by {requester.get_role_display().lower()}s. "
            "Ask a faculty member to book it for your group.",
            code="forbidden",
        )

    from apps.checkins.services import active_restriction

    restriction = active_restriction(booked_for, now)
    if restriction:
        raise BookingRejected(
            f"Booking is paused until {timezone.localtime(restriction.ends_at):%d %b, %H:%M} "
            f"after repeated no-shows ({restriction.tier_label or restriction.reason}).",
            code="restricted",
        )

    if end <= start:
        raise BookingRejected("The end time must be after the start time.", code="policy")
    if start < now - timedelta(minutes=1):
        raise BookingRejected("That time has already passed.", code="policy")

    slot = policy.slot_minutes
    local_start = timezone.localtime(start)
    local_end = timezone.localtime(end)
    for dt in (local_start, local_end):
        if dt.minute % slot or dt.second or dt.microsecond:
            raise BookingRejected(f"Bookings start and end on {slot}-minute boundaries.", code="policy")

    duration = minutes_between(start, end)
    if duration < policy.min_duration_minutes:
        raise BookingRejected(f"The minimum booking is {policy.min_duration_minutes} minutes.", code="policy")
    if duration > policy.max_duration_minutes and not privileged:
        raise BookingRejected(
            f"{resource.type.name} bookings are limited to {policy.max_duration_minutes // 60}h"
            f"{'' if policy.max_duration_minutes % 60 == 0 else f' {policy.max_duration_minutes % 60}m'} at a time.",
            code="policy",
        )
    if not privileged:
        if policy.lead_time_minutes and start < now + timedelta(minutes=policy.lead_time_minutes):
            hrs = policy.lead_time_minutes / 60
            notice = f"{hrs:g} hour{'s' if hrs != 1 else ''}" if hrs >= 1 else f"{policy.lead_time_minutes} minutes"
            raise BookingRejected(f"{resource.type.name} needs at least {notice} notice.", code="policy")
        horizon = timezone.localtime(now).date() + timedelta(days=policy.max_advance_days)
        if local_start.date() > horizon:
            raise BookingRejected(
                f"Bookings for {resource.type.plural or resource.type.name} open {policy.max_advance_days} days ahead "
                f"(until {horizon:%d %b}).",
                code="policy",
            )

    if local_start.date() != (local_end - timedelta(microseconds=1)).date():
        raise BookingRejected("A booking must start and end on the same day.", code="policy")
    intervals = opening_intervals(resource, local_start.date())
    if not any(o <= start and end <= c for o, c in intervals):
        if not intervals:
            raise BookingRejected(f"{resource.name} is closed on {local_start:%A}s.", code="closed")
        spans = ", ".join(f"{_fmt(o)}–{_fmt(c)}" for o, c in intervals)
        raise BookingRejected(f"{resource.name} is open {spans} on {local_start:%A}s.", code="closed")

    for b in blackouts_for(resource, start, end):
        if requester.role in (b.exempt_roles or []) or privileged:
            continue
        raise BookingRejected(
            f"{b.title}: bookings are closed {timezone.localtime(b.period.lower):%d %b %H:%M}"
            f" – {timezone.localtime(b.period.upper):%d %b %H:%M}.",
            code="blackout",
        )

    if policy.enforce_capacity and attendees > resource.capacity:
        raise BookingRejected(
            f"{resource.name} holds {resource.capacity}; you entered {attendees} people.", code="policy"
        )


# ── Quotas ──────────────────────────────────────────────────────────────────


def period_window(period: str, at: datetime) -> tuple[datetime, datetime]:
    local = timezone.localtime(at)
    d = local.date()
    if period == QuotaPeriod.DAY:
        start = d
        end = d + timedelta(days=1)
    elif period == QuotaPeriod.WEEK:
        start = d - timedelta(days=d.weekday())
        end = start + timedelta(days=7)
    else:
        start = d.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
    return aware(start, time.min), aware(end, time.min)


def applicable_quotas(user, resource_type_id=None):
    qs = Quota.objects.filter(institution_id=user.institution_id, active=True).filter(
        Q(role=user.role) | Q(department_id=user.department_id, department__isnull=False)
    )
    if resource_type_id is not None:
        qs = qs.filter(Q(resource_type__isnull=True) | Q(resource_type_id=resource_type_id))
    return list(qs.select_related("resource_type", "department"))


@dataclass
class QuotaUse:
    quota: Quota
    window: tuple[datetime, datetime]
    hours_used: Decimal
    bookings_used: int

    @property
    def hours_pct(self):
        return min(100, int(self.hours_used / self.quota.max_hours * 100)) if self.quota.max_hours else None

    @property
    def bookings_pct(self):
        return min(100, int(self.bookings_used * 100 / self.quota.max_bookings)) if self.quota.max_bookings else None

    @property
    def pct(self):
        return max(p for p in (self.hours_pct, self.bookings_pct, 0) if p is not None)


def _usage(quota: Quota, user, window, exclude_booking_id=None) -> tuple[Decimal, int]:
    from apps.bookings.services import consumption

    who = {"department_id": quota.department_id} if quota.is_departmental else {"user_id": user.pk}
    minutes, count = consumption(
        window=window, resource_type_id=quota.resource_type_id, exclude_booking_id=exclude_booking_id, **who
    )
    return (Decimal(minutes) / Decimal(60)).quantize(Decimal("0.1")), count


def check_quota(user, resource, start: datetime, end: datetime, *, exclude_booking_id=None):
    """Must run inside the booking transaction, after the caller locked the user (and department) row."""
    new_hours = Decimal(minutes_between(start, end)) / Decimal(60)
    for q in applicable_quotas(user, resource.type_id):
        window = period_window(q.period, start)
        hours, count = _usage(q, user, window, exclude_booking_id)
        whose = f"{q.department.code} department's" if q.is_departmental else "your"
        scope = f" {q.resource_type.name.lower()}" if q.resource_type_id else ""
        if q.max_bookings is not None and count + 1 > q.max_bookings:
            raise BookingRejected(
                f"This would exceed {whose}{scope} limit of {q.max_bookings} booking{'s' if q.max_bookings != 1 else ''} "
                f"{q.get_period_display()} ({q.name}).",
                code="quota",
                detail={"quota": q.pk},
            )
        if q.max_hours is not None and hours + new_hours > q.max_hours:
            left = max(Decimal(0), q.max_hours - hours)
            raise BookingRejected(
                f"This would exceed {whose}{scope} limit of {q.max_hours:g} h {q.get_period_display()} — "
                f"{left:g} h left ({q.name}).",
                code="quota",
                detail={"quota": q.pk},
            )


def quota_usage(user, at=None) -> list[QuotaUse]:
    at = at or timezone.now()
    out = []
    for q in applicable_quotas(user):
        window = period_window(q.period, at)
        hours, count = _usage(q, user, window)
        out.append(QuotaUse(q, window, hours, count))
    return out
