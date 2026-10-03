"""
Console landing (/manage/): "today" for the user's scope — the numbers that matter right now,
a short list of things that need this person, and a compact slice of the live board.
Scope: custodian -> their resources; dept_head -> their department; facility/admin -> campus.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import time, timedelta

from django.db.models import F
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.permissions import has_cap, is_campus_wide
from apps.bookings.models import HOLDING_STATUSES, Booking, BookingStatus
from apps.core.manage_views import staff_required
from apps.core.onboarding import setup_checklist
from apps.core.scope import managed_resources, resource_q, scope_label
from apps.core.timeutil import aware, trange

PREVIEW_ROWS = 8
SOON = timedelta(hours=1)


def _title(user):
    if is_campus_wide(user):
        return "Today on campus"
    if user.role == "dept_head" and user.department_id:
        return f"Today in {user.department.code or user.department.name}"
    return "Today at your resources"


def _approvals(user, now, needs):
    from apps.approvals.services import queue_for

    q = queue_for(user)
    waiting = q.count()
    overdue = q.filter(due_at__lt=now).count()
    if overdue:
        needs.append(
            {
                "tone": "danger",
                "icon": "timer",
                "url": reverse("manage:approvals") + "?overdue=1",
                "title": f"{overdue} request{'s are' if overdue != 1 else ' is'} past the review deadline",
                "text": "The requester is still waiting. Decide now or the slot expires at its start time.",
                "cta": "Review",
            }
        )
    if waiting - overdue > 0:
        nxt = q.filter(due_at__gte=now).order_by("due_at").select_related("booking__booked_for").first()
        text = "Each slot is held for the requester until you decide."
        if nxt:
            due = timezone.localtime(nxt.due_at)
            when = f"{due:%H:%M}" if due.date() == timezone.localdate() else f"{due:%a %d %b}, {due:%H:%M}"
            text = f"Next due {when}, from {nxt.booking.booked_for.display_name}."
        n = waiting - overdue
        needs.append(
            {
                "tone": "pending",
                "icon": "list-checks",
                "url": reverse("manage:approvals"),
                "title": f"{n} request{'s' if n != 1 else ''} waiting for you",
                "text": text,
                "cta": "Open queue",
            }
        )
    return waiting


def _breakdowns(user, needs):
    from apps.maintenance.models import BreakdownReport, ReportStatus, Severity

    qs = (
        BreakdownReport.objects.filter(institution_id=user.institution_id)
        .filter(resource_q(user))
        .exclude(status=ReportStatus.RESOLVED)
        .select_related("resource")
        .order_by("-created_at")
    )
    reports = list(qs[:50])
    for r in [r for r in reports if r.severity == Severity.CRITICAL][:3]:
        needs.append(
            {
                "tone": "danger",
                "icon": "flame",
                "url": reverse("manage:maintenance"),
                "title": f"{r.resource.name}: {r.summary}",
                "text": "Critical report. The resource is out of service until it's resolved.",
                "cta": "Handle",
            }
        )
    fresh = [r for r in reports if r.status == ReportStatus.OPEN and r.severity != Severity.CRITICAL]
    if fresh:
        needs.append(
            {
                "tone": "warn",
                "icon": "triangle-alert",
                "url": reverse("manage:maintenance"),
                "title": f"{len(fresh)} new breakdown report{'s' if len(fresh) != 1 else ''}",
                "text": f"Latest: {fresh[0].summary} ({fresh[0].resource.name}).",
                "cta": "Acknowledge",
            }
        )
    return qs.count()


def _low_stock(user, needs):
    from apps.inventory.models import InventoryItem

    qs = InventoryItem.objects.filter(institution_id=user.institution_id, quantity_available__lte=F("reorder_level"))
    if not is_campus_wide(user):
        qs = qs.filter(resource_id__in=managed_resources(user).values("pk"))
    items = list(qs.order_by("quantity_available", "name")[:3])
    n = qs.count()
    if n:
        names = ", ".join(f"{i.name} ({i.quantity_available} {i.unit})" for i in items)
        needs.append(
            {
                "tone": "warn",
                "icon": "package",
                "url": reverse("manage:inventory") + "?low=1",
                "title": f"{n} item{'s' if n != 1 else ''} low on stock",
                "text": names + (" and more." if n > len(items) else "."),
                "cta": "Restock",
            }
        )
    return n


@staff_required()
def home(request):
    from apps.bookings.availability import board
    from apps.bookings.manage_views import checkin_states, row_status

    user, now = request.user, timezone.now()
    today = timezone.localdate()
    rq = resource_q(user)
    bookings = Booking.objects.filter(institution_id=user.institution_id).filter(rq)
    resources = managed_resources(user)
    can_board = has_cap(user, "manage_resources") or has_cap(user, "approve_bookings")
    needs = []
    kpis = []

    live = list(
        bookings.filter(status=BookingStatus.CHECKED_IN)
        .select_related("resource__type", "booked_for")
        .order_by("period")[:12]
    )
    in_use = bookings.filter(status=BookingStatus.CHECKED_IN).count()
    soon_qs = bookings.filter(
        status__in=[BookingStatus.APPROVED, BookingStatus.PENDING],
        period__startswith__lt=now + SOON,
        period__endswith__gt=now,
    )
    soon = list(soon_qs.select_related("resource__type", "booked_for").order_by("period")[:12])
    starting = soon_qs.filter(period__startswith__gte=now).count()
    states = checkin_states(live + soon, now)
    waiting_checkin = [b for b in soon if states[b.pk]["state"] == "open"]
    missed = [b for b in soon if states[b.pk]["state"] == "missed"]
    if waiting_checkin and can_board:
        n = len(waiting_checkin)
        needs.append(
            {
                "tone": "info",
                "icon": "user-round-check",
                "url": reverse("manage:board"),
                "title": f"{n} booking{'s' if n != 1 else ''} in the check-in window",
                "text": "If they're at the door with a pass, you can check them in from the board.",
                "cta": "Open board",
            }
        )

    board_url = reverse("manage:board") if can_board else None
    kpis.append(
        {"label": "In use now", "icon": "zap", "value": in_use, "url": board_url, "note": "checked in right now"}
    )
    kpis.append(
        {
            "label": "Starting within the hour",
            "icon": "clock",
            "value": starting,
            "url": board_url,
            "note": f"{len(missed)} missed check-in" if missed else "confirmed or awaiting approval",
        }
    )
    if has_cap(user, "approve_bookings"):
        waiting = _approvals(user, now, needs)
        kpis.append(
            {
                "label": "Waiting for you",
                "icon": "list-checks",
                "value": waiting,
                "url": reverse("manage:approvals"),
                "note": "approval requests",
                "alert": waiting > 0,
            }
        )
    if has_cap(user, "manage_maintenance"):
        n = _breakdowns(user, needs)
        kpis.append(
            {
                "label": "Open breakdowns",
                "icon": "wrench",
                "value": n,
                "url": reverse("manage:maintenance"),
                "note": "reported, not yet resolved",
                "alert": n > 0,
            }
        )
        _maintenance_today(user, today, needs)
    if has_cap(user, "manage_inventory"):
        n = _low_stock(user, needs)
        kpis.append(
            {
                "label": "Low stock",
                "icon": "package",
                "value": n,
                "url": reverse("manage:inventory") + "?low=1",
                "note": "at or under reorder level",
                "alert": n > 0,
            }
        )
    if has_cap(user, "forgive_no_shows"):
        from apps.checkins.models import NoShow

        n = NoShow.objects.filter(institution_id=user.institution_id, detected_at__date=today).filter(rq).count()
        kpis.append(
            {
                "label": "No-shows today",
                "icon": "ban",
                "value": n,
                "url": reverse("manage:no_shows"),
                "note": "released after the grace period",
            }
        )

    order = {"danger": 0, "warn": 1, "pending": 2, "info": 3}
    needs.sort(key=lambda x: order.get(x["tone"], 9))

    # Board preview: resources with something happening now or soon first, then the rest.
    preview = []
    if can_board:
        busy_ids = list(dict.fromkeys([b.resource_id for b in live] + [b.resource_id for b in soon]))
        picked = list(resources.filter(pk__in=busy_ids[:PREVIEW_ROWS]).select_related("type", "building"))
        if len(picked) < PREVIEW_ROWS:
            picked += list(
                resources.exclude(pk__in=busy_ids).select_related("type", "building")[: PREVIEW_ROWS - len(picked)]
            )
        day_bookings = defaultdict(list)
        lo = aware(today, time.min)
        for b in Booking.objects.filter(
            resource_id__in=[r.pk for r in picked],
            status__in=HOLDING_STATUSES,
            period__overlap=trange(lo, lo + timedelta(days=1)),
        ).order_by("period"):
            day_bookings[b.resource_id].append(b)
        rank = {rid: i for i, rid in enumerate(busy_ids)}
        rows = board(picked, today, user, now=now, window=(time(7), time(22)))
        rows.sort(key=lambda rs: rank.get(rs[0].pk, len(rank)))
        preview = [{"r": r, "sched": s, "status": row_status(r, s, day_bookings[r.pk], now, True)} for r, s in rows]

    ctx = {
        "title": _title(user),
        "scope_label": scope_label(user),
        "resource_count": resources.count(),
        "campus_wide": is_campus_wide(user),
        "checklist": setup_checklist(user) if has_cap(user, "configure_policy") else None,
        "kpis": kpis,
        "needs": needs,
        "preview": preview,
        "can_board": can_board,
        "live": [(b, states[b.pk]) for b in live],
        "soon": [(b, states[b.pk]) for b in soon],
        "here": reverse("manage:home"),
        "now": now,
        "today": today,
    }
    return render(request, "manage/home.html", ctx)


def _maintenance_today(user, today, needs):
    from apps.maintenance.models import MaintenanceWindow, WindowStatus

    lo = aware(today, time.min)
    windows = list(
        MaintenanceWindow.objects.filter(
            institution_id=user.institution_id, status__in=[WindowStatus.SCHEDULED, WindowStatus.IN_PROGRESS]
        )
        .filter(resource_q(user))
        .filter(period__overlap=trange(lo, lo + timedelta(days=1)))
        .select_related("resource")
        .order_by("period")[:3]
    )
    for w in windows:
        s, e = timezone.localtime(w.start), timezone.localtime(w.end)
        span = f"{s:%H:%M}–{e:%H:%M}" if e.date() == s.date() else f"{s:%H:%M} until {e:%a %H:%M}"
        needs.append(
            {
                "tone": "info",
                "icon": "wrench",
                "url": reverse("manage:maintenance"),
                "title": f"Maintenance today: {w.title}",
                "text": f"{w.resource.name}, {span}.",
                "cta": "Details",
            }
        )
