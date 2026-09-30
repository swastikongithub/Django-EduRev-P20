"""
M9 — Analytics & Reporting.

    build_snapshot(resource, day) -> UtilisationSnapshot
    build_snapshots(day, institution_id=None) -> int           nightly Celery Beat job, idempotent (upsert)
    backfill(start_day, end_day, institution_id=None) -> int   used by the demo seeder

Dashboard queries return plain dicts/lists ready for templates. Each takes
``(institution_id, start, end, department_id=None, resource_type_id=None)`` — the
scope filters apply to the *resource* (its owning department / its type), so a
department head sees only their department's rooms and kit:

    overview(...)                        headline KPIs
    utilisation_by(dimension, ...)       dimension in {"resource", "type", "department", "building"}
    idle_capacity_ranking(...)           expensive, under-used resources first
    heatmap(...)                         7 weekdays x 24 hours of booked + class minutes
    no_show_rates(...)                   by user and by resource
    demand_vs_supply(...)                denied attempts vs bookings vs utilisation per type
    approval_turnaround(...)
    maintenance_downtime(...)
    department_quota_consumption(...)    departmental quotas, used vs limit, current period
    daily_series(...)                    per-day booked / used / no-shows for trend charts

Why snapshots
-------------
Utilisation needs interval arithmetic (opening hours minus blackouts minus
maintenance, unions of bookings) that SQL can do but that is painful to express
and slow to repeat for every dashboard view. So the arithmetic happens once per
resource-day, in the nightly job, and every dashboard is then a cheap
``GROUP BY`` over ``UtilisationSnapshot``. Only facts the snapshot cannot carry
(who no-showed, approval timings, live queues, quota windows) read live tables.

Definitions (per resource, per local calendar day)
--------------------------------------------------
- ``opening``           the resource's opening hours that day (resource > type > campus rules).
- ``class_minutes``     timetabled class slots on the ledger (BookingSlot kind=class) that day.
- ``maintenance_minutes`` maintenance slots on the ledger that fall inside opening hours
                        (bookable time lost to maintenance).
- ``open_minutes``      the *bookable supply*: opening − blackouts − maintenance − classes.
                        Class time is excluded because nobody can book it; it is added back in
                        the utilisation denominator below. A blackout removes supply even if
                        some roles are exempt from it.
- ``booked_minutes``    union of bookings in approved / checked_in / completed / no_show that
                        overlap the day. A no-show counts as booked-but-unused (the time was
                        withheld from everyone else until release). An early check-out shrinks
                        the booking, so the handed-back tail is *not* booked — it shows up in
                        ``released_minutes`` instead.
- ``used_minutes``      union of checked-in time: checked_in_at → checked_out_at (or the end).
- ``released_minutes``  NoShow.released_minutes + CheckIn.minutes_released (early check-out),
                        attributed to the day the booking starts.
- ``bookings`` / ``no_shows`` / ``cancellations``  counts of bookings *starting* that day
                        (bookings = approved/checked_in/completed/no_show).
- ``denied_attempts``   BookingAttempt rows for that day's time with outcome conflict /
                        timetable / maintenance — demand that the supply could not meet. Rule
                        refusals (quota, closed, policy...) are not unmet *capacity* demand.
- ``hourly_booked``     24 buckets (local hours) of booked + class minutes.

Derived metrics shown to users
------------------------------
- **Utilisation** = (class_minutes + booked_minutes) / (open_minutes + class_minutes), capped at
  100 %. The denominator is the time the resource could have been in use; the numerator is the
  time something (a class or a booking) had claimed it.
- **Realised utilisation** = (class_minutes + used_minutes) / (open_minutes + class_minutes) —
  what was actually used once no-shows and early exits are taken out.
- **Idle capacity** = open minutes not booked = max(0, open_minutes − booked_minutes).
- **No-show rate** = no_shows / bookings.
- Hours are floats rounded to 0.1; percentages are floats rounded to 0.1 (0.0 when undefined).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import connection
from django.db.models import (
    Avg,
    Count,
    DecimalField,
    DurationField,
    ExpressionWrapper,
    F,
    IntegerField,
    Q,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, Greatest, Least
from django.utils import timezone

from apps.bookings.models import AttemptOutcome, Booking, BookingAttempt, BookingSlot, BookingStatus, SlotKind
from apps.catalogue.models import Resource, ResourceStatus
from apps.core.db import RangeLower, RangeUpper
from apps.core.timeutil import aware, day_bounds, trange

from .models import UtilisationSnapshot

BOOKED_STATUSES = (
    BookingStatus.APPROVED,
    BookingStatus.CHECKED_IN,
    BookingStatus.COMPLETED,
    BookingStatus.NO_SHOW,
)
DENIED_OUTCOMES = (AttemptOutcome.CONFLICT, AttemptOutcome.TIMETABLE, AttemptOutcome.MAINTENANCE)

# demand_vs_supply: a resource type "needs more capacity" when enough requests were turned away
# AND either a large share of demand was refused or the existing units are already busy.
DEMAND_MIN_DENIED = 3
DEMAND_DENIAL_RATE_PCT = 20.0
DEMAND_UTILISATION_PCT = 75.0

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DIMENSIONS = {
    "resource": ("resource_id", "resource__name"),
    "type": ("resource__type_id", "resource__type__name"),
    "department": ("resource__department_id", "resource__department__name"),
    "building": ("resource__building_id", "resource__building__name"),
}
UNASSIGNED = "Unassigned"

_SNAPSHOT_FIELDS = [
    "open_minutes",
    "class_minutes",
    "maintenance_minutes",
    "booked_minutes",
    "used_minutes",
    "released_minutes",
    "bookings",
    "no_shows",
    "cancellations",
    "denied_attempts",
    "hourly_booked",
]


# ── Interval arithmetic ─────────────────────────────────────────────────────
# Intervals are half-open (start, end) tuples of aware datetimes. A resource has at
# most a few dozen claims a day, so plain Python here is cheaper than a round trip.


def _merge(intervals):
    out: list[tuple[datetime, datetime]] = []
    for s, e in sorted(i for i in intervals if i[0] < i[1]):
        if out and s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def _clip(intervals, lo, hi):
    return [(max(s, lo), min(e, hi)) for s, e in intervals if s < hi and e > lo]


def _intersect(a, b):
    return _merge([(max(s1, s2), min(e1, e2)) for s1, e1 in a for s2, e2 in b if s1 < e2 and s2 < e1])


def _subtract(a, b):
    """a − b, both merged."""
    out = []
    for s, e in a:
        cur = s
        for bs, be in b:
            if be <= cur or bs >= e:
                continue
            if bs > cur:
                out.append((cur, bs))
            cur = max(cur, be)
            if cur >= e:
                break
        if cur < e:
            out.append((cur, e))
    return out


def _minutes(intervals) -> int:
    return int(sum((e - s).total_seconds() for s, e in intervals) // 60)


# ── Snapshot building ───────────────────────────────────────────────────────


@dataclass
class _Context:
    """Facts that do not change from day to day, loaded once per build/backfill."""

    resources: list
    hours: dict  # resource pk -> weekly hours {weekday: [(opens, closes)]}


def _hours_index(resources) -> dict[int, dict]:
    """
    weekly_hours() for many resources with one query. Mirrors rules.services.weekly_hours:
    the most specific scope that has *any* rule wins, else the built-in default.
    """
    from apps.rules.models import AvailabilityRule, Scope
    from apps.rules.services import DEFAULT_HOURS

    by_resource: dict = defaultdict(lambda: defaultdict(list))
    by_type: dict = defaultdict(lambda: defaultdict(list))
    by_campus: dict = defaultdict(lambda: defaultdict(list))
    rows = AvailabilityRule.objects.filter(institution_id__in={r.institution_id for r in resources}).values_list(
        "institution_id", "scope", "resource_type_id", "resource_id", "weekday", "opens", "closes"
    )
    for inst, scope, type_id, resource_id, wd, opens, closes in rows:
        if scope == Scope.RESOURCE:
            by_resource[resource_id][wd].append((opens, closes))
        elif scope == Scope.TYPE:
            by_type[type_id][wd].append((opens, closes))
        else:
            by_campus[inst][wd].append((opens, closes))
    for index in (by_resource, by_type, by_campus):
        for week in index.values():
            for spans in week.values():
                spans.sort()
    out = {}
    for r in resources:
        week = by_resource.get(r.pk) or by_type.get(r.type_id) or by_campus.get(r.institution_id)
        out[r.pk] = dict(week) if week else DEFAULT_HOURS
    return out


def _context(resources) -> _Context:
    resources = list(resources)
    return _Context(resources=resources, hours=_hours_index(resources) if resources else {})


def _blackout_applies(b, r) -> bool:
    if b.institution_id != r.institution_id:
        return False
    if b.scope == "campus":
        return b.building_id is None or b.building_id == r.building_id
    if b.scope == "type":
        return b.resource_type_id == r.type_id
    return b.resource_id == r.pk


def _compute_day(ctx: _Context, day: date) -> dict[int, dict]:
    """
    Snapshot field values for every resource in ``ctx`` on ``day``.
    Five queries regardless of how many resources: blackouts, ledger slots,
    bookings (with check-in / no-show facts joined), denied attempts.
    """
    from apps.rules.models import Blackout
    from apps.rules.services import opening_intervals

    if not ctx.resources:
        return {}
    ds, de = day_bounds(day)
    span = trange(ds, de)
    ids = [r.pk for r in ctx.resources]

    blackouts = list(
        Blackout.objects.filter(
            institution_id__in={r.institution_id for r in ctx.resources}, period__overlap=span
        ).only("institution_id", "scope", "building_id", "resource_type_id", "resource_id", "period")
    )

    classes: dict[int, list] = defaultdict(list)
    maintenance: dict[int, list] = defaultdict(list)
    for rid, kind, period in BookingSlot.objects.filter(
        resource_id__in=ids, kind__in=(SlotKind.CLASS, SlotKind.MAINTENANCE), period__overlap=span
    ).values_list("resource_id", "kind", "period"):
        (classes if kind == SlotKind.CLASS else maintenance)[rid].append((period.lower, period.upper))

    bookings: dict[int, list] = defaultdict(list)
    for row in Booking.objects.filter(
        resource_id__in=ids, period__overlap=span, status__in=(*BOOKED_STATUSES, BookingStatus.CANCELLED)
    ).values_list(
        "resource_id",
        "status",
        "period",
        "checked_in_at",
        "checked_out_at",
        "checkin__minutes_released",
        "no_show__released_minutes",
    ):
        bookings[row[0]].append(row[1:])

    denied = dict(
        BookingAttempt.objects.filter(
            resource_id__in=ids, outcome__in=DENIED_OUTCOMES, period__startswith__gte=ds, period__startswith__lt=de
        )
        .order_by()
        .values("resource_id")
        .annotate(n=Count("id"))
        .values_list("resource_id", "n")
    )

    hour_windows = [(aware(day, time(h)), aware(day, time(h + 1)) if h < 23 else de) for h in range(24)]
    out = {}
    for r in ctx.resources:
        opening = _merge(_clip(opening_intervals(r, day, ctx.hours[r.pk]), ds, de))
        klass = _merge(_clip(classes[r.pk], ds, de))
        maint = _intersect(_merge(_clip(maintenance[r.pk], ds, de)), opening)
        blocked = _intersect(
            _merge(_clip([(b.period.lower, b.period.upper) for b in blackouts if _blackout_applies(b, r)], ds, de)),
            opening,
        )
        supply = _subtract(opening, _merge(blocked + maint + klass))

        booked_iv, used_iv = [], []
        n_bookings = n_no_shows = n_cancelled = released = 0
        for status, period, checked_in_at, checked_out_at, early_release, no_show_release in bookings[r.pk]:
            starts_today = ds <= period.lower < de
            if status == BookingStatus.CANCELLED:
                n_cancelled += starts_today
                continue
            booked_iv.append((period.lower, period.upper))
            if checked_in_at:
                used_iv.append((checked_in_at, checked_out_at or period.upper))
            if starts_today:
                n_bookings += 1
                n_no_shows += status == BookingStatus.NO_SHOW
                released += (early_release or 0) + (no_show_release or 0)
        booked = _merge(_clip(booked_iv, ds, de))
        used = _merge(_clip(used_iv, ds, de))
        busy = _merge(booked + klass)

        out[r.pk] = {
            "open_minutes": _minutes(supply),
            "class_minutes": _minutes(klass),
            "maintenance_minutes": _minutes(maint),
            "booked_minutes": _minutes(booked),
            "used_minutes": _minutes(used),
            "released_minutes": released,
            "bookings": n_bookings,
            "no_shows": n_no_shows,
            "cancellations": n_cancelled,
            "denied_attempts": denied.get(r.pk, 0),
            "hourly_booked": [_minutes(_intersect(busy, [w])) for w in hour_windows],
        }
    return out


def _snapshot_resources(institution_id=None):
    """Resources that belong in utilisation reporting: bookable and not retired."""
    qs = Resource.objects.filter(is_bookable=True).exclude(status=ResourceStatus.RETIRED)
    if institution_id is not None:
        qs = qs.filter(institution_id=institution_id)
    return qs.order_by("pk").only("pk", "institution_id", "type_id", "building_id")


def _upsert(day: date, values: dict[int, dict]) -> int:
    rows = [UtilisationSnapshot(resource_id=rid, date=day, **fields) for rid, fields in values.items()]
    UtilisationSnapshot.objects.bulk_create(
        rows,
        batch_size=500,
        update_conflicts=True,
        unique_fields=["resource", "date"],
        update_fields=[*_SNAPSHOT_FIELDS, "built_at"],
    )
    return len(rows)


def build_snapshot(resource, day: date) -> UtilisationSnapshot:
    """(Re)build one resource-day. Idempotent: the (resource, date) row is updated in place."""
    values = _compute_day(_context([resource]), day)[resource.pk]
    snap, _ = UtilisationSnapshot.objects.update_or_create(resource=resource, date=day, defaults=values)
    return snap


def build_snapshots(day: date, institution_id=None) -> int:
    """Nightly job: every reportable resource for ``day``, one bulk upsert. Returns rows written."""
    return _upsert(day, _compute_day(_context(_snapshot_resources(institution_id)), day))


def backfill(start_day: date, end_day: date, institution_id=None) -> int:
    """Build snapshots for every day in [start_day, end_day]. Returns rows written."""
    ctx = _context(_snapshot_resources(institution_id))
    n = 0
    d = start_day
    while d <= end_day:
        n += _upsert(d, _compute_day(ctx, d))
        d += timedelta(days=1)
    return n


# ── Dashboard helpers ───────────────────────────────────────────────────────


def _h(minutes) -> float:
    return round((minutes or 0) / 60, 1)


def _pct(num, den, cap=None) -> float:
    if not den:
        return 0.0
    p = round(100 * num / den, 1)
    return min(p, cap) if cap is not None else p


def _range_bounds(start: date, end: date):
    return aware(start, time.min), aware(end + timedelta(days=1), time.min)


def _scope(qs, prefix: str, department_id=None, resource_type_id=None):
    """Apply the resource scope filters; ``prefix`` is the path to the Resource ("resource__", ...)."""
    if department_id is not None:
        qs = qs.filter(**{f"{prefix}department_id": department_id})
    if resource_type_id is not None:
        qs = qs.filter(**{f"{prefix}type_id": resource_type_id})
    return qs


def _snapshots(institution_id, start, end, department_id=None, resource_type_id=None):
    qs = UtilisationSnapshot.objects.filter(resource__institution_id=institution_id, date__gte=start, date__lte=end)
    return _scope(qs, "resource__", department_id, resource_type_id).order_by()


def _idle_expr():
    return Greatest(F("open_minutes") - F("booked_minutes"), Value(0), output_field=IntegerField())


def _totals():
    """Aggregates shared by every snapshot roll-up (names are the raw minute/count totals)."""
    return {
        "open_m": Sum("open_minutes", default=0),
        "class_m": Sum("class_minutes", default=0),
        "maint_m": Sum("maintenance_minutes", default=0),
        "booked_m": Sum("booked_minutes", default=0),
        "used_m": Sum("used_minutes", default=0),
        "released_m": Sum("released_minutes", default=0),
        "idle_m": Sum(_idle_expr(), default=0),
        "n_bookings": Sum("bookings", default=0),
        "n_no_shows": Sum("no_shows", default=0),
        "n_cancellations": Sum("cancellations", default=0),
        "n_denied": Sum("denied_attempts", default=0),
    }


def _metrics(row: dict) -> dict:
    supply = row["open_m"] + row["class_m"]
    return {
        "open_hours": _h(row["open_m"]),
        "class_hours": _h(row["class_m"]),
        "maintenance_hours": _h(row["maint_m"]),
        "booked_hours": _h(row["booked_m"]),
        "used_hours": _h(row["used_m"]),
        "released_hours": _h(row["released_m"]),
        "idle_hours": _h(row["idle_m"]),
        "utilisation_pct": _pct(row["class_m"] + row["booked_m"], supply, cap=100.0),
        "realised_pct": _pct(row["class_m"] + row["used_m"], supply, cap=100.0),
        "bookings": row["n_bookings"],
        "no_shows": row["n_no_shows"],
        "no_show_rate_pct": _pct(row["n_no_shows"], row["n_bookings"]),
        "cancellations": row["n_cancellations"],
        "denied_attempts": row["n_denied"],
    }


# ── Dashboard queries ───────────────────────────────────────────────────────


def utilisation_by(
    dimension: str, institution_id, start: date, end: date, department_id=None, resource_type_id=None
) -> list[dict]:
    """
    One row per resource / type / department / building, busiest first:
    ``{key, label, resources, open_hours, class_hours, maintenance_hours, booked_hours, used_hours,
    released_hours, idle_hours, utilisation_pct, realised_pct, bookings, no_shows, no_show_rate_pct,
    cancellations, denied_attempts}``. ``key`` is the id (None for "Unassigned").
    """
    if dimension not in DIMENSIONS:
        raise ValueError(f"Unknown dimension {dimension!r}; expected one of {sorted(DIMENSIONS)}")
    key, label = DIMENSIONS[dimension]
    rows = (
        _snapshots(institution_id, start, end, department_id, resource_type_id)
        .values(key, label)
        .annotate(resources=Count("resource_id", distinct=True), **_totals())
    )
    out = [{"key": r[key], "label": r[label] or UNASSIGNED, "resources": r["resources"], **_metrics(r)} for r in rows]
    out.sort(key=lambda r: (-r["utilisation_pct"], -r["booked_hours"], r["label"]))
    return out


def overview(institution_id, start: date, end: date, department_id=None, resource_type_id=None) -> dict:
    """
    Headline KPIs for the range. All of ``_metrics`` (utilisation_pct, realised_pct, booked_hours,
    used_hours, idle_hours, open_hours, class_hours, maintenance_hours, released_hours, bookings,
    no_shows, no_show_rate_pct, cancellations, denied_attempts) plus:

    - ``resources``            resources with snapshots in the range
    - ``days``                 length of the range
    - ``pending_approvals``    live count of requests awaiting a decision (not date-filtered: it is a queue)
    - ``avg_turnaround_hours`` mean request→decision hours for steps decided in the range (None if none)
    - ``top_resource``         the busiest resource's utilisation_by("resource") row, or None
    """
    from apps.approvals.services import turnaround_hours

    totals = _snapshots(institution_id, start, end, department_id, resource_type_id).aggregate(
        resources=Count("resource_id", distinct=True), **_totals()
    )
    by_resource = utilisation_by("resource", institution_id, start, end, department_id, resource_type_id)
    pending = _scope(
        Booking.objects.filter(institution_id=institution_id, status=BookingStatus.PENDING),
        "resource__",
        department_id,
        resource_type_id,
    ).count()
    return {
        **_metrics(totals),
        "resources": totals["resources"],
        "days": (end - start).days + 1,
        "pending_approvals": pending,
        "avg_turnaround_hours": turnaround_hours(
            _approvals(institution_id, start, end, department_id, resource_type_id)
        ),
        "top_resource": by_resource[0] if by_resource else None,
    }


def idle_capacity_ranking(
    institution_id, start: date, end: date, department_id=None, resource_type_id=None, limit: int = 10
) -> list[dict]:
    """
    Resources ranked by idle hours weighted by acquisition cost — an idle ₹40 lakh
    spectrometer outranks an idle seminar room. Resources without a recorded cost score 0
    and fall back to plain idle hours. Rows:
    ``{resource_id, name, code, type, department, building, acquisition_cost (float|None),
    open_hours, booked_hours, idle_hours, idle_pct, utilisation_pct, idle_cost_score}``
    where ``idle_cost_score`` = idle_hours × acquisition_cost and ``idle_pct`` = idle / open.
    """
    rows = (
        _snapshots(institution_id, start, end, department_id, resource_type_id)
        .values(
            "resource_id",
            "resource__name",
            "resource__code",
            "resource__type__name",
            "resource__department__name",
            "resource__building__name",
            "resource__acquisition_cost",
        )
        .annotate(**_totals())
        .annotate(
            score=ExpressionWrapper(
                F("idle_m") * Coalesce(F("resource__acquisition_cost"), Value(Decimal(0))),
                output_field=DecimalField(max_digits=24, decimal_places=2),
            )
        )
        .order_by("-score", "-idle_m", "resource__name")[:limit]
    )
    out = []
    for r in rows:
        m = _metrics(r)
        cost = r["resource__acquisition_cost"]
        out.append(
            {
                "resource_id": r["resource_id"],
                "name": r["resource__name"],
                "code": r["resource__code"],
                "type": r["resource__type__name"],
                "department": r["resource__department__name"] or UNASSIGNED,
                "building": r["resource__building__name"] or "",
                "acquisition_cost": float(cost) if cost is not None else None,
                "open_hours": m["open_hours"],
                "booked_hours": m["booked_hours"],
                "idle_hours": m["idle_hours"],
                "idle_pct": _pct(r["idle_m"], r["open_m"]),
                "utilisation_pct": m["utilisation_pct"],
                "idle_cost_score": round(float(r["score"]) / 60, 2),
            }
        )
    return out


def heatmap(institution_id, start: date, end: date, department_id=None, resource_type_id=None) -> dict:
    """
    Weekday x hour of booked + class minutes, summed across the range. Aggregated inside
    PostgreSQL by unnesting the 24-slot JSON arrays, so a year of snapshots never reaches Python.

    ``{"rows": [{"weekday": 0..6, "label": "Mon", "minutes": [24 ints], "total": int}] * 7,
    "max": largest cell, "total": sum of all cells}``
    """
    qs = _snapshots(institution_id, start, end, department_id, resource_type_id).values("id")
    sub_sql, params = qs.query.sql_with_params()
    table = UtilisationSnapshot._meta.db_table
    sql = f"""
        SELECT (EXTRACT(ISODOW FROM s.date))::int - 1 AS wd, (h.idx - 1)::int AS hr, SUM(h.val::int) AS minutes
        FROM {table} s
        CROSS JOIN LATERAL jsonb_array_elements_text(s.hourly_booked) WITH ORDINALITY AS h(val, idx)
        WHERE s.id IN ({sub_sql}) AND jsonb_typeof(s.hourly_booked) = 'array'
        GROUP BY 1, 2
    """  # noqa: S608 - table name comes from model meta; values are parameterised
    grid = [[0] * 24 for _ in range(7)]
    with connection.cursor() as cur:
        cur.execute(sql, params)
        for wd, hr, minutes in cur.fetchall():
            if 0 <= hr < 24:
                grid[wd][hr] = int(minutes or 0)
    rows = [{"weekday": i, "label": WEEKDAY_LABELS[i], "minutes": grid[i], "total": sum(grid[i])} for i in range(7)]
    return {"rows": rows, "max": max(max(r) for r in grid), "total": sum(r["total"] for r in rows)}


def no_show_rates(
    institution_id, start: date, end: date, department_id=None, resource_type_id=None, limit: int = 10
) -> dict:
    """
    ``{"overall": {bookings, no_shows, rate_pct},
       "by_user": [{user_id, name, username, vid, bookings, no_shows, rate_pct}],     worst first, no_shows > 0
       "by_resource": [{resource_id, name, bookings, no_shows, rate_pct}]}``         worst first, no_shows > 0
    By-user reads live bookings (snapshots have no user); by-resource reads snapshots.
    """
    lo, hi = _range_bounds(start, end)
    users = (
        _scope(
            Booking.objects.filter(
                institution_id=institution_id,
                status__in=BOOKED_STATUSES,
                period__startswith__gte=lo,
                period__startswith__lt=hi,
            ),
            "resource__",
            department_id,
            resource_type_id,
        )
        .order_by()
        .values("booked_for_id", "booked_for__first_name", "booked_for__last_name", "booked_for__username")
        .annotate(
            vid=F("booked_for__vid"),
            n=Count("id"),
            ns=Count("id", filter=Q(status=BookingStatus.NO_SHOW)),
        )
        .filter(ns__gt=0)
        .order_by("-ns", "n", "booked_for__username")[:limit]
    )
    by_user = [
        {
            "user_id": u["booked_for_id"],
            "name": f"{u['booked_for__first_name']} {u['booked_for__last_name']}".strip() or u["booked_for__username"],
            "username": u["booked_for__username"],
            "vid": u["vid"],
            "bookings": u["n"],
            "no_shows": u["ns"],
            "rate_pct": _pct(u["ns"], u["n"]),
        }
        for u in users
    ]
    snaps = _snapshots(institution_id, start, end, department_id, resource_type_id)
    resources = (
        snaps.values("resource_id", "resource__name")
        .annotate(n=Sum("bookings"), ns=Sum("no_shows"))
        .filter(ns__gt=0)
        .order_by("-ns", "n", "resource__name")[:limit]
    )
    by_resource = [
        {
            "resource_id": r["resource_id"],
            "name": r["resource__name"],
            "bookings": r["n"],
            "no_shows": r["ns"],
            "rate_pct": _pct(r["ns"], r["n"]),
        }
        for r in resources
    ]
    t = snaps.aggregate(n=Sum("bookings", default=0), ns=Sum("no_shows", default=0))
    return {
        "overall": {"bookings": t["n"], "no_shows": t["ns"], "rate_pct": _pct(t["ns"], t["n"])},
        "by_user": by_user,
        "by_resource": by_resource,
    }


def demand_vs_supply(institution_id, start: date, end: date, department_id=None, resource_type_id=None) -> list[dict]:
    """
    Per resource type, most unmet demand first:
    ``{type_id, type, resources, bookings, denied_attempts, demand, denial_rate_pct, utilisation_pct,
    booked_hours, open_hours, needs_capacity}``. ``demand`` = bookings + denied attempts;
    ``denial_rate_pct`` = denied / demand. ``needs_capacity`` is True when at least
    DEMAND_MIN_DENIED requests were refused for lack of supply and either the denial rate is at
    least DEMAND_DENIAL_RATE_PCT or utilisation is at least DEMAND_UTILISATION_PCT.
    """
    out = []
    for r in utilisation_by("type", institution_id, start, end, department_id, resource_type_id):
        demand = r["bookings"] + r["denied_attempts"]
        denial = _pct(r["denied_attempts"], demand)
        out.append(
            {
                "type_id": r["key"],
                "type": r["label"],
                "resources": r["resources"],
                "bookings": r["bookings"],
                "denied_attempts": r["denied_attempts"],
                "demand": demand,
                "denial_rate_pct": denial,
                "utilisation_pct": r["utilisation_pct"],
                "booked_hours": r["booked_hours"],
                "open_hours": r["open_hours"],
                "needs_capacity": r["denied_attempts"] >= DEMAND_MIN_DENIED
                and (denial >= DEMAND_DENIAL_RATE_PCT or r["utilisation_pct"] >= DEMAND_UTILISATION_PCT),
            }
        )
    out.sort(key=lambda r: (-r["needs_capacity"], -r["denied_attempts"], -r["utilisation_pct"], r["type"]))
    return out


def _approvals(institution_id, start, end, department_id=None, resource_type_id=None):
    from apps.approvals.models import Approval

    lo, hi = _range_bounds(start, end)
    qs = Approval.objects.filter(booking__institution_id=institution_id, decided_at__gte=lo, decided_at__lt=hi)
    return _scope(qs, "booking__resource__", department_id, resource_type_id)


def approval_turnaround(institution_id, start: date, end: date, department_id=None, resource_type_id=None) -> dict:
    """
    Request → decision time for approval steps decided in the range (same definition as
    approvals.services.turnaround_hours), plus the live queue:
    ``{avg_hours (float|None), decided, approved, rejected, pending_now, overdue_now,
    by_type: [{type_id, type, avg_hours, decided}]}`` (slowest type first).
    """
    from apps.approvals.models import Approval, Decision
    from apps.approvals.services import turnaround_hours

    decided = _approvals(institution_id, start, end, department_id, resource_type_id).filter(
        decision__in=[Decision.APPROVED, Decision.REJECTED]
    )
    counts = decided.aggregate(
        approved=Count("id", filter=Q(decision=Decision.APPROVED)),
        rejected=Count("id", filter=Q(decision=Decision.REJECTED)),
    )
    by_type = (
        decided.order_by()
        .values("booking__resource__type_id", "booking__resource__type__name")
        .annotate(
            avg=Avg(ExpressionWrapper(F("decided_at") - F("booking__created_at"), output_field=DurationField())),
            n=Count("id"),
        )
    )
    types = [
        {
            "type_id": t["booking__resource__type_id"],
            "type": t["booking__resource__type__name"],
            "avg_hours": round(t["avg"].total_seconds() / 3600, 1) if t["avg"] is not None else None,
            "decided": t["n"],
        }
        for t in by_type
    ]
    types.sort(key=lambda t: (-(t["avg_hours"] or 0), t["type"]))
    queue = _scope(
        Approval.objects.filter(
            booking__institution_id=institution_id,
            decision=Decision.PENDING,
            booking__status=BookingStatus.PENDING,
        ),
        "booking__resource__",
        department_id,
        resource_type_id,
    ).aggregate(pending=Count("id"), overdue=Count("id", filter=Q(due_at__lt=timezone.now())))
    return {
        "avg_hours": turnaround_hours(decided),
        "decided": counts["approved"] + counts["rejected"],
        "approved": counts["approved"],
        "rejected": counts["rejected"],
        "pending_now": queue["pending"],
        "overdue_now": queue["overdue"],
        "by_type": types,
    }


def maintenance_downtime(institution_id, start: date, end: date, department_id=None, resource_type_id=None) -> dict:
    """
    Two views of downtime:
    - ``hours``: wall-clock maintenance time (non-cancelled MaintenanceWindows clipped to the range,
      clipped in SQL with greatest/least on the range bounds);
    - ``lost_open_hours``: bookable opening hours lost to maintenance (from snapshots).

    ``{total_hours, lost_open_hours, windows,
       by_resource: [{resource_id, name, type, hours, windows, lost_open_hours}],     most downtime first
       by_type: [{type_id, type, resources, hours, windows, lost_open_hours}]}``
    """
    from apps.maintenance.models import MaintenanceWindow, WindowStatus

    lo, hi = _range_bounds(start, end)
    clipped = ExpressionWrapper(
        Least(RangeUpper("period"), Value(hi)) - Greatest(RangeLower("period"), Value(lo)),
        output_field=DurationField(),
    )
    windows = _scope(
        MaintenanceWindow.objects.filter(institution_id=institution_id, period__overlap=trange(lo, hi)).exclude(
            status=WindowStatus.CANCELLED
        ),
        "resource__",
        department_id,
        resource_type_id,
    ).order_by()
    snaps = _snapshots(institution_id, start, end, department_id, resource_type_id).filter(maintenance_minutes__gt=0)

    def _hours(td):
        return round(td.total_seconds() / 3600, 1) if td else 0.0

    lost_by_resource = dict(
        snaps.values("resource_id").annotate(m=Sum("maintenance_minutes")).values_list("resource_id", "m")
    )
    lost_by_type = dict(
        snaps.values("resource__type_id").annotate(m=Sum("maintenance_minutes")).values_list("resource__type_id", "m")
    )
    by_resource = [
        {
            "resource_id": r["resource_id"],
            "name": r["resource__name"],
            "type": r["resource__type__name"],
            "hours": _hours(r["t"]),
            "windows": r["n"],
            "lost_open_hours": _h(lost_by_resource.get(r["resource_id"], 0)),
        }
        for r in windows.values("resource_id", "resource__name", "resource__type__name").annotate(
            t=Sum(clipped), n=Count("id")
        )
    ]
    by_resource.sort(key=lambda r: (-r["hours"], r["name"]))
    by_type = [
        {
            "type_id": r["resource__type_id"],
            "type": r["resource__type__name"],
            "resources": r["resources"],
            "hours": _hours(r["t"]),
            "windows": r["n"],
            "lost_open_hours": _h(lost_by_type.get(r["resource__type_id"], 0)),
        }
        for r in windows.values("resource__type_id", "resource__type__name").annotate(
            t=Sum(clipped), n=Count("id"), resources=Count("resource_id", distinct=True)
        )
    ]
    by_type.sort(key=lambda r: (-r["hours"], r["type"]))
    return {
        "total_hours": round(sum(r["hours"] for r in by_type), 1),
        "lost_open_hours": _h(sum(lost_by_type.values())),
        "windows": sum(r["windows"] for r in by_type),
        "by_resource": by_resource,
        "by_type": by_type,
    }


def department_quota_consumption(
    institution_id,
    start: date | None = None,
    end: date | None = None,
    department_id=None,
    resource_type_id=None,
    at=None,
) -> list[dict]:
    """
    Departmental quotas, used vs limit, for the quota period containing ``at`` (default: now,
    or the end of ``end`` when the range lies in the past). Uses the same consumption query the
    booking engine enforces quotas with, so the dashboard can never disagree with a refusal.

    ``[{quota_id, name, department_id, department, department_code, resource_type (str|None), period,
    period_label, window_start, window_end, hours_used, max_hours, hours_pct, bookings_used,
    max_bookings, bookings_pct, pct}]`` — fullest first. ``*_pct`` are ints 0..100 or None when that
    limit is not set; ``pct`` is the larger of the two.
    """
    from apps.bookings.services import consumption
    from apps.rules.models import Quota
    from apps.rules.services import QuotaUse, period_window

    now = timezone.now()
    at = at or (min(now, aware(end, time.max)) if end else now)
    qs = Quota.objects.filter(institution_id=institution_id, active=True, department__isnull=False).select_related(
        "department", "resource_type"
    )
    if department_id is not None:
        qs = qs.filter(department_id=department_id)
    if resource_type_id is not None:
        qs = qs.filter(Q(resource_type__isnull=True) | Q(resource_type_id=resource_type_id))
    out = []
    for q in qs:
        window = period_window(q.period, at)
        minutes, count = consumption(window=window, department_id=q.department_id, resource_type_id=q.resource_type_id)
        use = QuotaUse(q, window, (Decimal(minutes) / Decimal(60)).quantize(Decimal("0.1")), count)
        out.append(
            {
                "quota_id": q.pk,
                "name": q.name,
                "department_id": q.department_id,
                "department": q.department.name,
                "department_code": q.department.code,
                "resource_type": q.resource_type.name if q.resource_type_id else None,
                "period": q.period,
                "period_label": q.get_period_display(),
                "window_start": window[0],
                "window_end": window[1],
                "hours_used": float(use.hours_used),
                "max_hours": float(q.max_hours) if q.max_hours is not None else None,
                "hours_pct": use.hours_pct,
                "bookings_used": count,
                "max_bookings": q.max_bookings,
                "bookings_pct": use.bookings_pct,
                "pct": use.pct,
            }
        )
    out.sort(key=lambda r: (-r["pct"], r["department"], r["name"]))
    return out


def daily_series(institution_id, start: date, end: date, department_id=None, resource_type_id=None) -> list[dict]:
    """
    One row per calendar day in [start, end] (missing days are zeros), oldest first:
    ``{date, open_hours, class_hours, booked_hours, used_hours, bookings, no_shows, cancellations,
    denied_attempts, utilisation_pct}``.
    """
    rows = {
        r["date"]: r
        for r in _snapshots(institution_id, start, end, department_id, resource_type_id)
        .values("date")
        .annotate(**_totals())
    }
    out = []
    d = start
    while d <= end:
        r = rows.get(d)
        m = _metrics(r) if r else None
        out.append(
            {
                "date": d,
                "open_hours": m["open_hours"] if m else 0.0,
                "class_hours": m["class_hours"] if m else 0.0,
                "booked_hours": m["booked_hours"] if m else 0.0,
                "used_hours": m["used_hours"] if m else 0.0,
                "bookings": m["bookings"] if m else 0,
                "no_shows": m["no_shows"] if m else 0,
                "cancellations": m["cancellations"] if m else 0,
                "denied_attempts": m["denied_attempts"] if m else 0,
                "utilisation_pct": m["utilisation_pct"] if m else 0.0,
            }
        )
        d += timedelta(days=1)
    return out
