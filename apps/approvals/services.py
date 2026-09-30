"""
M5 service interface.

    resolve_workflow(resource, requester, attendees, minutes) -> ApprovalWorkflow | None
    start_chain(booking, workflow)                             creates Approval rows, notifies step 1
    decide(approval, user, approve, comment)                    advances or ends the chain
    queue_for(user)                                             approvals this user may decide now
    approvers_for(approval)                                     who is asked
    close_open_steps(booking)                                   mark waiting steps as skipped
    expire_stale(now)                                           pending bookings whose start passed
"""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.accounts.permissions import has_cap, is_campus_wide
from apps.bookings.models import Booking, BookingStatus
from apps.core.errors import InvalidTransition, NotPermitted

from .models import Approval, ApprovalWorkflow, ApproverRole, Decision


def resolve_workflow(resource, requester, attendees: int, duration_minutes: int) -> ApprovalWorkflow | None:
    candidates = (
        ApprovalWorkflow.objects.filter(institution_id=resource.institution_id, active=True)
        .filter(
            Q(resource_id=resource.pk)
            | Q(resource_type_id=resource.type_id, resource__isnull=True)
            | Q(resource__isnull=True, resource_type__isnull=True)
        )
        .prefetch_related("steps")
    )
    matching = [
        w
        for w in candidates
        if (not w.requester_roles or requester.role in w.requester_roles)
        and (w.min_attendees is None or attendees >= w.min_attendees)
        and (w.min_duration_minutes is None or duration_minutes >= w.min_duration_minutes)
    ]
    if not matching:
        return None
    matching.sort(key=lambda w: (w.specificity, w.priority), reverse=True)
    chosen = matching[0]
    if not chosen.auto_approve and not chosen.steps.all():
        return None  # a workflow with no steps cannot block anyone
    return chosen


def approvers_for(approval: Approval):
    booking = approval.booking
    role = approval.approver_role
    qs = User.objects.filter(institution_id=booking.institution_id, is_active=True)
    if role == ApproverRole.USER:
        return qs.filter(pk=approval.approver_user_id)
    if role == ApproverRole.CUSTODIAN:
        return qs.filter(custodianships__resource_id=booking.resource_id)
    if role == ApproverRole.DEPT_HEAD:
        return qs.filter(role=Role.DEPT_HEAD, department_id=booking.resource.department_id)
    if role == ApproverRole.FACILITY_MANAGER:
        return qs.filter(role=Role.FACILITY_MANAGER)
    return qs.filter(role=Role.ADMIN)


def start_chain(booking: Booking, workflow: ApprovalWorkflow | None, *, now=None, notify=True):
    from apps.notifications.models import Kind
    from apps.notifications.services import notify as send

    now = now or timezone.now()
    if workflow is None or workflow.auto_approve:
        Approval.objects.create(
            booking=booking,
            workflow=workflow,
            step_order=0,
            approver_role=ApproverRole.ADMIN,
            decision=Decision.SKIPPED,
            comment=f"Auto-confirmed by rule: {workflow.name}" if workflow else "No approval required",
            decided_at=now,
        )
        return
    steps = list(workflow.steps.all())
    rows = [
        Approval(
            booking=booking,
            workflow=workflow,
            step_order=s.order,
            approver_role=s.approver_role,
            approver_user=s.approver_user,
            decision=Decision.PENDING if i == 0 else Decision.WAITING,
            due_at=now + timedelta(hours=s.sla_hours) if i == 0 else None,
        )
        for i, s in enumerate(steps)
    ]
    Approval.objects.bulk_create(rows)
    if notify:
        first = Approval.objects.select_related("booking__resource").get(booking=booking, step_order=steps[0].order)
        _ask(first)
        send(
            booking.booked_for,
            Kind.APPROVAL_PENDING,
            f"Requested · {booking.resource.name}",
            f"Held for you while {first.get_approver_role_display().lower()} reviews it "
            f"({len(steps)} step{'s' if len(steps) > 1 else ''}).",
            booking.get_absolute_url(),
        )


def _ask(approval: Approval):
    from apps.notifications.models import Kind
    from apps.notifications.services import notify_many

    b = approval.booking
    start = timezone.localtime(b.start)
    notify_many(
        approvers_for(approval),
        Kind.APPROVAL_REQUIRED,
        f"Approval needed · {b.resource.name}",
        f"{b.booked_for.display_name} · {start:%a %d %b %H:%M}–{timezone.localtime(b.end):%H:%M} · {b.title}",
        "/manage/approvals/",
    )


def can_decide(user, approval: Approval) -> bool:
    if approval.decision != Decision.PENDING or not has_cap(user, "approve_bookings"):
        return False
    if is_campus_wide(user):
        return True
    return approvers_for(approval).filter(pk=user.pk).exists()


def decide(approval: Approval, user, *, approve: bool, comment: str = "", request=None, now=None) -> Booking:
    from apps.audit.services import record
    from apps.bookings.services import set_status
    from apps.notifications.models import Kind
    from apps.notifications.services import notify

    now = now or timezone.now()
    with transaction.atomic():
        booking = (
            Booking.objects.select_for_update().select_related("resource", "booked_for").get(pk=approval.booking_id)
        )
        approval = Approval.objects.select_for_update().get(pk=approval.pk)
        if not can_decide(user, approval):
            raise NotPermitted("You can't decide this approval.")
        if booking.status != BookingStatus.PENDING:
            raise InvalidTransition(f"This request is already {booking.get_status_display().lower()}.")
        if booking.start <= now:
            set_status(booking, BookingStatus.EXPIRED, reason="Start time passed before a decision", now=now)
            close_open_steps(booking)
            raise InvalidTransition("The start time has passed; the request expired.")
        if not approve and not comment.strip():
            raise InvalidTransition("Please give the requester a reason for rejecting.")

        approval.decision = Decision.APPROVED if approve else Decision.REJECTED
        approval.decided_by = user
        approval.decided_at = now
        approval.comment = comment.strip()[:500]
        approval.save(update_fields=["decision", "decided_by", "decided_at", "comment"])
        record(
            user,
            "approval.approve" if approve else "approval.reject",
            booking,
            after={"step": approval.step_order, "comment": approval.comment},
            request=request,
        )

        if not approve:
            set_status(booking, BookingStatus.REJECTED, reason=approval.comment, now=now)
            close_open_steps(booking)
            from apps.inventory.services import cancel_reservations

            cancel_reservations(booking)
            notify(
                booking.booked_for,
                Kind.REJECTED,
                f"Not approved · {booking.resource.name}",
                f"{user.display_name}: {approval.comment}",
                booking.get_absolute_url(),
            )
            return booking

        nxt = booking.approvals.filter(decision=Decision.WAITING).order_by("step_order").first()
        if nxt:
            step = nxt.workflow.steps.filter(order=nxt.step_order).first() if nxt.workflow_id else None
            nxt.decision = Decision.PENDING
            nxt.due_at = now + timedelta(hours=step.sla_hours if step else 24)
            nxt.save(update_fields=["decision", "due_at"])
            _ask(nxt)
            return booking

        set_status(booking, BookingStatus.APPROVED, reason="Approved", now=now)
        notify(
            booking.booked_for,
            Kind.APPROVED,
            f"Approved · {booking.resource.name}",
            f"{timezone.localtime(booking.start):%a %d %b, %H:%M}. Your QR pass is ready.",
            booking.get_absolute_url(),
        )
        return booking


def close_open_steps(booking: Booking):
    booking.approvals.filter(decision__in=[Decision.PENDING, Decision.WAITING]).update(decision=Decision.SKIPPED)


def queue_for(user):
    """Pending approval steps this user is entitled to decide, oldest first."""
    qs = Approval.objects.filter(
        decision=Decision.PENDING, booking__status=BookingStatus.PENDING, booking__institution_id=user.institution_id
    ).select_related("booking__resource__type", "booking__resource__building", "booking__booked_for", "workflow")
    if not has_cap(user, "approve_bookings"):
        return qs.none()
    if is_campus_wide(user):
        return qs.order_by("booking__period")
    q = Q(approver_role=ApproverRole.USER, approver_user=user)
    if user.role == Role.CUSTODIAN:
        q |= Q(approver_role=ApproverRole.CUSTODIAN, booking__resource__custodians__user=user)
    if user.role == Role.DEPT_HEAD and user.department_id:
        q |= Q(approver_role=ApproverRole.DEPT_HEAD, booking__resource__department_id=user.department_id)
    return qs.filter(q).distinct().order_by("booking__period")


def expire_stale(now=None) -> int:
    from apps.bookings.services import set_status
    from apps.notifications.models import Kind
    from apps.notifications.services import notify

    now = now or timezone.now()
    n = 0
    with transaction.atomic():
        stale = (
            Booking.objects.select_for_update(skip_locked=True)
            .filter(status=BookingStatus.PENDING, period__startswith__lte=now)
            .select_related("resource", "booked_for")
        )
        for b in stale:
            set_status(b, BookingStatus.EXPIRED, reason="No decision before the start time", now=now)
            close_open_steps(b)
            notify(
                b.booked_for,
                Kind.EXPIRED,
                f"Request expired · {b.resource.name}",
                "It wasn't approved before the start time, so the slot was released.",
                b.get_absolute_url(),
            )
            n += 1
    return n


def turnaround_hours(qs=None):
    """Average hours from request to decision for decided approval steps."""
    from django.db.models import Avg, DurationField, ExpressionWrapper, F

    qs = qs if qs is not None else Approval.objects.all()
    avg = (
        qs.filter(decided_at__isnull=False, decision__in=[Decision.APPROVED, Decision.REJECTED])
        .annotate(t=ExpressionWrapper(F("decided_at") - F("booking__created_at"), output_field=DurationField()))
        .aggregate(a=Avg("t"))["a"]
    )
    return round(avg.total_seconds() / 3600, 1) if avg else None
