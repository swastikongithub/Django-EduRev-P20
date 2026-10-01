"""
QR check-in on a phone.

Two QR codes exist, and both open ordinary URLs, so the phone's own camera app works
(no install, no special scanner needed):

* the **booking pass** (/c/<token>/) on the student's screen — the owner checks in from
  it; a custodian scanning it verifies the booking and checks it in on their behalf;
* the **door QR** (/here/<code>/) fixed to the room or equipment — scanning it at the
  door checks in whatever booking the person has there right now (proof of presence).

The in-app scanner (/scan/) does the same for people who prefer it.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import can_manage_resource
from apps.bookings.models import Booking
from apps.bookings.services import visible_bookings
from apps.catalogue.models import Resource
from apps.core.errors import DomainError
from apps.core.http import safe_next

from . import services
from .models import CheckInMethod


@login_required
def scan(request):
    return render(request, "checkins/scan.html")


@login_required
def pass_landing(request, token):
    b = Booking.objects.select_related("resource__building", "booked_for").filter(qr_token=token).first()
    if b is None or b.institution_id != request.user.institution_id:
        raise Http404
    is_owner = request.user.pk in (b.booked_for_id, b.requester_id)
    is_manager = can_manage_resource(request.user, b.resource)
    if not (is_owner or is_manager):
        # Someone else's pass: confirm it's real, reveal nothing personal.
        return render(request, "checkins/landing.html", {"foreign": True, "b": b})
    if request.method == "POST":
        method = CheckInMethod.APP if is_owner else CheckInMethod.PASS_QR
        try:
            services.check_in(b, request.user, method=method, request=request)
            messages.success(request, f"Checked in to {b.resource.name}. Enjoy the session.")
        except DomainError as exc:
            messages.error(request, exc.message)
        return redirect(b.get_absolute_url() if is_owner else request.path)
    return render(
        request,
        "checkins/landing.html",
        {
            "b": b,
            "is_owner": is_owner,
            "is_manager": is_manager,
            "state": services.checkin_state(b),
        },
    )


@login_required
def here(request, code):
    resource = get_object_or_404(
        Resource.objects.select_related("building", "type"), institution_id=request.user.institution_id, code=code
    )
    booking = None
    error = None
    if request.method == "POST":
        try:
            booking = services.check_in_at_resource(resource, request.user, request=request)
        except DomainError as exc:
            error = exc.message
        if booking:
            messages.success(request, f"Checked in to {resource.name}.")
            return redirect(booking.get_absolute_url())
    from apps.bookings import availability

    now = timezone.now()
    mine = (
        Booking.objects.filter(
            resource=resource, booked_for=request.user, status__in=["approved", "checked_in"], period__endswith__gt=now
        )
        .order_by("period")
        .first()
    )
    return render(
        request,
        "checkins/here.html",
        {
            "r": resource,
            "mine": mine,
            "state": services.checkin_state(mine, now) if mine else None,
            "error": error,
            "today": availability.day(resource, timezone.localdate(), request.user, now=now),
            "posted": request.method == "POST",
        },
    )


@login_required
@require_POST
def check_in(request, reference):
    b = get_object_or_404(visible_bookings(request.user), reference=reference)
    try:
        services.check_in(
            b,
            request.user,
            method=CheckInMethod.APP
            if request.user.pk in (b.booked_for_id, b.requester_id)
            else CheckInMethod.CUSTODIAN,
            request=request,
        )
        messages.success(request, f"Checked in to {b.resource.name}.")
    except DomainError as exc:
        messages.error(request, exc.message)
    return redirect(safe_next(request, b.get_absolute_url()))


@login_required
@require_POST
def check_out(request, reference):
    b = get_object_or_404(visible_bookings(request.user), reference=reference)
    try:
        b = services.check_out(b, request.user, request=request)
        released = b.checkin.minutes_released if hasattr(b, "checkin") else 0
        msg = "Checked out. Thanks for releasing it on time."
        if released:
            msg = f"Checked out early. {released} minutes went back to campus for someone else."
        messages.success(request, msg)
    except DomainError as exc:
        messages.error(request, exc.message)
    return redirect(safe_next(request, b.get_absolute_url()))
