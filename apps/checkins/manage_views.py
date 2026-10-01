"""
No-show monitor (/manage/no-shows/): what was released because nobody checked in, who is
paused because of it, and the two overrides — forgive a no-show, lift a pause. Custodians see
their own resources; facility managers and admins see the campus.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import is_campus_wide
from apps.bookings.models import Booking, BookingStatus
from apps.core.errors import DomainError
from apps.core.http import safe_next
from apps.core.manage_views import staff_required
from apps.core.scope import resource_q, scope_label

from . import services
from .models import NoShow, Restriction

PER_PAGE = 40
RANGES = (7, 30, 90)
RESTRICTION_LOOKBACK = timedelta(days=90)


def _no_shows(user):
    return NoShow.objects.filter(institution_id=user.institution_id).filter(resource_q(user))


def _restrictions(user, now):
    """Active pauses. Outside campus-wide roles: only people who missed a booking on your resources."""
    qs = Restriction.objects.filter(
        institution_id=user.institution_id, starts_at__lte=now, ends_at__gt=now, lifted_at__isnull=True
    )
    if not is_campus_wide(user):
        qs = qs.filter(user_id__in=_no_shows(user).filter(detected_at__gte=now - RESTRICTION_LOOKBACK).values("user_id"))
    return qs


@staff_required("forgive_no_shows")
def no_shows(request):
    user, now = request.user, timezone.now()
    base = _no_shows(user)
    week_ago = now - timedelta(days=7)
    week = base.filter(detected_at__gte=week_ago)
    week_count = week.count()
    prev_count = base.filter(detected_at__gte=now - timedelta(days=14), detected_at__lt=week_ago).count()
    attended = (
        Booking.objects.filter(institution_id=user.institution_id, requires_checkin=True, checked_in_at__isnull=False)
        .filter(resource_q(user))
        .filter(period__startswith__gte=week_ago, period__startswith__lt=now)
        .filter(status__in=[BookingStatus.CHECKED_IN, BookingStatus.COMPLETED])
        .count()
    )
    needed = week_count + attended
    restrictions = list(_restrictions(user, now).select_related("user__department").order_by("ends_at"))

    try:
        days = int(request.GET.get("days", 30))
    except ValueError:
        days = 30
    days = days if days in RANGES else 30
    show = request.GET.get("show", "all")
    show = show if show in ("all", "counted", "forgiven") else "all"
    rows = base.filter(detected_at__gte=now - timedelta(days=days)).select_related(
        "user", "resource__building", "booking", "forgiven_by"
    )
    if show == "counted":
        rows = rows.filter(forgiven=False)
    elif show == "forgiven":
        rows = rows.filter(forgiven=True)
    page = Paginator(rows.order_by("-detected_at"), PER_PAGE).get_page(request.GET.get("page"))
    people = {ns.user_id for ns in page.object_list}
    record = dict(
        NoShow.objects.filter(user_id__in=people, forgiven=False, detected_at__gte=now - timedelta(days=30))
        .values("user_id")
        .annotate(n=Count("id"))
        .values_list("user_id", "n")
    )
    paused = {r.user_id for r in restrictions}
    ctx = {
        "week_count": week_count,
        "delta": week_count - prev_count,
        "rate": (week_count / needed) if needed else None,
        "needed": needed,
        "released": week.aggregate(n=Sum("released_minutes"))["n"] or 0,
        "forgiven_week": week.filter(forgiven=True).count(),
        "restrictions": restrictions,
        "page": page,
        "rows": [(ns, record.get(ns.user_id, 0), ns.user_id in paused) for ns in page.object_list],
        "days": days,
        "ranges": RANGES,
        "show": show,
        "scope_label": scope_label(user),
        "campus_wide": is_campus_wide(user),
        "here": request.get_full_path(),
        "now": now,
    }
    return render(request, "manage/no_shows.html", ctx)


@staff_required("forgive_no_shows")
@require_POST
def forgive(request, pk):
    user, now = request.user, timezone.now()
    try:
        ns = _no_shows(user).select_related("user", "resource").get(pk=pk)
    except NoShow.DoesNotExist:
        raise Http404 from None
    back = safe_next(request, reverse("manage:no_shows"))
    reason = request.POST.get("reason", "").strip()
    if ns.forgiven:
        messages.info(request, f"Already forgiven by {ns.forgiven_by.display_name if ns.forgiven_by else 'a colleague'}.")
        return redirect(back)
    if not reason:
        messages.error(request, "Add a short reason so the forgiveness is on record, then try again.")
        return redirect(back)
    was_paused = services.active_restriction(ns.user, now) is not None
    try:
        services.forgive(ns, user, reason, request=request, now=now)
    except DomainError as exc:
        messages.error(request, exc.message)
        return redirect(back)
    msg = f"Forgiven. It no longer counts towards {ns.user.display_name}'s record."
    if was_paused and services.active_restriction(ns.user, now) is None:
        msg += " Their booking pause was lifted too."
    messages.success(request, msg)
    return redirect(back)


@staff_required("forgive_no_shows")
@require_POST
def lift(request, pk):
    user, now = request.user, timezone.now()
    qs = Restriction.objects.filter(institution_id=user.institution_id).select_related("user")
    if not is_campus_wide(user):
        qs = qs.filter(user_id__in=_no_shows(user).filter(detected_at__gte=now - RESTRICTION_LOOKBACK).values("user_id"))
    try:
        r = qs.get(pk=pk)
    except Restriction.DoesNotExist:
        raise Http404 from None
    back = safe_next(request, reverse("manage:no_shows"))
    if r.lifted_at or r.ends_at <= now:
        messages.info(request, f"{r.user.display_name} can already book; this pause has ended.")
        return redirect(back)
    try:
        services.lift_restriction(r, user, request=request)
    except DomainError as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, f"Pause lifted. {r.user.display_name} can book again straight away.")
    return redirect(back)
