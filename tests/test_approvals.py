"""
M5 approval workflows: resolution, multi-step chains, rejection, expiry, queue scoping —
and the acceptance criterion "approval workflows configurable per resource type without
deployment" (a workflow is a row; editing it changes the next booking's behaviour).
"""

from datetime import timedelta

import pytest

from apps.accounts.models import Department, Role
from apps.approvals import services as approvals
from apps.approvals.models import Approval, ApprovalStep, ApprovalWorkflow, ApproverRole, Decision
from apps.audit.models import AuditLog
from apps.bookings import services as bookings
from apps.bookings.models import BookingSlot, BookingStatus
from apps.catalogue.models import Custodian, Resource
from apps.core.errors import InvalidTransition, NotPermitted
from apps.notifications.models import Kind, Notification

from .conftest import at

pytestmark = pytest.mark.django_db


def book(user, resource, d, h1, h2, now, **kw):
    return bookings.create_booking(
        requester=user, resource=resource, start=at(d, *h1), end=at(d, *h2), title="Seminar", now=now, **kw
    )


def workflow(lpu, name, *steps, resource=None, resource_type=None, **kw):
    w = ApprovalWorkflow.objects.create(
        institution=lpu, name=name, resource=resource, resource_type=resource_type, **kw
    )
    for i, step in enumerate(steps, start=1):
        role, user = step if isinstance(step, tuple) else (step, None)
        ApprovalStep.objects.create(workflow=w, order=i, approver_role=role, approver_user=user)
    return w


def steps(booking):
    return list(Approval.objects.filter(booking=booking).order_by("step_order"))


@pytest.fixture
def dept_head(make_user):
    return make_user(Role.DEPT_HEAD)


@pytest.fixture
def ece(lpu):
    return Department.objects.create(institution=lpu, code="ECE", name="Electronics")


@pytest.fixture
def lab(lpu, lab_type, block34, cse):
    return Resource.objects.create(
        institution=lpu, type=lab_type, code="34-LAB1", name="Lab 1", capacity=40, building=block34, department=cse
    )


# ── Resolution ──────────────────────────────────────────────────────────────


def test_no_workflow_confirms_instantly(student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    assert b.status == BookingStatus.APPROVED
    [s] = steps(b)
    assert s.decision == Decision.SKIPPED
    assert s.comment == "No approval required"


def test_specificity_resource_beats_type_beats_any(lpu, student, room, room2, lab, room_type):
    any_wf = workflow(lpu, "Any", ApproverRole.FACILITY_MANAGER, priority=500)
    type_wf = workflow(lpu, "Classrooms", ApproverRole.CUSTODIAN, resource_type=room_type, priority=300)
    res_wf = workflow(lpu, "Room 301", ApproverRole.DEPT_HEAD, resource=room, priority=1)
    assert approvals.resolve_workflow(room, student, 1, 60) == res_wf
    assert approvals.resolve_workflow(room2, student, 1, 60) == type_wf
    assert approvals.resolve_workflow(lab, student, 1, 60) == any_wf


def test_priority_breaks_ties_within_a_specificity(lpu, student, room, room_type):
    workflow(lpu, "Low", ApproverRole.CUSTODIAN, resource_type=room_type, priority=10)
    high = workflow(lpu, "High", ApproverRole.DEPT_HEAD, resource_type=room_type, priority=200)
    assert approvals.resolve_workflow(room, student, 1, 60) == high


def test_inactive_and_stepless_workflows_do_not_block(lpu, student, room, room_type, monday, now):
    workflow(lpu, "Off", ApproverRole.CUSTODIAN, resource_type=room_type, active=False)
    workflow(lpu, "No steps", resource=room)
    assert approvals.resolve_workflow(room, student, 1, 60) is None
    assert book(student, room, monday, (10,), (11,), now).status == BookingStatus.APPROVED


def test_requester_roles_condition(lpu, student, faculty, room, room_type, monday, now):
    workflow(lpu, "Students need OK", ApproverRole.CUSTODIAN, resource_type=room_type, requester_roles=["student"])
    assert book(student, room, monday, (10,), (11,), now).status == BookingStatus.PENDING
    assert book(faculty, room, monday, (12,), (13,), now).status == BookingStatus.APPROVED


def test_min_attendees_condition_is_inclusive(lpu, student, make_user, room, room_type, monday, now):
    workflow(lpu, "Big groups", ApproverRole.CUSTODIAN, resource_type=room_type, min_attendees=30)
    assert book(student, room, monday, (10,), (11,), now, attendees=29).status == BookingStatus.APPROVED
    assert book(make_user(), room, monday, (12,), (13,), now, attendees=30).status == BookingStatus.PENDING


def test_min_duration_condition_is_inclusive(lpu, student, make_user, room, room_type, monday, now):
    workflow(lpu, "Long", ApproverRole.CUSTODIAN, resource_type=room_type, min_duration_minutes=120)
    assert book(student, room, monday, (10,), (11, 30), now).status == BookingStatus.APPROVED
    assert book(make_user(), room, monday, (12,), (14,), now).status == BookingStatus.PENDING


def test_auto_approve_rule_confirms_and_leaves_a_trail(lpu, student, room, room_type, monday, now):
    workflow(lpu, "Classrooms need OK", ApproverRole.CUSTODIAN, resource_type=room_type)
    workflow(lpu, "301 is open", resource=room, auto_approve=True)
    b = book(student, room, monday, (10,), (11,), now)
    assert b.status == BookingStatus.APPROVED
    [s] = steps(b)
    assert s.decision == Decision.SKIPPED
    assert s.comment == "Auto-confirmed by rule: 301 is open"


def test_changing_a_workflow_row_changes_the_next_booking(lpu, student, make_user, room, room_type, monday, now):
    """Acceptance criterion: approval workflows configurable per resource type without deployment."""
    first = book(student, room, monday, (8,), (9,), now)
    assert first.status == BookingStatus.APPROVED

    wf = workflow(lpu, "Classrooms", ApproverRole.CUSTODIAN, resource_type=room_type)
    second = book(make_user(), room, monday, (9,), (10,), now)
    assert second.status == BookingStatus.PENDING

    wf.auto_approve = True
    wf.save()
    assert book(make_user(), room, monday, (10,), (11,), now).status == BookingStatus.APPROVED

    wf.auto_approve = False
    wf.requester_roles = ["faculty"]
    wf.save()
    assert book(make_user(), room, monday, (11,), (12,), now).status == BookingStatus.APPROVED

    wf.requester_roles = []
    wf.save()
    assert book(make_user(), room, monday, (12,), (13,), now).status == BookingStatus.PENDING

    wf.active = False
    wf.save()
    assert book(make_user(), room, monday, (13,), (14,), now).status == BookingStatus.APPROVED

    # Existing bookings are not rewritten by the change.
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.status, second.status) == (BookingStatus.APPROVED, BookingStatus.PENDING)


# ── Multi-step chain ────────────────────────────────────────────────────────


def test_two_step_chain_custodian_then_dept_head(lpu, student, custodian, dept_head, room, room_type, monday, now):
    workflow(lpu, "Two-step", ApproverRole.CUSTODIAN, ApproverRole.DEPT_HEAD, resource_type=room_type)
    b = book(student, room, monday, (10,), (11,), now)
    assert b.status == BookingStatus.PENDING
    assert BookingSlot.objects.filter(booking=b).exists(), "a pending request holds the slot"
    s1, s2 = steps(b)
    assert (s1.decision, s2.decision) == (Decision.PENDING, Decision.WAITING)
    assert s1.due_at == now + timedelta(hours=24)
    assert Notification.objects.filter(user=custodian, kind=Kind.APPROVAL_REQUIRED).count() == 1
    assert not Notification.objects.filter(user=dept_head, kind=Kind.APPROVAL_REQUIRED).exists()
    assert Notification.objects.filter(user=student, kind=Kind.APPROVAL_PENDING).exists()

    # The dept head cannot jump the queue.
    with pytest.raises(NotPermitted):
        approvals.decide(s1, dept_head, approve=True, now=now)

    decided_at = now + timedelta(hours=1)
    approvals.decide(s1, custodian, approve=True, comment="fine", now=decided_at)
    b.refresh_from_db()
    s1, s2 = steps(b)
    assert b.status == BookingStatus.PENDING
    assert (s1.decision, s2.decision) == (Decision.APPROVED, Decision.PENDING)
    assert s1.decided_by == custodian
    assert s2.due_at == decided_at + timedelta(hours=24)
    assert Notification.objects.filter(user=dept_head, kind=Kind.APPROVAL_REQUIRED).count() == 1

    # Step one's approver cannot decide step two.
    with pytest.raises(NotPermitted):
        approvals.decide(s2, custodian, approve=True, now=decided_at)

    approvals.decide(s2, dept_head, approve=True, now=decided_at)
    b.refresh_from_db()
    assert b.status == BookingStatus.APPROVED
    assert b.decided_at == decided_at
    assert BookingSlot.objects.filter(booking=b).exists()
    assert Notification.objects.filter(user=student, kind=Kind.APPROVED).count() == 1

    # A decided step cannot be decided again.
    with pytest.raises(NotPermitted):
        approvals.decide(s2, dept_head, approve=False, comment="changed my mind", now=decided_at)

    audit = AuditLog.objects.filter(target_type="bookings.booking", target_id=str(b.pk), action="approval.approve")
    assert sorted(audit.values_list("actor_id", flat=True)) == sorted([custodian.pk, dept_head.pk])


def test_reject_needs_a_comment_frees_the_slot_and_skips_the_rest(
    lpu, student, make_user, custodian, dept_head, room, room_type, monday, now
):
    workflow(lpu, "Two-step", ApproverRole.CUSTODIAN, ApproverRole.DEPT_HEAD, resource_type=room_type)
    b = book(student, room, monday, (10,), (11,), now)
    s1, _ = steps(b)

    with pytest.raises(InvalidTransition, match="reason"):
        approvals.decide(s1, custodian, approve=False, comment="   ", now=now)
    b.refresh_from_db()
    s1.refresh_from_db()
    assert b.status == BookingStatus.PENDING
    assert s1.decision == Decision.PENDING

    approvals.decide(s1, custodian, approve=False, comment="Room reserved for exams", now=now)
    b.refresh_from_db()
    s1, s2 = steps(b)
    assert b.status == BookingStatus.REJECTED
    assert b.status_reason == "Room reserved for exams"
    assert (s1.decision, s2.decision) == (Decision.REJECTED, Decision.SKIPPED)
    assert not BookingSlot.objects.filter(booking=b).exists()
    n = Notification.objects.get(user=student, kind=Kind.REJECTED)
    assert "Room reserved for exams" in n.body
    assert AuditLog.objects.filter(target_id=str(b.pk), action="approval.reject", actor=custodian).exists()
    # The dept head never gets asked.
    assert not Notification.objects.filter(user=dept_head, kind=Kind.APPROVAL_REQUIRED).exists()

    # The slot is really free: someone else can take it (the workflow applies to them too).
    other = book(make_user(), room, monday, (10,), (11,), now)
    assert other.status == BookingStatus.PENDING


def test_named_user_step(lpu, student, faculty, make_user, room, room_type, monday, now):
    warden = make_user(Role.CUSTODIAN)  # approve_bookings capability, but not this room's custodian
    workflow(lpu, "Warden", (ApproverRole.USER, warden), resource_type=room_type)
    b = book(student, room, monday, (10,), (11,), now)
    [s] = steps(b)
    assert list(approvals.approvers_for(s)) == [warden]
    assert list(approvals.queue_for(warden)) == [s]
    approvals.decide(s, warden, approve=True, now=now)
    b.refresh_from_db()
    assert b.status == BookingStatus.APPROVED


# ── Who may decide ──────────────────────────────────────────────────────────


def test_non_approvers_cannot_decide(lpu, student, faculty, make_user, room, room_type, monday, now):
    workflow(lpu, "Custodian", ApproverRole.CUSTODIAN, resource_type=room_type)
    b = book(student, room, monday, (10,), (11,), now)
    [s] = steps(b)
    other_custodian = make_user(Role.CUSTODIAN)
    same_dept_head = make_user(Role.DEPT_HEAD)  # can approve, but this step belongs to the custodian
    for outsider in (student, faculty, make_user(), other_custodian, same_dept_head):
        with pytest.raises(NotPermitted):
            approvals.decide(s, outsider, approve=True, now=now)
    b.refresh_from_db()
    assert b.status == BookingStatus.PENDING


def test_facility_manager_can_decide_any_step(lpu, student, facility_manager, room, room_type, monday, now):
    workflow(lpu, "Custodian", ApproverRole.CUSTODIAN, resource_type=room_type)
    b = book(student, room, monday, (10,), (11,), now)
    [s] = steps(b)
    approvals.decide(s, facility_manager, approve=True, now=now)
    b.refresh_from_db()
    assert b.status == BookingStatus.APPROVED


def test_queue_for_custodian_scoping(
    lpu, student, make_user, custodian, facility_manager, room, room_type, block34, ece, monday, now
):
    other_room = Resource.objects.create(
        institution=lpu,
        type=room_type,
        code="34-999",
        name="Room 34-999",
        capacity=60,
        building=block34,
        department=ece,
    )
    other_custodian = make_user(Role.CUSTODIAN)
    Custodian.objects.create(resource=other_room, user=other_custodian)
    workflow(lpu, "Custodian", ApproverRole.CUSTODIAN, resource_type=room_type)
    mine = steps(book(student, room, monday, (10,), (11,), now))[0]
    theirs = steps(book(make_user(), other_room, monday, (10,), (11,), now))[0]

    assert list(approvals.queue_for(custodian)) == [mine]
    assert list(approvals.queue_for(other_custodian)) == [theirs]
    assert set(approvals.queue_for(facility_manager)) == {mine, theirs}
    assert not approvals.queue_for(student).exists()
    with pytest.raises(NotPermitted):
        approvals.decide(theirs, custodian, approve=True, now=now)


def test_queue_for_dept_head_scoping(lpu, student, make_user, dept_head, room, room_type, block34, ece, monday, now):
    ece_room = Resource.objects.create(
        institution=lpu,
        type=room_type,
        code="34-777",
        name="Room 34-777",
        capacity=60,
        building=block34,
        department=ece,
    )
    ece_head = make_user(Role.DEPT_HEAD, department=ece)
    workflow(lpu, "HoD", ApproverRole.DEPT_HEAD, resource_type=room_type)
    cse_step = steps(book(student, room, monday, (10,), (11,), now))[0]
    ece_step = steps(book(make_user(), ece_room, monday, (10,), (11,), now))[0]

    assert list(approvals.queue_for(dept_head)) == [cse_step]
    assert list(approvals.queue_for(ece_head)) == [ece_step]
    with pytest.raises(NotPermitted):
        approvals.decide(ece_step, dept_head, approve=True, now=now)
    approvals.decide(ece_step, ece_head, approve=True, now=now)
    assert not approvals.queue_for(ece_head).exists()


def test_queue_hides_steps_of_cancelled_requests(lpu, student, custodian, room, room_type, monday, now):
    workflow(lpu, "Custodian", ApproverRole.CUSTODIAN, resource_type=room_type)
    b = book(student, room, monday, (10,), (11,), now)
    [s] = steps(b)
    bookings.cancel_booking(b, student, now=now)
    assert not approvals.queue_for(custodian).exists()
    s.refresh_from_db()
    assert s.decision == Decision.SKIPPED
    with pytest.raises((NotPermitted, InvalidTransition)):
        approvals.decide(s, custodian, approve=True, now=now)
    b.refresh_from_db()
    assert b.status == BookingStatus.CANCELLED
    assert not BookingSlot.objects.filter(booking=b).exists()


# ── Expiry ──────────────────────────────────────────────────────────────────


def test_deciding_after_the_start_expires_the_request(lpu, student, make_user, custodian, room, room_type, monday, now):
    workflow(lpu, "Custodian", ApproverRole.CUSTODIAN, resource_type=room_type)
    b = book(student, room, monday, (10,), (11,), now)
    [s] = steps(b)
    with pytest.raises(InvalidTransition, match="expired"):
        approvals.decide(s, custodian, approve=True, now=at(monday, 10))
    b.refresh_from_db()
    s.refresh_from_db()
    assert b.status == BookingStatus.EXPIRED, "the expiry must persist even though decide() raised"
    assert s.decision == Decision.SKIPPED
    assert not BookingSlot.objects.filter(booking=b).exists()


def test_expire_stale_sweep_releases_the_slot(lpu, student, make_user, custodian, room, room2, room_type, monday, now):
    workflow(lpu, "Custodian", ApproverRole.CUSTODIAN, resource_type=room_type)
    starting = book(student, room, monday, (10,), (11,), now)
    later = book(student, room2, monday, (14,), (15,), now)

    assert approvals.expire_stale(now=at(monday, 9, 59)) == 0
    assert approvals.expire_stale(now=at(monday, 10)) == 1
    starting.refresh_from_db()
    later.refresh_from_db()
    assert starting.status == BookingStatus.EXPIRED
    assert later.status == BookingStatus.PENDING
    assert not BookingSlot.objects.filter(booking=starting).exists()
    assert Notification.objects.filter(user=student, kind=Kind.EXPIRED).count() == 1
    assert all(a.decision == Decision.SKIPPED for a in steps(starting))
    assert not approvals.queue_for(custodian).filter(booking=starting).exists()

    # Idempotent: a second sweep changes nothing.
    assert approvals.expire_stale(now=at(monday, 10, 1)) == 0

    # The released time is bookable by someone else straight away.
    ApprovalWorkflow.objects.update(active=False)
    walk_in = book(make_user(), room, monday, (10,), (11,), at(monday, 10))
    assert walk_in.status == BookingStatus.APPROVED
