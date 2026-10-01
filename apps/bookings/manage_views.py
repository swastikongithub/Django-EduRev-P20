"""
Live booking board (/manage/board/): every resource in the user's scope on one shared
07:00–22:00 timeline, plus what is in progress and about to start, with custodian check-in
and check-out actions. The body re-renders itself every 60 s through htmx.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, time, timedelta

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

from apps.catalogue.models import Building, ResourceType
from apps.core.manage_views import staff_required
from apps.core.scope import managed_resources, scope_label
from apps.core.timeutil import aware, trange

from .availability import board as board_rows
from .models import HOLDING_STATUSES, Booking, BookingStatus

ROWS_PER_PAGE = 40
START_H, END_H = 7, 22
SOON = timedelta(minutes=90)


def _date(v, default):
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        return default


def _pct(dt, day):
    lo = aware(day, time(START_H))
    total = (END_H - START_H) * 3600
    return max(0.0, min(100.0, (dt - lo).total_seconds() / total * 100))


def checkin_states(bookings, now):
    """checkin_state() for many bookings, loading each resource's policy once."""
    from apps.checkins.services import checkin_window
    from apps.rules.services import policy_for

    policies = {}
    out = {}
    for b in bookings:
        if b.status == BookingStatus.CHECKED_IN:
            out[b.pk] = {"state": "in_use"}
            continue
        if b.status == BookingStatus.PENDING:
            out[b.pk] = {"state": "pending"}
            continue
        if b.status != BookingStatus.APPROVED:
            out[b.pk] = {"state": "inactive"}
            continue
        if not b.requires_checkin:
            out[b.pk] = {"state": "not_required"}
            continue
        if b.resource_id not in policies:
            policies[b.resource_id] = policy_for(b.resource)
        opens, closes = checkin_window(b, policies[b.resource_id])
        if now < opens:
            out[b.pk] = {"state": "not_yet", "opens": opens, "closes": closes}
        elif now <= closes:
            out[b.pk] = {"state": "open", "opens": opens, "closes": closes}
        else:
            out[b.pk] = {"state": "missed", "closes": closes}
    return out


def row_status(r, sched, bookings, now, is_today):
    """One short phrase for the row label: what the resource is doing right now."""
    if r.status != "active":
        return {"tone": "danger", "icon": "wrench", "text": "Out of service"}
    if not is_today:
        n = len([b for b in bookings if b.status in HOLDING_STATUSES])
        return {"tone": "plain", "icon": "calendar-check", "text": f"{n} booking{'s' if n != 1 else ''}"} if n else None
    for b in bookings:
        if b.start <= now < b.end:
            if b.status == BookingStatus.CHECKED_IN:
                return {"tone": "live", "icon": "zap", "text": f"In use until {timezone.localtime(b.end):%H:%M}"}
            if b.status == BookingStatus.APPROVED and b.requires_checkin and now > b.checkin_deadline:
                return {"tone": "danger", "icon": "ban", "text": "Missed check-in"}
            if b.status == BookingStatus.APPROVED:
                return {"tone": "pending", "icon": "hourglass", "text": "Waiting for check-in"}
    for blk in sched.blocks if sched else []:
        if blk.start <= now < blk.end and blk.kind in ("class", "maintenance", "blackout"):
            label = {"class": "Class", "maintenance": "Maintenance", "blackout": "Blackout"}[blk.kind]
            return {"tone": "class" if blk.kind == "class" else "warn", "icon": "clock",
                    "text": f"{label} until {timezone.localtime(blk.end):%H:%M}"}
    if sched and not any(o <= now < c for o, c in sched.intervals):
        return {"tone": "plain", "icon": "circle-pause", "text": "Closed now"}
    nxt = min((blk.start for blk in (sched.blocks if sched else []) if blk.start > now), default=None)
    if nxt and timezone.localtime(nxt).date() == timezone.localtime(now).date():
        return {"tone": "success", "icon": "circle-check", "text": f"Free until {timezone.localtime(nxt):%H:%M}"}
    return {"tone": "success", "icon": "circle-check", "text": "Free for the rest of the day"}


@staff_required("manage_resources", "approve_bookings")
def board(request):
    user = request.user
    now = timezone.now()
    today = timezone.localdate()
    day = _date(request.GET.get("date"), today)
    is_today = day == today

    scope = managed_resources(user)
    types = ResourceType.objects.filter(pk__in=scope.values("type_id")).order_by("sort_order", "name")
    buildings = Building.objects.filter(pk__in=scope.values("building_id")).order_by("code")

    qs = scope.select_related("type", "building")
    t_code, b_code, q = request.GET.get("type", ""), request.GET.get("building", ""), request.GET.get("q", "").strip()
    if t_code:
        qs = qs.filter(type__code=t_code)
    if b_code:
        qs = qs.filter(building__code=b_code)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(room__icontains=q))
    page = Paginator(qs, ROWS_PER_PAGE).get_page(request.GET.get("page"))
    resources = list(page.object_list)

    rows = board_rows(resources, day, user, now=now, window=(time(START_H), time(END_H)))
    day_lo, day_hi = aware(day, time.min), aware(day + timedelta(days=1), time.min)
    day_bookings = defaultdict(list)
    for b in Booking.objects.filter(
        resource_id__in=[r.pk for r in resources], period__overlap=trange(day_lo, day_hi), status__in=HOLDING_STATUSES
    ).order_by("period"):
        day_bookings[b.resource_id].append(b)

    board = [
        {"r": r, "sched": sched, "status": row_status(r, sched, day_bookings[r.pk], now, is_today)}
        for r, sched in rows
    ]

    # Side list: whole filtered scope, not just this page of rows.
    in_scope = qs.values("pk")
    side = Booking.objects.filter(resource_id__in=in_scope).select_related(
        "resource__type", "resource__building", "booked_for"
    )
    if is_today:
        in_progress = list(side.filter(status=BookingStatus.CHECKED_IN).order_by("period")[:20])
        soon = list(
            side.filter(
                status__in=[BookingStatus.APPROVED, BookingStatus.PENDING],
                period__startswith__lte=now + SOON,
                period__endswith__gt=now,
            ).order_by("period")[:20]
        )
        day_list = []
    else:
        in_progress, soon = [], []
        shown = (*HOLDING_STATUSES, BookingStatus.COMPLETED, BookingStatus.NO_SHOW)
        day_list = list(side.filter(status__in=shown, period__overlap=trange(day_lo, day_hi)).order_by("period")[:40])
    states = checkin_states(in_progress + soon + day_list, now)
    params = {k: v for k, v in request.GET.items() if k in ("type", "building", "q") and v}

    def url_for(**extra):
        p = {**params, **{k: v for k, v in extra.items() if v}}
        return reverse("manage:board") + (("?" + urlencode(p)) if p else "")

    here = url_for(date=day.isoformat() if not is_today else "", page=page.number if page.number > 1 else "")
    ticks = [{"h": f"{h:02d}", "left": (h - START_H) / (END_H - START_H) * 100} for h in range(START_H, END_H + 1)]
    ctx = {
        "day": day,
        "is_today": is_today,
        "now": now,
        "now_pct": _pct(now, day) if is_today and aware(day, time(START_H)) <= now <= aware(day, time(END_H)) else None,
        "rows": board,
        "page": page,
        "total": page.paginator.count,
        "scope_total": scope.count() if (t_code or b_code or q) else page.paginator.count,
        "types": types,
        "buildings": buildings,
        "t_code": t_code,
        "b_code": b_code,
        "q": q,
        "ticks": ticks,
        "in_progress": [(b, states[b.pk]) for b in in_progress],
        "soon": [(b, states[b.pk]) for b in soon],
        "day_list": [(b, states[b.pk]) for b in day_list],
        "scope_label": scope_label(user),
        "prev_url": url_for(date=(day - timedelta(days=1)).isoformat()),
        "next_url": url_for(date=(day + timedelta(days=1)).isoformat()),
        "today_url": url_for(),
        "is_past": day < today,
        "clear_url": reverse("manage:board") + ("" if is_today else f"?date={day.isoformat()}"),
        "refresh_url": here,
        "here": here,
        "page_prev": url_for(date=day.isoformat() if not is_today else "", page=page.previous_page_number())
        if page.has_previous() else "",
        "page_next": url_for(date=day.isoformat() if not is_today else "", page=page.next_page_number())
        if page.has_next() else "",
    }
    template = "manage/_board_body.html" if request.headers.get("HX-Request") else "manage/board.html"
    return render(request, template, ctx)
