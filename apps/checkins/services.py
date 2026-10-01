"""
M6 service interface.

    checkin_window(booking)                  -> (opens_at, closes_at)
    check_in(booking, actor, method)         approved -> checked_in (QR pass, room QR, app, custodian)
    check_in_at_resource(resource, user)     door-QR flow: find the user's booking that is open for check-in now
    check_out(booking, actor)                checked_in -> completed; hands back unused time
    sweep_no_shows(now)                      auto-release after the grace period; records NoShow; applies ladder
    sweep_completed(now)                     close bookings whose end has passed
    active_restriction(user, at)             current booking restriction, if any
    forgive(no_show, actor, reason)          custodian/manager override; may lift a restriction
    lift_restriction(restriction, actor)
"""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import can_manage_resource, has_cap
from apps.bookings.models import Booking, BookingStatus
from apps.core.errors import InvalidTransition, NotPermitted
from apps.core.timeutil import minutes_between

from .models import CheckIn, CheckInMethod, NoShow, Restriction


def _policy(booking):
    from apps.rules.services import policy_for

    return policy_for(booking.resource)


def checkin_window(booking: Booking, policy=None):
    policy = policy or _policy(booking)
    opens = booking.start - timedelta(minutes=policy.checkin_opens_minutes)
    closes = min(booking.start + timedelta(minutes=booking.checkin_grace_minutes), booking.end)
    return opens, closes


def checkin_state(booking: Booking, now=None) -> dict:
    """What the UI should show on a booking pass right now."""
    now = now or timezone.now()
    if booking.status == BookingStatus.CHECKED_IN:
        return {"state": "in_use", "ends": booking.end}
    if booking.status != BookingStatus.APPROVED:
        return {"state": "inactive"}
    if not booking.requires_checkin:
        return {"state": "not_required"}
    opens, closes = checkin_window(booking)
    if now < opens:
        return {"state": "not_yet", "opens": opens, "closes": closes}
    if now <= closes:
        return {"state": "open", "opens": opens, "closes": closes, "seconds_left": int((closes - now).total_seconds())}
    return {"state": "missed", "closes": closes}


def _may_act(actor, booking) -> bool:
    return actor.pk in (booking.booked_for_id, booking.requester_id) or can_manage_resource(actor, booking.resource)


def check_in(booking: Booking, actor, *, method=CheckInMethod.APP, request=None, now=None) -> Booking:
    now = now or timezone.now()
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("resource").get(pk=booking.pk)
        if not _may_act(actor, booking):
            raise NotPermitted("This booking belongs to someone else.")
        if method in (CheckInMethod.PASS_QR, CheckInMethod.CUSTODIAN) and not can_manage_resource(
            actor, booking.resource
        ):
            raise NotPermitted("Only the resource custodian can check in a pass on someone's behalf.")
        if booking.status == BookingStatus.CHECKED_IN:
            return booking
        if booking.status != BookingStatus.APPROVED:
            raise InvalidTransition(
                f"This booking is {booking.get_status_display().lower()}, so it can't be checked into."
            )
        opens, closes = checkin_window(booking)
        if now < opens:
            raise InvalidTransition(f"Check-in opens at {timezone.localtime(opens):%H:%M}.")
        if now > closes:
            raise InvalidTransition("The check-in window has closed and the slot was released.")
        booking.status = BookingStatus.CHECKED_IN
        booking.checked_in_at = now
        booking.save(update_fields=["status", "checked_in_at", "updated_at"])
        CheckIn.objects.create(booking=booking, checked_in_at=now, method=method, checked_in_by=actor)
        from apps.inventory.services import issue_for_booking

        issue_for_booking(booking, actor)
        from apps.audit.services import record

        record(actor, "booking.check_in", booking, after={"method": method}, request=request)
    return booking


def check_in_at_resource(resource, user, *, request=None, now=None) -> Booking | None:
    """Door-QR flow: the user scanned the QR fixed to the room/equipment."""
    now = now or timezone.now()
    candidates = Booking.objects.filter(
        resource=resource,
        booked_for=user,
        status__in=[BookingStatus.APPROVED, BookingStatus.CHECKED_IN],
        period__startswith__lte=now + timedelta(hours=1),
        period__endswith__gt=now,
    ).order_by("period")
    for b in candidates:
        if b.status == BookingStatus.CHECKED_IN:
            return b
        opens, closes = checkin_window(b)
        if opens <= now <= closes:
            return check_in(b, user, method=CheckInMethod.RESOURCE_QR, request=request, now=now)
    return None


def check_out(booking: Booking, actor, *, request=None, now=None, auto=False) -> Booking:
    now = now or timezone.now()
    from apps.bookings.services import shrink_booking

    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("resource").get(pk=booking.pk)
        if not auto and not _may_act(actor, booking):
            raise NotPermitted("This booking belongs to someone else.")
        if booking.status != BookingStatus.CHECKED_IN:
            raise InvalidTransition("Only a booking that is in use can be checked out.")
        released = 0
        if now < booking.end:
            # Round up to the next 5 minutes and give the rest of the slot back to campus.
            cut = now + timedelta(minutes=(5 - timezone.localtime(now).minute % 5) % 5)
            cut = cut.replace(second=0, microsecond=0)
            released = shrink_booking(booking, cut)
        booking.status = BookingStatus.COMPLETED
        booking.checked_out_at = min(now, booking.end)
        booking.save(update_fields=["status", "checked_out_at", "updated_at"])
        from apps.bookings.services import release_slot

        release_slot(booking)
        CheckIn.objects.filter(booking=booking).update(
            checked_out_at=booking.checked_out_at,
            checked_out_by=None if auto else actor,
            auto_checked_out=auto,
            minutes_released=released,
        )
        from apps.inventory.services import return_for_booking

        return_for_booking(booking, None if auto else actor)
        if not auto:
            from apps.audit.services import record

            record(actor, "booking.check_out", booking, after={"released_minutes": released}, request=request)
    return booking


# ── Restrictions ────────────────────────────────────────────────────────────


def active_restriction(user, at=None) -> Restriction | None:
    if user is None or not getattr(user, "pk", None):
        return None
    at = at or timezone.now()
    return (
        Restriction.objects.filter(user=user, starts_at__lte=at, ends_at__gt=at, lifted_at__isnull=True)
        .order_by("-ends_at")
        .first()
    )


def recent_no_shows(user, days: int, at=None) -> int:
    at = at or timezone.now()
    return NoShow.objects.filter(user=user, forgiven=False, detected_at__gte=at - timedelta(days=days)).count()


def apply_ladder(user, now=None) -> Restriction | None:
    """Progressive restriction: the highest tier the user's recent no-shows reach decides."""
    from apps.notifications.models import Kind
    from apps.notifications.services import notify
    from apps.rules.models import RestrictionTier

    now = now or timezone.now()
    tiers = list(RestrictionTier.objects.filter(institution_id=user.institution_id).order_by("-no_shows"))
    for tier in tiers:
        count = recent_no_shows(user, tier.window_days, now)
        if count < tier.no_shows:
            continue
        if tier.restrict_days == 0:
            notify(
                user,
                Kind.RESTRICTED,
                "Heads up: no-shows are adding up",
                f"{count} missed check-ins in {tier.window_days} days. One more and booking will be paused.",
                "/me/standing/",
            )
            return None
        ends = now + timedelta(days=tier.restrict_days)
        current = active_restriction(user, now)
        if current and current.ends_at >= ends:
            return current
        r = Restriction.objects.create(
            institution_id=user.institution_id,
            user=user,
            starts_at=now,
            ends_at=ends,
            reason=f"{count} no-shows in {tier.window_days} days",
            tier_label=tier.label,
        )
        notify(
            user,
            Kind.RESTRICTED,
            f"Booking paused for {tier.restrict_days} days",
            f"{count} missed check-ins in {tier.window_days} days ({tier.label}). "
            f"You can book again from {timezone.localtime(ends):%d %b}.",
            "/me/standing/",
        )
        return r
    return None


def forgive(no_show: NoShow, actor, reason: str, *, request=None, now=None) -> NoShow:
    if not has_cap(actor, "forgive_no_shows") or not can_manage_resource(actor, no_show.resource):
        raise NotPermitted("You can't forgive no-shows for this resource.")
    if no_show.user_id == actor.pk:
        raise NotPermitted("Your own no-show has to be forgiven by someone else.")  # SEC-04
    now = now or timezone.now()
    with transaction.atomic():
        no_show.forgiven = True
        no_show.forgiven_by = actor
        no_show.forgiven_reason = reason[:240]
        no_show.save(update_fields=["forgiven", "forgiven_by", "forgiven_reason"])
        # Re-evaluate: lift the automatic restrictions the user no longer qualifies for. Every
        # tier reached leaves its own row (3rd, 4th, 5th no-show...), so lift them all, not just
        # the longest — otherwise an older, shorter pause keeps blocking the user.
        from apps.rules.models import RestrictionTier

        still = any(
            recent_no_shows(no_show.user, t.window_days, now) >= t.no_shows
            for t in RestrictionTier.objects.filter(institution_id=no_show.institution_id, restrict_days__gt=0)
        )
        if not still:
            Restriction.objects.filter(
                user=no_show.user, automatic=True, lifted_at__isnull=True, starts_at__lte=now, ends_at__gt=now
            ).update(lifted_at=now, lifted_by=actor)
        from apps.audit.services import record

        record(actor, "no_show.forgive", no_show.booking, after={"reason": reason}, request=request)
    return no_show


def lift_restriction(restriction: Restriction, actor, *, request=None):
    if not has_cap(actor, "forgive_no_shows"):
        raise NotPermitted("You can't lift restrictions.")
    if restriction.user_id == actor.pk:
        raise NotPermitted("Your own restriction has to be lifted by someone else.")  # SEC-04
    restriction.lifted_at = timezone.now()
    restriction.lifted_by = actor
    restriction.save(update_fields=["lifted_at", "lifted_by"])
    from apps.audit.services import record

    record(actor, "restriction.lift", restriction, request=request)
    return restriction


# ── Sweeps (Celery Beat) ────────────────────────────────────────────────────


def sweep_no_shows(now=None) -> list[Booking]:
    """
    Release confirmed bookings nobody checked into within the grace period.
    SKIP LOCKED lets overlapping sweeps (or a slow worker) run safely side by side,
    and a booking being checked into right now is simply skipped until next minute.
    """
    from apps.bookings.services import set_status
    from apps.notifications.models import Kind
    from apps.notifications.services import notify

    now = now or timezone.now()
    released = []
    with transaction.atomic():
        due = (
            Booking.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(status=BookingStatus.APPROVED, requires_checkin=True, period__startswith__lte=now)
            .select_related("resource", "booked_for")
        )
        for b in due:
            if b.checkin_deadline >= now:
                continue  # check_in() still accepts the deadline minute itself (now <= closes)
            freed = minutes_between(max(now, b.start), b.end)
            set_status(
                b, BookingStatus.NO_SHOW, reason=f"Not checked in within {b.checkin_grace_minutes} minutes", now=now
            )
            from apps.inventory.services import cancel_reservations

            cancel_reservations(b)
            NoShow.objects.create(
                institution_id=b.institution_id,
                booking=b,
                user=b.booked_for,
                resource=b.resource,
                detected_at=now,
                released_minutes=freed,
            )
            notify(
                b.booked_for,
                Kind.AUTO_RELEASED,
                f"Released · {b.resource.name}",
                f"No check-in by {timezone.localtime(b.checkin_deadline):%H:%M}, so the slot went back to campus. "
                "Repeated no-shows pause booking.",
                b.get_absolute_url(),
            )
            apply_ladder(b.booked_for, now)
            released.append(b)
    return released


def sweep_completed(now=None) -> int:
    from apps.bookings.services import set_status

    now = now or timezone.now()
    n = 0
    for b in Booking.objects.filter(status=BookingStatus.CHECKED_IN, period__endswith__lte=now):
        check_out(b, None, now=now, auto=True)
        n += 1
    with transaction.atomic():
        for b in Booking.objects.select_for_update(skip_locked=True).filter(
            status=BookingStatus.APPROVED, requires_checkin=False, period__endswith__lte=now
        ):
            set_status(b, BookingStatus.COMPLETED, reason="Ended", now=now)
            n += 1
    return n


def sweep_restrictions(now=None) -> int:
    """Restrictions end by time; nothing to mutate, but report how many lapsed for ops visibility."""
    now = now or timezone.now()
    return Restriction.objects.filter(
        ends_at__lte=now, ends_at__gt=now - timedelta(hours=1), lifted_at__isnull=True
    ).count()
