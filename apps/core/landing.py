"""
The public landing page's data: everything it shows about the campus comes from the live database
or from the code that enforces it, never from copy written to look good.

* `ledger_preview()` is a real day of the booking ledger (the same `availability.board` the live
  board uses), read as an anonymous visitor and reduced to *kinds* of claim: no names, no booking
  titles, no course codes. Cached for five minutes.
* `catalogue()` is the bookable resource types with their real counts and curated photographs.
* `role_matrix()` is derived from `ROLE_PERMISSIONS` and `MFA_REQUIRED_ROLES`, so the page cannot
  promise a role something the server would refuse it.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.db.models import Count, Q
from django.templatetags.static import static
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.permissions import ROLE_PERMISSIONS
from apps.bookings import availability
from apps.catalogue.models import Building, Resource, ResourceStatus, ResourceType
from apps.core.models import default_institution_id

CACHE_SECONDS = 300
WINDOW = (time(8, 0), time(20, 0))
ROWS = 6

# What each claim on the ledger is called on the page, in legend order.
KIND_LABELS = {
    availability.BOOKED: "Booked",
    availability.PENDING: "Pending approval",
    availability.CLASS: "Timetabled class",
    availability.MAINTENANCE: "Maintenance",
    availability.BLACKOUT: "Blackout",
}


def _pos(t: datetime, lo: datetime, hi: datetime) -> float:
    total = (hi - lo).total_seconds()
    return max(0.0, min(100.0, (t - lo).total_seconds() / total * 100))


def _row(resource, sched, lo, hi) -> dict:
    segments = []
    cursor = lo
    for o, c in sorted(sched.intervals):  # time outside opening hours
        if o > cursor:
            segments.append(("closed", cursor, o))
        cursor = max(cursor, c)
    if cursor < hi:
        segments.append(("closed", cursor, hi))
    for b in sched.blocks:
        if b.kind in KIND_LABELS:
            segments.append((b.kind, b.start, b.end))
    out = []
    for kind, start, end in segments:
        left, right = _pos(start, lo, hi), _pos(end, lo, hi)
        if right - left > 0.05:
            s, e = timezone.localtime(start), timezone.localtime(end)
            out.append(
                {
                    "kind": kind,
                    "left": round(left, 3),
                    "width": round(right - left, 3),
                    "label": f"{s:%H:%M}–{e:%H:%M} {KIND_LABELS.get(kind, 'Closed')}",
                }
            )
    out.sort(key=lambda s: s["left"])
    return {
        "name": resource.name,
        "type": resource.type.name,
        "building": resource.building.name if resource.building_id else "",
        "art": resource.art,
        "segments": out,
        "kinds": sorted({s["kind"] for s in out if s["kind"] != "closed"}),
    }


def _pick(rows: list[dict]) -> list[dict]:
    """Up to six rows: the rarest kinds of claim first (so a maintenance window or a blackout is
    shown when the day has one), then the busiest rows, one resource type per row where possible."""
    busiest = sorted(rows, key=lambda r: (len(r["kinds"]), len(r["segments"])), reverse=True)
    seen = Counter(k for r in rows for k in r["kinds"])
    picked, types = [], set()

    def take(r):
        picked.append(r)
        types.add(r["type"])

    for kind in sorted(seen, key=seen.get):
        if len(picked) < ROWS and not any(kind in r["kinds"] for r in picked):
            options = [r for r in busiest if kind in r["kinds"] and r not in picked]
            fresh = [r for r in options if r["type"] not in types]
            if fresh or options:
                take((fresh or options)[0])
    for r in busiest:
        if len(picked) < ROWS and r not in picked and r["type"] not in types and r["kinds"]:
            take(r)
    return picked


NOUNS = {
    availability.CLASS: ("timetabled class", "timetabled classes"),
    availability.BOOKED: ("booking", "bookings"),
    availability.PENDING: ("request pending approval", "requests pending approval"),
    availability.MAINTENANCE: ("maintenance window", "maintenance windows"),
    availability.BLACKOUT: ("blackout", "blackouts"),
}


def _summary(totals: Counter) -> str:
    """'70 timetabled classes, 44 bookings and 1 maintenance window'."""
    parts = [f"{totals[k]} {NOUNS[k][totals[k] != 1]}" for k in NOUNS if totals[k]]
    if len(parts) < 2:
        return parts[0] if parts else "no claims"
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _day_preview(resources, d: date, now) -> dict:
    tz = timezone.get_current_timezone()
    lo = timezone.make_aware(datetime.combine(d, WINDOW[0]), tz)
    hi = timezone.make_aware(datetime.combine(d, WINDOW[1]), tz)
    board = availability.board(resources, d, AnonymousUser(), now=now, window=WINDOW)
    totals = Counter(b.kind for _, sched in board for b in sched.blocks if b.kind in KIND_LABELS)
    rows = [_row(r, sched, lo, hi) for r, sched in board if sched.intervals]
    picked = _pick(rows)
    return {
        "day": d,
        "is_today": d == timezone.localdate(now),
        "rows": picked,
        "kinds": sorted({k for r in picked for k in r["kinds"]}, key=list(KIND_LABELS).index),
        "summary": _summary(totals),
        "resources": len(board),
        "now_pos": round(_pos(now, lo, hi), 3) if lo <= now <= hi else None,
        "hours": [
            {"label": f"{h:02d}:00", "left": round((h - WINDOW[0].hour) / (WINDOW[1].hour - WINDOW[0].hour) * 100, 3)}
            for h in range(WINDOW[0].hour, WINDOW[1].hour + 1, 3)
        ],
    }


def _bookable():
    return (
        Resource.objects.filter(institution_id=default_institution_id(), status=ResourceStatus.ACTIVE, is_bookable=True)
        .select_related("type", "building")
        .order_by("type__sort_order", "name")
    )


def ledger_preview(now=None) -> dict | None:
    """The first day from today, within a week, whose ledger shows at least three kinds of claim
    (otherwise the busiest of those days). None when nothing is bookable yet."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    key = f"landing:ledger:{today.isoformat()}:{now.hour}:{now.minute // 5}"
    best = cache.get(key)
    if best is None:
        best = _busiest_week_day(today, now)
        cache.set(key, best or {}, CACHE_SECONDS)
    if not best:
        return None
    # Photo URLs carry the static manifest's hash, so they are resolved per request, never cached.
    return {**best, "rows": [{**r, "photo": photo_for(r["art"])} for r in best["rows"]]}


def _busiest_week_day(today, now) -> dict | None:
    resources = list(_bookable())
    best = None
    if resources:
        for k in range(7):
            p = _day_preview(resources, today + timedelta(days=k), now)
            if p["rows"] and (best is None or len(p["kinds"]) > len(best["kinds"])):
                best = p
            if best and len(best["kinds"]) >= 3:
                break
    return best


def photo_for(art: str, size: str = "sm") -> str | None:
    if not art:
        return None
    path = f"img/resources/{art}{'-sm' if size == 'sm' else ''}.webp"
    return static(path) if finders.find(path) else None


def catalogue() -> dict:
    key = "landing:catalogue"
    data = cache.get(key)
    if data is None:
        data = _catalogue()
        cache.set(key, data, CACHE_SECONDS)
    return {
        **data,
        "types": [{**t, "photo": photo_for(t["art"], "lg"), "photo_sm": photo_for(t["art"])} for t in data["types"]],
    }


def _catalogue() -> dict:
    inst = default_institution_id()
    live = Q(resources__status=ResourceStatus.ACTIVE, resources__is_bookable=True)
    types = list(
        ResourceType.objects.filter(institution_id=inst)
        .annotate(n=Count("resources", filter=live))
        .filter(n__gt=0)
        .order_by("sort_order", "name")
    )
    arts = Counter()
    for type_id, art in _bookable().exclude(art="").values_list("type_id", "art"):
        arts[(type_id, art)] += 1
    out = []
    for t in types:
        art = max(((a, n) for (tid, a), n in arts.items() if tid == t.pk), key=lambda x: x[1], default=(None, 0))[0]
        out.append(
            {
                "code": t.code,
                "name": t.plural or t.name,
                "singular": t.name,
                "category": t.get_category_display(),
                "icon": t.icon,
                "count": t.n,
                "art": art,
            }
        )
    return {
        "types": out,
        "resources": sum(t["count"] for t in out),
        "buildings": Building.objects.filter(institution_id=inst)
        .filter(resources__status=ResourceStatus.ACTIVE, resources__is_bookable=True)
        .distinct()
        .count(),
    }


# ── Roles ────────────────────────────────────────────────────────────────────────────────────
# Columns: faculty and staff hold identical capabilities, so they share one.
ROLE_COLUMNS = [
    ("student", "Student", [Role.STUDENT], "Their own bookings"),
    ("faculty", "Faculty & staff", [Role.FACULTY, Role.STAFF], "Their bookings, and bookings for a class"),
    ("custodian", "Resource custodian", [Role.CUSTODIAN], "The resources they look after"),
    ("dept_head", "Head of department", [Role.DEPT_HEAD], "Their department's resources"),
    ("facility_manager", "Facility manager", [Role.FACILITY_MANAGER], "The whole campus"),
    ("admin", "Administrator", [Role.ADMIN], "The whole campus, plus people and roles"),
]

# Capabilities whose subject only arises from a Celery Beat sweep (no-shows and booking pauses are
# recorded by checkins.sweep_no_shows). Production runs no Beat service today, so the public page
# does not advertise them; the capability and its pages are unchanged.
NEEDS_SCHEDULER = {"forgive_no_shows"}

CAPABILITIES = [
    ("book_resources", "Book rooms, labs, courts and equipment"),
    ("book_recurring", "Weekly recurring bookings"),
    ("book_on_behalf", "Book for a class or group"),
    ("approve_bookings", "Approve requests"),
    ("manage_resources", "Manage resources and door QR codes"),
    ("manage_maintenance", "Schedule maintenance, handle breakdowns"),
    ("manage_inventory", "Track stock and consumables"),
    ("view_department_analytics", "Department insights"),
    ("view_campus_analytics", "Campus-wide insights"),
    ("configure_policy", "Booking rules, hours and blackouts"),
    ("manage_timetable", "Import and publish the timetable"),
    ("view_audit_log", "Read the audit log"),
    ("manage_users", "Add people and change roles"),
]


def role_matrix() -> dict:
    columns = []
    for key, label, roles, scope in ROLE_COLUMNS:
        caps = set.intersection(*(ROLE_PERMISSIONS[r] for r in roles))
        columns.append(
            {
                "key": key,
                "label": label,
                "scope": scope,
                "caps": caps,
                "mfa": all(r in settings.MFA_REQUIRED_ROLES for r in roles),
                "can": [text for code, text in CAPABILITIES if code in caps],
            }
        )
    rows = [{"label": text, "cells": [code in c["caps"] for c in columns]} for code, text in CAPABILITIES]
    rows.append({"label": "Two-factor sign-in required", "cells": [c["mfa"] for c in columns], "mfa": True})
    return {"columns": columns, "rows": rows}
