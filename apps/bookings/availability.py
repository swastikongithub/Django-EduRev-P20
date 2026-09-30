"""
Availability — what the calendar shows, and *why*.

Every cell carries a state and a sentence. A slot is never simply greyed out:
"CSE326 Lecture · K23KF", "Booked", "Maintenance: projector replacement",
"Diwali break", "Closed", "Needs 24 h notice"... This is also where the
acceptance criterion "timetable-occupied slots never offered" is honoured for
display — the booking service and the database enforce it again on write.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.accounts.permissions import can_manage_resource, is_campus_wide
from apps.core.timeutil import aware, trange

from .models import BookingSlot, BookingStatus, SlotKind

# Display states, in the order a cell is evaluated.
PAST = "past"
CLOSED = "closed"
MINE = "mine"
PENDING = "pending"
BOOKED = "booked"
CLASS = "class"
MAINTENANCE = "maintenance"
BLACKOUT = "blackout"
OUT_OF_SERVICE = "out_of_service"
FORBIDDEN = "forbidden"
RESTRICTED = "restricted"
LEAD = "lead"
BEYOND = "beyond"
FREE = "free"

SELECTABLE = {FREE}

LEGEND = [
    (FREE, "Available"),
    (MINE, "Your booking"),
    (BOOKED, "Booked"),
    (PENDING, "Pending approval"),
    (CLASS, "Timetabled class"),
    (MAINTENANCE, "Maintenance"),
    (BLACKOUT, "Blackout"),
    (CLOSED, "Closed"),
]


@dataclass
class Block:
    kind: str
    start: datetime
    end: datetime
    label: str
    reference: str = ""

    @property
    def minutes(self):
        return int((self.end - self.start).total_seconds() // 60)


@dataclass
class Cell:
    start: datetime
    end: datetime
    state: str
    reason: str = ""

    @property
    def selectable(self):
        return self.state in SELECTABLE

    @property
    def hhmm(self):
        return timezone.localtime(self.start).strftime("%H:%M")


@dataclass
class DaySchedule:
    day: date
    intervals: list[tuple[datetime, datetime]]
    cells: list[Cell] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)

    @property
    def is_open(self):
        return bool(self.intervals)

    @property
    def free_cells(self):
        return [c for c in self.cells if c.state == FREE]

    @property
    def free_minutes(self):
        return sum(int((c.end - c.start).total_seconds() // 60) for c in self.free_cells)

    @property
    def open_minutes(self):
        return sum(int((c - o).total_seconds() // 60) for o, c in self.intervals)

    @property
    def first_free(self):
        f = self.free_cells
        return f[0] if f else None

    @property
    def load(self):
        """0..1 share of open time that is taken (for heat strips)."""
        total = len([c for c in self.cells if c.state not in (CLOSED, PAST)])
        busy = len([c for c in self.cells if c.state in (MINE, BOOKED, PENDING, CLASS, MAINTENANCE)])
        return busy / total if total else 0


class _Context:
    """Per-user facts that don't change between cells."""

    def __init__(self, resource, user, now, policy):
        from apps.checkins.services import active_restriction

        self.now = now
        self.policy = policy
        self.privileged = user.is_authenticated and is_campus_wide(user)
        self.manager = user.is_authenticated and can_manage_resource(user, resource)
        self.user_id = user.pk if user.is_authenticated else None
        self.role = getattr(user, "role", "")
        self.forbidden = bool(
            user.is_authenticated and not resource.type.role_may_book(self.role) and not self.privileged
        )
        self.restriction = active_restriction(user, now) if user.is_authenticated else None
        self.lead_until = now + timedelta(minutes=policy.lead_time_minutes) if not self.privileged else now
        self.horizon = (
            timezone.localtime(now).date() + timedelta(days=policy.max_advance_days)
            if not self.privileged
            else date.max
        )


def _load(resources, start, end):
    """One query for ledger slots, one for bookings metadata, one for blackouts — across all resources."""
    from apps.rules.models import Blackout, Scope

    ids = [r.pk for r in resources]
    slots = defaultdict(list)
    for s in (
        BookingSlot.objects.filter(resource_id__in=ids, period__overlap=trange(start, end))
        .select_related("booking")
        .order_by("period")
    ):
        slots[s.resource_id].append(s)
    type_ids = {r.type_id for r in resources}
    building_ids = {r.building_id for r in resources if r.building_id}
    institution_ids = {r.institution_id for r in resources}
    blackouts = list(
        Blackout.objects.filter(institution_id__in=institution_ids, period__overlap=trange(start, end)).filter(
            Q(scope=Scope.CAMPUS, building__isnull=True)
            | Q(scope=Scope.CAMPUS, building_id__in=building_ids)
            | Q(scope=Scope.TYPE, resource_type_id__in=type_ids)
            | Q(scope=Scope.RESOURCE, resource_id__in=ids)
        )
    )
    return slots, blackouts


def _blackouts_for(resource, blackouts):
    out = []
    for b in blackouts:
        if b.scope == "campus" and (b.building_id is None or b.building_id == resource.building_id):
            out.append(b)
        elif b.scope == "type" and b.resource_type_id == resource.type_id:
            out.append(b)
        elif b.scope == "resource" and b.resource_id == resource.pk:
            out.append(b)
    return out


def _block_for(slot, ctx: _Context) -> Block:
    if slot.kind == SlotKind.CLASS:
        return Block(CLASS, slot.period.lower, slot.period.upper, slot.label)
    if slot.kind == SlotKind.MAINTENANCE:
        return Block(MAINTENANCE, slot.period.lower, slot.period.upper, slot.label or "Maintenance")
    b = slot.booking
    mine = b is not None and ctx.user_id in (b.booked_for_id, b.requester_id)
    if mine:
        return Block(MINE, slot.period.lower, slot.period.upper, b.title, b.reference)
    kind = PENDING if b and b.status == BookingStatus.PENDING else BOOKED
    label = (
        (b.group_label or b.title)
        if (ctx.manager or ctx.privileged) and b
        else ("Requested" if kind == PENDING else "Booked")
    )
    return Block(kind, slot.period.lower, slot.period.upper, label, b.reference if ctx.manager and b else "")


def _day(
    resource, day, ctx: _Context, hours, slots, blackouts, step: int, window: tuple[time, time] | None
) -> DaySchedule:
    from apps.rules.services import opening_intervals

    intervals = opening_intervals(resource, day, hours)
    sched = DaySchedule(day=day, intervals=intervals)
    day_start, day_end = aware(day, time.min), aware(day + timedelta(days=1), time.min)
    blocks = [_block_for(s, ctx) for s in slots if s.period.lower < day_end and s.period.upper > day_start]
    my_blackouts = [b for b in _blackouts_for(resource, blackouts) if ctx.role not in (b.exempt_roles or [])]
    for b in my_blackouts:
        if b.period.lower < day_end and b.period.upper > day_start:
            blocks.append(Block(BLACKOUT, max(b.period.lower, day_start), min(b.period.upper, day_end), b.title))
    sched.blocks = sorted(blocks, key=lambda b: b.start)

    if window:
        lo, hi = aware(day, window[0]), aware(day, window[1]) if window[1] != time.max else day_end
    elif intervals:
        lo, hi = min(o for o, _ in intervals), max(c for _, c in intervals)
    else:
        return sched

    t = lo
    while t < hi:
        u = t + timedelta(minutes=step)
        sched.cells.append(_cell(resource, t, u, ctx, intervals, sched.blocks))
        t = u
    return sched


def _cell(resource, t, u, ctx: _Context, intervals, blocks) -> Cell:
    if u <= ctx.now:
        return Cell(t, u, PAST, "Past")
    if not any(o <= t and u <= c for o, c in intervals):
        return Cell(t, u, CLOSED, "Closed")
    for b in blocks:
        if b.start < u and t < b.end:
            if b.kind == BLACKOUT and ctx.privileged:
                continue
            return Cell(t, u, b.kind, b.label)
    if resource.status != "active":
        return Cell(t, u, OUT_OF_SERVICE, resource.status_note or "Out of service")
    if ctx.forbidden:
        return Cell(t, u, FORBIDDEN, f"{resource.type.plural or resource.type.name} need faculty booking")
    if ctx.restriction:
        return Cell(t, u, RESTRICTED, f"Booking paused until {timezone.localtime(ctx.restriction.ends_at):%d %b}")
    if t < ctx.lead_until:
        if t < ctx.now:
            return Cell(t, u, PAST, "Already started")
        return Cell(
            t,
            u,
            LEAD,
            f"Needs {ctx.policy.lead_time_minutes // 60 or ctx.policy.lead_time_minutes}"
            f"{' h' if ctx.policy.lead_time_minutes >= 60 else ' min'} notice",
        )
    if timezone.localtime(t).date() > ctx.horizon:
        return Cell(t, u, BEYOND, f"Opens {ctx.policy.max_advance_days} days ahead")
    return Cell(t, u, FREE, "Available")


def schedule(resource, days: list[date], user, *, now=None, window=None) -> list[DaySchedule]:
    from apps.rules.services import policy_for, weekly_hours

    now = now or timezone.now()
    policy = policy_for(resource)
    ctx = _Context(resource, user, now, policy)
    start = aware(min(days), time.min)
    end = aware(max(days) + timedelta(days=1), time.min)
    slots, blackouts = _load([resource], start, end)
    hours = weekly_hours(resource)
    return [_day(resource, d, ctx, hours, slots[resource.pk], blackouts, policy.slot_minutes, window) for d in days]


def day(resource, d: date, user, **kw) -> DaySchedule:
    return schedule(resource, [d], user, **kw)[0]


def board(resources, d: date, user, *, now=None, window=(time(7, 0), time(22, 0)), step=30):
    """Many resources, one day, a shared timeline — the live booking board and the 'rooms at 2 pm' view."""
    from apps.rules.services import policy_for, weekly_hours

    now = now or timezone.now()
    resources = list(resources)
    if not resources:
        return []
    slots, blackouts = _load(resources, aware(d, time.min), aware(d + timedelta(days=1), time.min))
    rows = []
    for r in resources:
        policy = policy_for(r)
        ctx = _Context(r, user, now, policy)
        rows.append((r, _day(r, d, ctx, weekly_hours(r), slots[r.pk], blackouts, step, window)))
    return rows


def is_free(resource, start, end) -> bool:
    return not BookingSlot.objects.filter(resource=resource, period__overlap=trange(start, end)).exists()


def busy_resource_ids(resource_ids, start, end) -> set[int]:
    return set(
        BookingSlot.objects.filter(resource_id__in=resource_ids, period__overlap=trange(start, end)).values_list(
            "resource_id", flat=True
        )
    )


def next_free_start(resource, user, *, now=None, horizon_days=7, duration_minutes=60):
    """First start time with `duration_minutes` of contiguous free cells, within the horizon."""
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    for sched in schedule(resource, [today + timedelta(days=i) for i in range(horizon_days)], user, now=now):
        run = []
        for c in sched.cells:
            if c.state == FREE and (not run or run[-1].end == c.start):
                run.append(c)
            else:
                run = [c] if c.state == FREE else []
            if run and (run[-1].end - run[0].start) >= timedelta(minutes=duration_minutes):
                return run[0].start
    return None
