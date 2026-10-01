"""
M3 — Booking Engine service interface.

    create_booking(...)          atomic slot claim; returns Booking or raises BookingRejected/SlotUnavailable
    cancel_booking(...)          owner or manager cancels; frees the slot
    set_status(...)              guarded state transition used by other modules
    explain_conflicts(...)       what holds a time range, in words
    claim_block / release_blocks timetable + maintenance claims on the shared ledger
    displace_bookings(...)       cancel holding bookings that a hard constraint now overrides
    expand_occurrences / preview_series / create_series   recurring bookings
    suggest_alternatives(...)    free resources of the same kind for a time range
    consumption(...)             booked minutes/count for quota accounting

Correctness does not depend on the friendly pre-checks in this module. The final
word belongs to PostgreSQL: both INSERTs below run inside one transaction, and the
exclusion constraints reject any overlap with SQLSTATE 23P01 — which we translate
into SlotUnavailable. See docs/booking-concurrency.md.
"""

from __future__ import annotations

import logging
import random
import time as time_mod
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.accounts.permissions import can_manage_resource, has_cap
from apps.core.db import RangeDuration
from apps.core.errors import BookingRejected, InvalidTransition, NotPermitted, SlotUnavailable
from apps.core.timeutil import aware, minutes_between, trange

from .models import (
    HOLDING_STATUSES,
    AttemptOutcome,
    Booking,
    BookingAttempt,
    BookingSeries,
    BookingSlot,
    BookingStatus,
    SlotKind,
)

log = logging.getLogger(__name__)

EXCLUSION_VIOLATION = "23P01"
DEADLOCK_DETECTED = "40P01"
CLAIM_RETRIES = 8


def _is_exclusion_violation(exc: IntegrityError) -> bool:
    cause = exc.__cause__
    return getattr(cause, "sqlstate", None) == EXCLUSION_VIOLATION


def _hm(dt):
    return timezone.localtime(dt).strftime("%H:%M")


# ── Conflicts ───────────────────────────────────────────────────────────────


@dataclass
class Conflict:
    kind: str
    start: datetime
    end: datetime
    label: str
    booking_id: int | None = None

    @property
    def sentence(self) -> str:
        span = f"{_hm(self.start)}–{_hm(self.end)}"
        if self.kind == SlotKind.CLASS:
            return f"A timetabled class ({self.label}) runs {span}."
        if self.kind == SlotKind.MAINTENANCE:
            return f"Scheduled maintenance ({self.label}) runs {span}."
        return f"Already booked {span}."


def conflicts_for(resource, start, end, *, exclude_booking_id=None) -> list[Conflict]:
    qs = BookingSlot.objects.filter(resource=resource, period__overlap=trange(start, end))
    if exclude_booking_id:
        qs = qs.exclude(booking_id=exclude_booking_id)
    return [Conflict(s.kind, s.period.lower, s.period.upper, s.label, s.booking_id) for s in qs.order_by("period")]


def _conflict_error(resource, start, end, conflicts: list[Conflict]) -> SlotUnavailable:
    if not conflicts:
        # The constraint fired but the row that beat us is not visible yet (it committed
        # after our snapshot) — this is exactly the race the constraint exists for.
        return SlotUnavailable("Someone booked this slot a moment ago. Pick another time.", code="conflict")
    first = conflicts[0]
    code = {SlotKind.CLASS: "timetable", SlotKind.MAINTENANCE: "maintenance"}.get(first.kind, "conflict")
    return SlotUnavailable(
        first.sentence, code=code, detail={"conflicts": [{"kind": c.kind, "label": c.label} for c in conflicts]}
    )


def record_attempt(resource, user, start, end, outcome):
    try:
        BookingAttempt.objects.create(resource=resource, user=user, period=trange(start, end), outcome=outcome)
    except Exception:  # pragma: no cover - analytics must never block booking
        log.exception("could not record booking attempt")


_OUTCOME_FOR_CODE = {
    "conflict": AttemptOutcome.CONFLICT,
    "timetable": AttemptOutcome.TIMETABLE,
    "maintenance": AttemptOutcome.MAINTENANCE,
    "blackout": AttemptOutcome.BLACKOUT,
    "closed": AttemptOutcome.CLOSED,
    "quota": AttemptOutcome.QUOTA,
    "restricted": AttemptOutcome.RESTRICTED,
    "forbidden": AttemptOutcome.FORBIDDEN,
}


ADVISORY_NAMESPACE = 20_020  # P20; keeps our advisory keys apart from anything else using them


def serialise_claims(resource_id: int):
    """
    Throughput aid, not the correctness mechanism.

    A transaction-scoped advisory lock queues concurrent claims *on the same resource*
    so they reach the exclusion check one after another instead of deadlocking in
    pairs. Different resources never wait on each other. Remove this function and
    double-booking is still impossible (test_database_constraint_alone_* proves it);
    you would only pay for it in deadlock retries under a stampede.
    """
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", [ADVISORY_NAMESPACE, resource_id])


def _is_deadlock(exc: OperationalError) -> bool:
    return getattr(exc.__cause__, "sqlstate", None) == DEADLOCK_DETECTED


def _claim(booking: Booking, *, label: str):
    """
    INSERT the booking and its ledger slot in one savepoint.

    Exclusion constraints check *in-progress* rows too: when two transactions insert
    overlapping ranges at the same instant, each waits for the other, and PostgreSQL's
    deadlock detector aborts one of them (40P01). That victim lost the race, but it
    cannot know yet whether the winner will commit — so it rolls back to the savepoint
    and tries again. The retry either sees the winner's committed row (-> 23P01 ->
    SlotUnavailable) or, if the winner rolled back, takes the slot itself.
    """
    resource = booking.resource
    serialise_claims(resource.pk)
    for attempt in range(CLAIM_RETRIES):
        try:
            with transaction.atomic():
                booking.save(force_insert=True)
                BookingSlot.objects.create(
                    resource=resource, period=booking.period, kind=SlotKind.BOOKING, booking=booking, label=label
                )
            return
        except IntegrityError as exc:
            booking.pk = None
            if not _is_exclusion_violation(exc):
                raise
            raise _conflict_error(
                resource, booking.start, booking.end, conflicts_for(resource, booking.start, booking.end)
            ) from None
        except OperationalError as exc:
            booking.pk = None
            if not _is_deadlock(exc):
                raise
            visible = conflicts_for(resource, booking.start, booking.end)
            if visible:
                raise _conflict_error(resource, booking.start, booking.end, visible) from None
            time_mod.sleep(random.uniform(0.005, 0.03) * (attempt + 1))  # de-synchronise the retry
    raise SlotUnavailable("This slot is in very high demand right now — please try again.", code="conflict")


# ── Create ──────────────────────────────────────────────────────────────────


def create_booking(
    *,
    requester: User,
    resource,
    start: datetime,
    end: datetime,
    title: str,
    attendees: int = 1,
    booked_for: User | None = None,
    group_label: str = "",
    notes: str = "",
    items: dict[int, int] | None = None,
    series: BookingSeries | None = None,
    request=None,
    notify: bool = True,
    now: datetime | None = None,
) -> Booking:
    from apps.rules import services as rules

    now = now or timezone.now()
    booked_for = booked_for or requester
    title = (title or "").strip() or f"{resource.type.name} booking"

    try:
        if booked_for.pk != requester.pk and not has_cap(requester, "book_on_behalf"):
            raise NotPermitted("You can only book for yourself.")
        if group_label and not has_cap(requester, "book_on_behalf"):
            raise NotPermitted("Only faculty and staff can book on behalf of a class or group.")
        if booked_for.institution_id != resource.institution_id:
            raise NotPermitted("That resource belongs to another institution.")

        policy = rules.policy_for(resource)
        rules.validate_request(
            requester=requester,
            booked_for=booked_for,
            resource=resource,
            start=start,
            end=end,
            attendees=attendees,
            now=now,
            policy=policy,
        )
        # Friendly pre-check. Not relied upon for correctness (see module docstring).
        existing = conflicts_for(resource, start, end)
        if existing:
            raise _conflict_error(resource, start, end, existing)

        with transaction.atomic():
            # Serialise *this person's* concurrent requests so quota arithmetic is exact.
            # Different people never wait on each other here; the slot itself is guarded
            # by the exclusion constraint, not by a lock.
            User.objects.select_for_update().only("pk").get(pk=booked_for.pk)
            quotas = rules.applicable_quotas(booked_for, resource.type_id)
            if any(q.is_departmental for q in quotas):
                Department.objects.select_for_update().only("pk").get(pk=booked_for.department_id)
            rules.check_quota(booked_for, resource, start, end)

            from apps.approvals import services as approvals

            workflow = approvals.resolve_workflow(resource, requester, attendees, minutes_between(start, end))
            needs_approval = workflow is not None and not workflow.auto_approve

            booking = Booking(
                institution_id=resource.institution_id,
                resource=resource,
                requester=requester,
                booked_for=booked_for,
                group_label=group_label.strip(),
                title=title[:140],
                attendees=attendees,
                notes=notes,
                period=trange(start, end),
                status=BookingStatus.PENDING if needs_approval else BookingStatus.APPROVED,
                series=series,
                requires_checkin=policy.requires_checkin,
                checkin_grace_minutes=policy.checkin_grace_minutes,
                decided_at=None if needs_approval else now,
            )
            _claim(booking, label=group_label or title[:160])

            approvals.start_chain(booking, workflow, now=now, notify=notify)
            if items:
                from apps.inventory import services as inventory

                inventory.reserve(booking, items)

            from apps.audit.services import record

            record(
                requester,
                "booking.create",
                booking,
                after={"status": booking.status, "period": str(booking.period)},
                request=request,
            )
            if notify and not needs_approval:
                _notify_confirmed(booking)
    except (BookingRejected, NotPermitted) as exc:
        record_attempt(resource, booked_for, start, end, _OUTCOME_FOR_CODE.get(exc.code, AttemptOutcome.POLICY))
        raise

    record_attempt(resource, booked_for, start, end, AttemptOutcome.BOOKED)
    return booking


def _notify_confirmed(booking: Booking):
    from apps.notifications.models import Kind
    from apps.notifications.services import notify

    start = timezone.localtime(booking.start)
    notify(
        booking.booked_for,
        Kind.BOOKING_CONFIRMED,
        f"Confirmed · {booking.resource.name}",
        f"{start:%a %d %b}, {start:%H:%M}–{_hm(booking.end)}. Your QR pass is ready.",
        booking.get_absolute_url(),
    )


# ── State changes ───────────────────────────────────────────────────────────


def release_slot(booking: Booking):
    BookingSlot.objects.filter(booking=booking).delete()


def set_status(booking: Booking, new_status: str, *, reason: str = "", actor=None, now=None) -> Booking:
    """Guarded transition. Leaving a holding status frees the time on the ledger."""
    now = now or timezone.now()
    if booking.status == new_status:
        return booking
    if not booking.can_transition(new_status):
        raise InvalidTransition(
            f"A {booking.get_status_display().lower()} booking can't become {BookingStatus(new_status).label.lower()}."
        )
    booking.status = new_status
    if reason:
        booking.status_reason = reason[:240]
    update = ["status", "status_reason", "updated_at"]
    if new_status == BookingStatus.CANCELLED:
        booking.cancelled_at = now
        update.append("cancelled_at")
    if new_status in (BookingStatus.APPROVED, BookingStatus.REJECTED):
        booking.decided_at = now
        update.append("decided_at")
    booking.save(update_fields=update)
    if new_status not in HOLDING_STATUSES:
        release_slot(booking)
    return booking


def can_cancel(user, booking: Booking, now=None) -> bool:
    if booking.status not in (BookingStatus.PENDING, BookingStatus.APPROVED):
        return False
    if booking.end <= (now or timezone.now()):
        return False
    return user.pk in (booking.requester_id, booking.booked_for_id) or can_manage_resource(user, booking.resource)


def cancel_booking(booking: Booking, actor, *, reason: str = "", request=None, now=None) -> Booking:
    now = now or timezone.now()
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("resource").get(pk=booking.pk)
        if not can_cancel(actor, booking, now=now):
            raise NotPermitted("This booking can't be cancelled.")
        before = booking.status
        set_status(booking, BookingStatus.CANCELLED, reason=reason or "Cancelled by requester", actor=actor, now=now)
        from apps.approvals.services import close_open_steps
        from apps.inventory.services import cancel_reservations

        close_open_steps(booking)
        cancel_reservations(booking)
        from apps.audit.services import record

        record(
            actor,
            "booking.cancel",
            booking,
            before={"status": before},
            after={"status": booking.status, "reason": reason},
            request=request,
        )
        if actor.pk != booking.booked_for_id:
            from apps.notifications.models import Kind
            from apps.notifications.services import notify

            notify(
                booking.booked_for,
                Kind.CANCELLED,
                f"Cancelled · {booking.resource.name}",
                reason or f"Cancelled by {actor.display_name}.",
                booking.get_absolute_url(),
            )
    return booking


# ── Hard claims: timetable and maintenance ──────────────────────────────────


def displace_bookings(resource, start, end, *, reason: str, notify: bool = True, now=None) -> list[Booking]:
    """Cancel holding bookings overlapping [start, end) because a hard constraint now owns that time."""
    now = now or timezone.now()
    victims = list(
        Booking.objects.select_for_update()
        .filter(resource=resource, status__in=HOLDING_STATUSES, period__overlap=trange(start, end))
        .select_related("resource", "booked_for")
    )
    for b in victims:
        if b.status == BookingStatus.CHECKED_IN:
            # Someone is physically there; end their session at the start of the hard claim.
            b.status = BookingStatus.COMPLETED
            b.status_reason = reason[:240]
            b.period = trange(b.start, max(b.start + timedelta(minutes=1), min(b.end, start)))
            b.save(update_fields=["status", "status_reason", "period", "updated_at"])
            release_slot(b)
        else:
            set_status(b, BookingStatus.CANCELLED, reason=reason, now=now)
            from apps.approvals.services import close_open_steps
            from apps.inventory.services import cancel_reservations

            close_open_steps(b)
            cancel_reservations(b)
        if notify:
            from apps.notifications.models import Kind
            from apps.notifications.services import notify as send

            alts = suggest_alternatives(b.resource, b.start, b.end, attendees=b.attendees, limit=2)
            alt_text = (" Free alternatives: " + ", ".join(a.name for a in alts) + ".") if alts else ""
            send(
                b.booked_for,
                Kind.UNAVAILABLE,
                f"{b.resource.name} is no longer available",
                f"{reason} Your booking {b.reference} on {timezone.localtime(b.start):%a %d %b %H:%M} was cancelled.{alt_text}",
                b.get_absolute_url(),
            )
    return victims


def claim_block(
    resource,
    start,
    end,
    *,
    kind: str,
    source_type: str,
    source_id: int,
    label: str,
    displace: bool = True,
    reason: str = "",
    notify: bool = True,
) -> tuple[BookingSlot, int]:
    """
    Write a timetable/maintenance claim onto the ledger, displacing ordinary bookings.
    A concurrent booking that lands between our displacement and our INSERT makes the
    INSERT fail on the constraint; we simply displace again and retry.
    """
    displaced = 0
    for _attempt in range(3):
        if displace:
            displaced += len(
                displace_bookings(resource, start, end, reason=reason or f"{label} was scheduled.", notify=notify)
            )
        try:
            with transaction.atomic():
                slot = BookingSlot.objects.create(
                    resource=resource,
                    period=trange(start, end),
                    kind=kind,
                    source_type=source_type,
                    source_id=source_id,
                    label=label[:160],
                )
            return slot, displaced
        except IntegrityError as exc:
            if not _is_exclusion_violation(exc):
                raise
            blockers = conflicts_for(resource, start, end)
            if not displace or any(c.kind != SlotKind.BOOKING for c in blockers):
                raise _conflict_error(resource, start, end, blockers) from None
    raise SlotUnavailable("The time range kept being claimed concurrently; try again.")


def release_blocks(source_type: str, source_ids) -> int:
    deleted, _ = BookingSlot.objects.filter(source_type=source_type, source_id__in=list(source_ids)).delete()
    return deleted


def shrink_block(source_type: str, source_id: int, new_end: datetime):
    for slot in BookingSlot.objects.filter(source_type=source_type, source_id=source_id):
        if new_end <= slot.period.lower:
            slot.delete()
        elif new_end < slot.period.upper:
            slot.period = trange(slot.period.lower, new_end)
            slot.save(update_fields=["period"])


def shrink_booking(booking: Booking, new_end: datetime) -> int:
    """Hand back the tail of a booking (early check-out). Returns minutes released."""
    if new_end >= booking.end:
        return 0
    new_end = max(new_end, booking.start + timedelta(minutes=1))
    released = minutes_between(new_end, booking.end)
    booking.period = trange(booking.start, new_end)
    booking.save(update_fields=["period", "updated_at"])
    BookingSlot.objects.filter(booking=booking).update(period=booking.period)
    return released


# ── Alternatives ────────────────────────────────────────────────────────────


def suggest_alternatives(resource, start, end, *, attendees: int = 1, limit: int = 3):
    from apps.catalogue.models import Resource

    taken = BookingSlot.objects.filter(period__overlap=trange(start, end)).values("resource_id")
    candidates = (
        Resource.objects.filter(
            institution_id=resource.institution_id,
            type_id=resource.type_id,
            status="active",
            is_bookable=True,
            capacity__gte=attendees,
        )
        .exclude(pk=resource.pk)
        .exclude(pk__in=taken)
        .select_related("building", "type")
    )
    from apps.rules.services import blackouts_for, opening_intervals

    out = []
    # Prefer same building, then the closest capacity.
    for r in sorted(
        candidates, key=lambda r: (r.building_id != resource.building_id, abs(r.capacity - resource.capacity))
    ):
        if not any(o <= start and end <= c for o, c in opening_intervals(r, timezone.localtime(start).date())):
            continue
        if blackouts_for(r, start, end):
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


# ── Quota accounting ────────────────────────────────────────────────────────


def consumption(*, window, user_id=None, department_id=None, resource_type_id=None, exclude_booking_id=None):
    """Minutes and count of bookings that count against a quota in `window`."""
    start, end = window
    qs = Booking.objects.filter(
        status__in=(*HOLDING_STATUSES, BookingStatus.COMPLETED),
        period__startswith__gte=start,
        period__startswith__lt=end,
    )
    if user_id is not None:
        qs = qs.filter(booked_for_id=user_id)
    if department_id is not None:
        qs = qs.filter(booked_for__department_id=department_id)
    if resource_type_id is not None:
        qs = qs.filter(resource__type_id=resource_type_id)
    if exclude_booking_id:
        qs = qs.exclude(pk=exclude_booking_id)
    agg = qs.aggregate(total=Coalesce(Sum(RangeDuration("period")), timedelta(0)))
    return int(agg["total"].total_seconds() // 60), qs.count()


# ── Recurring bookings ──────────────────────────────────────────────────────

MAX_OCCURRENCES = 60


def expand_occurrences(
    *,
    frequency: str,
    interval: int,
    weekdays: list[int],
    start_date: date,
    until_date: date,
    start_time: time,
    end_time: time,
) -> list[tuple[datetime, datetime]]:
    out = []
    interval = max(1, interval)
    if frequency == "daily":
        d = start_date
        while d <= until_date and len(out) < MAX_OCCURRENCES:
            out.append((aware(d, start_time), aware(d, end_time)))
            d += timedelta(days=interval)
        return out
    days = sorted(set(weekdays or [start_date.weekday()]))
    week0 = start_date - timedelta(days=start_date.weekday())
    week = 0
    while len(out) < MAX_OCCURRENCES:
        monday = week0 + timedelta(weeks=week * interval)
        if monday > until_date:
            break
        for wd in days:
            d = monday + timedelta(days=wd)
            if start_date <= d <= until_date:
                out.append((aware(d, start_time), aware(d, end_time)))
        week += 1
    return out[:MAX_OCCURRENCES]


@dataclass
class OccurrencePlan:
    start: datetime
    end: datetime
    ok: bool
    code: str = ""
    reason: str = ""
    alternatives: list = field(default_factory=list)


def preview_series(*, requester, resource, occurrences, attendees=1, booked_for=None) -> list[OccurrencePlan]:
    """Dry-run each occurrence against rules and the ledger (no writes)."""
    from apps.rules import services as rules

    booked_for = booked_for or requester
    policy = rules.policy_for(resource)
    plans = []
    for s, e in occurrences:
        try:
            rules.validate_request(
                requester=requester,
                booked_for=booked_for,
                resource=resource,
                start=s,
                end=e,
                attendees=attendees,
                policy=policy,
            )
            c = conflicts_for(resource, s, e)
            if c:
                raise _conflict_error(resource, s, e, c)
            plans.append(OccurrencePlan(s, e, True))
        except BookingRejected as exc:
            alts = (
                suggest_alternatives(resource, s, e, attendees=attendees, limit=2)
                if exc.code in ("conflict", "timetable", "maintenance")
                else []
            )
            plans.append(OccurrencePlan(s, e, False, exc.code, exc.message, alts))
    return plans


def create_series(
    *,
    requester,
    resource,
    title,
    frequency,
    interval,
    weekdays,
    start_date,
    until_date,
    start_time,
    end_time,
    attendees=1,
    group_label="",
    booked_for=None,
    notes="",
    request=None,
):
    """
    Book every occurrence that can be booked. Each occurrence is claimed in its own
    savepoint, so a mid-series conflict skips that one date and the rest proceed.
    """
    if not has_cap(requester, "book_recurring"):
        raise NotPermitted("Recurring bookings are available to faculty and staff.")
    occurrences = expand_occurrences(
        frequency=frequency,
        interval=interval,
        weekdays=weekdays,
        start_date=start_date,
        until_date=until_date,
        start_time=start_time,
        end_time=end_time,
    )
    if not occurrences:
        raise BookingRejected("That pattern has no dates in range.", code="policy")
    series = BookingSeries.objects.create(
        institution_id=resource.institution_id,
        resource=resource,
        requester=requester,
        title=title[:140],
        frequency=frequency,
        interval=interval,
        weekdays=weekdays,
        start_date=start_date,
        until_date=until_date,
        start_time=start_time,
        end_time=end_time,
        group_label=group_label,
    )
    created, skipped = [], []
    for s, e in occurrences:
        try:
            created.append(
                create_booking(
                    requester=requester,
                    resource=resource,
                    start=s,
                    end=e,
                    title=title,
                    attendees=attendees,
                    booked_for=booked_for,
                    group_label=group_label,
                    notes=notes,
                    series=series,
                    request=request,
                    notify=False,
                )
            )
        except (BookingRejected, NotPermitted) as exc:
            skipped.append({"start": s.isoformat(), "end": e.isoformat(), "code": exc.code, "reason": exc.message})
    series.created_count = len(created)
    series.skipped = skipped
    series.save(update_fields=["created_count", "skipped", "updated_at"])

    from apps.notifications.models import Kind
    from apps.notifications.services import notify

    pending = sum(1 for b in created if b.status == BookingStatus.PENDING)
    body = f"{len(created)} of {len(occurrences)} dates booked"
    if skipped:
        body += f", {len(skipped)} skipped (conflicts or rules)"
    if pending:
        body += f"; {pending} awaiting approval"
    notify(
        requester,
        Kind.SERIES,
        f"Recurring booking · {resource.name}",
        body + ".",
        created[0].get_absolute_url() if created else "",
    )
    return series, created, skipped


# ── Queries used by views ───────────────────────────────────────────────────


def visible_bookings(user):
    """Bookings a user may see: their own, plus those on resources they manage."""
    from apps.accounts.permissions import is_campus_wide

    qs = Booking.objects.filter(institution_id=user.institution_id)
    if is_campus_wide(user):
        return qs
    q = Q(booked_for=user) | Q(requester=user)
    if user.role == "custodian":
        q |= Q(resource__custodians__user=user)
    elif user.role == "dept_head" and user.department_id:
        q |= Q(resource__department_id=user.department_id) | Q(booked_for__department_id=user.department_id)
    return qs.filter(q).distinct()
