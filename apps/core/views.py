"""Home: task-first — "I need a resource at a particular time" — not a dashboard of widgets."""

from datetime import time, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.permissions import has_cap
from apps.bookings import availability
from apps.bookings.models import Booking, BookingStatus
from apps.catalogue.models import Resource, ResourceType, SavedResource
from apps.checkins.services import active_restriction, checkin_state
from apps.core.timeutil import ceil_to


def root(request):
    return redirect("core:home" if request.user.is_authenticated else "accounts:login")


def greeting(now):
    h = timezone.localtime(now).hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"


def time_choices(start=time(6, 0), end=time(22, 0), step=30):
    out, t = [], timezone.datetime.combine(timezone.localdate(), start)
    stop = timezone.datetime.combine(timezone.localdate(), end)
    while t <= stop:
        out.append(t.strftime("%H:%M"))
        t += timedelta(minutes=step)
    return out


@login_required
def home(request):
    user = request.user
    now = timezone.now()
    today = timezone.localdate()

    upcoming = list(
        Booking.objects.filter(
            booked_for=user,
            status__in=[BookingStatus.PENDING, BookingStatus.APPROVED, BookingStatus.CHECKED_IN],
            period__endswith__gt=now,
        )
        .select_related("resource__type", "resource__building")
        .order_by("period")[:4]
    )
    next_booking = upcoming[0] if upcoming else None
    next_state = checkin_state(next_booking, now) if next_booking else None

    # "Free right now": resources free for the next hour, starting with the user's own block.
    start = ceil_to(now, 30)
    end = start + timedelta(hours=1)
    candidates = Resource.objects.filter(
        institution_id=user.institution_id, status="active", is_bookable=True
    ).select_related("type", "building")
    if user.role == "student":
        candidates = candidates.filter(Q(type__allowed_roles=[]) | Q(type__allowed_roles__contains=[user.role]))
    busy = availability.busy_resource_ids(list(candidates.values_list("pk", flat=True)), start, end)
    free_now = [
        r for r in candidates.exclude(pk__in=busy).filter(type__category__in=["space", "lab"]) if _open(r, start, end)
    ]
    home_building = (
        Booking.objects.filter(booked_for=user)
        .values("resource__building_id")
        .annotate(n=Count("id"))
        .order_by("-n")
        .first()
    )
    if home_building:
        free_now.sort(key=lambda r: (r.building_id != home_building["resource__building_id"], r.capacity))
    free_now = free_now[:6]
    free_rows = availability.board(free_now, today, user, now=now)

    # "Your usual spots": starred first, then most booked.
    saved_ids = list(SavedResource.objects.filter(user=user).values_list("resource_id", flat=True))
    frequent = list(
        Booking.objects.filter(booked_for=user)
        .values_list("resource_id", flat=True)
        .annotate(n=Count("id"))
        .order_by("-n")[:6]
    )
    usual_ids = list(dict.fromkeys(saved_ids + frequent))[:4]
    usual = sorted(
        Resource.objects.filter(pk__in=usual_ids).select_related("type", "building"),
        key=lambda r: usual_ids.index(r.pk),
    )
    usual_rows = availability.board(usual, today, user, now=now)

    types = (
        ResourceType.objects.filter(institution_id=user.institution_id).annotate(n=Count("resources")).filter(n__gt=0)
    )
    ctx = {
        "greeting": greeting(now),
        "next_booking": next_booking,
        "next_state": next_state,
        "more_upcoming": upcoming[1:],
        "free_rows": free_rows,
        "free_from": start,
        "usual_rows": usual_rows,
        "saved_ids": set(saved_ids),
        "types": types,
        "times": time_choices(),
        "default_from": timezone.localtime(ceil_to(now, 30)).strftime("%H:%M")
        if timezone.localtime(now).hour < 21
        else "09:00",
        "default_to": timezone.localtime(ceil_to(now, 30) + timedelta(hours=1)).strftime("%H:%M")
        if timezone.localtime(now).hour < 21
        else "10:00",
        "restriction": active_restriction(user, now),
        "is_staff_side": has_cap(user, "approve_bookings")
        or has_cap(user, "manage_resources")
        or has_cap(user, "view_department_analytics"),
        "today": today,
        "tomorrow": today + timedelta(days=1),
    }
    if ctx["is_staff_side"]:
        ctx["desk"] = _desk(user)
    return render(request, "core/home.html", ctx)


def _open(resource, start, end):
    from apps.rules.services import opening_intervals

    return any(o <= start and end <= c for o, c in opening_intervals(resource, timezone.localtime(start).date()))


def _desk(user):
    """A compact 'what needs you' strip for staff roles on the home screen."""
    from apps.approvals.services import queue_for
    from apps.checkins.models import NoShow
    from apps.maintenance.models import BreakdownReport, ReportStatus

    desk = {}
    if has_cap(user, "approve_bookings"):
        desk["approvals"] = queue_for(user).count()
    if has_cap(user, "manage_maintenance"):
        qs = BreakdownReport.objects.filter(institution_id=user.institution_id, status=ReportStatus.OPEN)
        if user.role == "custodian":
            qs = qs.filter(resource__custodians__user=user)
        desk["breakdowns"] = qs.count()
    if has_cap(user, "forgive_no_shows"):
        desk["no_shows_today"] = NoShow.objects.filter(
            institution_id=user.institution_id, detected_at__date=timezone.localdate()
        ).count()
    live = Booking.objects.filter(institution_id=user.institution_id, status=BookingStatus.CHECKED_IN)
    if user.role == "custodian":
        live = live.filter(resource__custodians__user=user)
    desk["in_use"] = live.count()
    return desk
