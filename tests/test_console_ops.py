"""
Operations console (/manage/): every screen renders for the people who use it, students are
turned away, object scope is enforced (a custodian can't act on resources they don't look
after), and the actions change real state through the services.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.approvals.models import Approval, ApprovalStep, ApprovalWorkflow, ApproverRole, Decision
from apps.bookings import services as bookings
from apps.bookings.models import Booking, BookingSlot, BookingStatus, SlotKind
from apps.checkins.models import NoShow, Restriction
from apps.core.timeutil import trange
from apps.inventory.models import InventoryItem
from apps.maintenance.models import BreakdownReport, MaintenanceWindow, ReportStatus, WindowStatus

from .conftest import at

pytestmark = pytest.mark.django_db

PAGES = ["manage:home", "manage:approvals", "manage:board", "manage:no_shows", "manage:maintenance",
         "manage:inventory"]


@pytest.fixture
def day(monday):
    return monday


@pytest.fixture
def custodian_client(client, custodian):
    client.force_login(custodian)
    return client


@pytest.fixture
def fm_client(client, facility_manager):
    client.force_login(facility_manager)
    return client


@pytest.fixture
def custodian_workflow(lpu, room_type):
    w = ApprovalWorkflow.objects.create(institution=lpu, name="Classrooms need the custodian", resource_type=room_type)
    ApprovalStep.objects.create(workflow=w, order=1, approver_role=ApproverRole.CUSTODIAN, sla_hours=4)
    return w


def book(user, resource, d, h1, h2, **kw):
    return bookings.create_booking(
        requester=user, resource=resource, start=at(d, h1), end=at(d, h2), title="Study group", notify=False, **kw
    )


def pending_step(booking):
    return Approval.objects.get(booking=booking, decision=Decision.PENDING)


# ── Rendering and access ────────────────────────────────────────────────────


@pytest.mark.parametrize("name", PAGES)
def test_pages_render_for_custodian(custodian_client, room, name):
    assert custodian_client.get(reverse(name)).status_code == 200


@pytest.mark.parametrize("name", PAGES)
def test_pages_render_for_facility_manager(fm_client, room, room2, name):
    assert fm_client.get(reverse(name)).status_code == 200


@pytest.mark.parametrize("name", PAGES)
def test_students_are_refused(client, student, name):
    client.force_login(student)
    assert client.get(reverse(name)).status_code == 403


def test_dept_head_sees_department_pages_but_not_no_shows(client, make_user, room):
    client.force_login(make_user(Role.DEPT_HEAD))
    for name in ("manage:home", "manage:approvals", "manage:board"):
        assert client.get(reverse(name)).status_code == 200
    assert client.get(reverse("manage:no_shows")).status_code == 403


def test_pages_render_with_live_data(fm_client, custodian_workflow, student, room, room2, day, lpu, custodian):
    """Smoke the full screens with something in every list."""
    b = book(student, room, day, 10, 11)
    ok = book(student, room2, day, 12, 13)
    NoShow.objects.create(institution=lpu, booking=ok, user=student, resource=room2, detected_at=timezone.now(),
                          released_minutes=45)
    Restriction.objects.create(institution=lpu, user=student, starts_at=timezone.now() - timedelta(hours=1),
                               ends_at=timezone.now() + timedelta(days=3), reason="3 no-shows in 30 days")
    BreakdownReport.objects.create(institution=lpu, resource=room, reported_by=student, summary="Projector dead")
    InventoryItem.objects.create(institution=lpu, name="Whiteboard markers", sku="MRK", kind="consumable",
                                 resource=room, quantity_total=20, quantity_available=2, reorder_level=5)
    pages = {name: fm_client.get(reverse(name)) for name in PAGES}
    assert all(r.status_code == 200 for r in pages.values())
    assert b"Study group" in pages["manage:approvals"].content
    assert b"Projector dead" in pages["manage:maintenance"].content
    assert b"Whiteboard markers" in pages["manage:inventory"].content
    assert b"3 no-shows in 30 days" in pages["manage:no_shows"].content
    assert b"low on stock" in pages["manage:home"].content
    assert fm_client.get(reverse("manage:board"), {"date": day.isoformat()}).status_code == 200
    assert b.status == BookingStatus.PENDING


def test_board_htmx_refresh_returns_body_only(custodian_client, room):
    resp = custodian_client.get(reverse("manage:board"), HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'id="board-body"' in html and 'hx-trigger="every 60s"' in html
    assert "<html" not in html
    assert "Room 34-301" in html


def test_board_shows_only_custodians_resources(custodian_client, room, room2):
    html = custodian_client.get(reverse("manage:board")).content.decode()
    assert "Room 34-301" in html and "Room 34-302" not in html


# ── Approvals ───────────────────────────────────────────────────────────────


def test_custodian_queue_is_scoped(custodian_client, custodian_workflow, student, room, room2, day):
    book(student, room, day, 10, 11)
    book(student, room2, day, 14, 15)
    html = custodian_client.get(reverse("manage:approvals")).content.decode()
    assert "Room 34-301" in html and "Room 34-302" not in html


def test_custodian_cannot_decide_for_resource_they_dont_manage(custodian_client, custodian_workflow, student,
                                                                room2, day):
    b = book(student, room2, day, 10, 11)
    step = pending_step(b)
    resp = custodian_client.post(reverse("manage:approval_decide", args=[step.pk]), {"action": "approve"})
    assert resp.status_code == 404
    b.refresh_from_db()
    assert b.status == BookingStatus.PENDING


def test_approve_via_view_confirms_booking(custodian_client, custodian_workflow, student, room, day):
    b = book(student, room, day, 10, 11)
    resp = custodian_client.post(reverse("manage:approval_decide", args=[pending_step(b).pk]), {"action": "approve"})
    assert resp.status_code == 302
    b.refresh_from_db()
    assert b.status == BookingStatus.APPROVED


def test_reject_needs_a_reason_then_rejects(custodian_client, custodian_workflow, student, room, day):
    b = book(student, room, day, 10, 11)
    step = pending_step(b)
    url = reverse("manage:approval_decide", args=[step.pk])
    resp = custodian_client.post(url, {"action": "reject", "comment": ""}, HTTP_HX_REQUEST="true")
    assert resp.status_code == 200 and b"reason" in resp.content
    b.refresh_from_db()
    assert b.status == BookingStatus.PENDING

    resp = custodian_client.post(url, {"action": "reject", "comment": "Hall booked for exams"}, HTTP_HX_REQUEST="true")
    assert resp.status_code == 200 and b"Rejected" in resp.content
    b.refresh_from_db()
    assert b.status == BookingStatus.REJECTED
    assert b.status_reason == "Hall booked for exams"


def test_facility_manager_can_decide_anywhere(fm_client, custodian_workflow, student, room2, day):
    b = book(student, room2, day, 10, 11)
    fm_client.post(reverse("manage:approval_decide", args=[pending_step(b).pk]), {"action": "approve"})
    b.refresh_from_db()
    assert b.status == BookingStatus.APPROVED


# ── No-shows ────────────────────────────────────────────────────────────────


@pytest.fixture
def no_show_on(lpu, student, day):
    def _make(resource, h=10):
        b = book(student, resource, day, h, h + 1)
        Booking.objects.filter(pk=b.pk).update(status=BookingStatus.NO_SHOW)
        return NoShow.objects.create(institution=lpu, booking=b, user=student, resource=resource,
                                     detected_at=timezone.now(), released_minutes=45)

    return _make


def test_custodian_cannot_forgive_elsewhere(custodian_client, no_show_on, room2):
    ns = no_show_on(room2)
    resp = custodian_client.post(reverse("manage:no_show_forgive", args=[ns.pk]), {"reason": "Room was locked"})
    assert resp.status_code == 404
    ns.refresh_from_db()
    assert not ns.forgiven


def test_forgive_requires_reason_and_works(custodian_client, no_show_on, room):
    ns = no_show_on(room)
    url = reverse("manage:no_show_forgive", args=[ns.pk])
    custodian_client.post(url, {"reason": " "})
    ns.refresh_from_db()
    assert not ns.forgiven
    assert custodian_client.post(url, {"reason": "Room was locked"}).status_code == 302
    ns.refresh_from_db()
    assert ns.forgiven and ns.forgiven_reason == "Room was locked"


def test_lift_restriction_scoped_to_people_seen_on_your_resources(custodian_client, no_show_on, lpu, student,
                                                                   make_user, room):
    other = make_user(Role.STUDENT)
    no_show_on(room)
    now = timezone.now()
    mine = Restriction.objects.create(institution=lpu, user=student, starts_at=now - timedelta(hours=1),
                                      ends_at=now + timedelta(days=7), reason="3 no-shows")
    theirs = Restriction.objects.create(institution=lpu, user=other, starts_at=now - timedelta(hours=1),
                                        ends_at=now + timedelta(days=7), reason="3 no-shows")
    assert custodian_client.post(reverse("manage:restriction_lift", args=[theirs.pk])).status_code == 404
    assert custodian_client.post(reverse("manage:restriction_lift", args=[mine.pk])).status_code == 302
    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert mine.lifted_at is not None and theirs.lifted_at is None


# ── Maintenance ─────────────────────────────────────────────────────────────


def _schedule_post(resource, d, h1, h2, step="preview", **extra):
    data = {"resource": resource.pk, "start_date": d.isoformat(), "start_time": f"{h1:02d}:00",
            "end_date": d.isoformat(), "end_time": f"{h2:02d}:00", "kind": "repair", "title": "Projector repair",
            "step": step}
    if step == "confirm":
        data["checked"] = f"{resource.pk}|{at(d, h1).isoformat()}|{at(d, h2).isoformat()}"
    data.update(extra)
    return data


def test_schedule_preview_then_confirm_displaces_booking(custodian_client, student, room, day):
    b = book(student, room, day, 10, 11)
    url = reverse("manage:maintenance_schedule")

    resp = custodian_client.post(url, _schedule_post(room, day, 9, 12))
    assert resp.status_code == 200
    assert b"1 booking will be cancelled" in resp.content
    b.refresh_from_db()
    assert b.status == BookingStatus.APPROVED and not MaintenanceWindow.objects.exists()

    resp = custodian_client.post(url, _schedule_post(room, day, 9, 12, step="confirm"))
    assert resp.status_code == 302
    b.refresh_from_db()
    assert b.status == BookingStatus.CANCELLED
    w = MaintenanceWindow.objects.get()
    assert w.displaced_bookings == 1 and w.resource == room


def test_confirm_with_changed_details_previews_again(custodian_client, room, day):
    data = _schedule_post(room, day, 9, 12, step="confirm")
    data["end_time"] = "13:00"
    resp = custodian_client.post(reverse("manage:maintenance_schedule"), data)
    assert resp.status_code == 200 and b"You changed the details" in resp.content
    assert not MaintenanceWindow.objects.exists()


def test_schedule_refuses_over_a_timetabled_class(custodian_client, room, day):
    BookingSlot.objects.create(resource=room, period=trange(at(day, 14), at(day, 15)), kind=SlotKind.CLASS,
                               source_type="timetable_entry", source_id=1, label="CSE326 Lecture")
    url = reverse("manage:maintenance_schedule")
    preview = custodian_client.post(url, _schedule_post(room, day, 13, 16))
    assert b"CSE326 Lecture" in preview.content and b"Schedule and cancel" not in preview.content
    resp = custodian_client.post(url, _schedule_post(room, day, 13, 16, step="confirm"))
    assert resp.status_code == 200 and b"Not scheduled" in resp.content and b"CSE326 Lecture" in resp.content
    assert not MaintenanceWindow.objects.exists()


def test_custodian_cannot_schedule_on_unmanaged_resource(custodian_client, room, room2, day):
    resp = custodian_client.post(reverse("manage:maintenance_schedule"),
                                 _schedule_post(room2, day, 9, 10, step="confirm"))
    assert resp.status_code == 200 and b"Pick one of the resources you look after" in resp.content
    assert not MaintenanceWindow.objects.exists()


def test_window_and_report_actions(custodian_client, custodian, facility_manager, student, room, room2, lpu, day):
    from apps.maintenance import services as maintenance

    w = maintenance.schedule(room, at(day, 9), at(day, 10), title="Deep clean", actor=custodian)
    other = maintenance.schedule(room2, at(day, 9), at(day, 10), title="Deep clean", actor=facility_manager)
    assert custodian_client.post(reverse("manage:maintenance_window", args=[other.pk, "cancel"])).status_code == 404
    assert custodian_client.post(reverse("manage:maintenance_window", args=[w.pk, "cancel"])).status_code == 302
    w.refresh_from_db()
    assert w.status == WindowStatus.CANCELLED

    r = BreakdownReport.objects.create(institution=lpu, resource=room, reported_by=student, summary="AC leaking")
    custodian_client.post(reverse("manage:maintenance_report", args=[r.pk, "acknowledge"]))
    r.refresh_from_db()
    assert r.status == ReportStatus.ACKNOWLEDGED
    custodian_client.post(reverse("manage:maintenance_report", args=[r.pk, "resolve"]), {"resolution": "Fixed pipe"})
    r.refresh_from_db()
    assert r.status == ReportStatus.RESOLVED and r.resolution == "Fixed pipe"


# ── Inventory ───────────────────────────────────────────────────────────────


@pytest.fixture
def markers(lpu, room):
    return InventoryItem.objects.create(institution=lpu, name="Markers", sku="MRK-1", kind="consumable",
                                        resource=room, quantity_total=10, quantity_available=2, reorder_level=5)


def test_restock_changes_stock(custodian_client, markers):
    resp = custodian_client.post(reverse("manage:inventory_restock", args=[markers.pk]), {"qty": "10", "note": "PO 1"})
    assert resp.status_code == 302
    markers.refresh_from_db()
    assert markers.quantity_available == 12
    assert markers.movements.get().note == "PO 1"


def test_restock_rejects_bad_quantity(custodian_client, markers):
    custodian_client.post(reverse("manage:inventory_restock", args=[markers.pk]), {"qty": "0"})
    custodian_client.post(reverse("manage:inventory_restock", args=[markers.pk]), {"qty": "lots"})
    markers.refresh_from_db()
    assert markers.quantity_available == 2


def test_custodian_cannot_restock_elsewhere(custodian_client, lpu, room2):
    item = InventoryItem.objects.create(institution=lpu, name="Cables", sku="CBL-1", kind="accessory", resource=room2,
                                        quantity_total=4, quantity_available=4, reorder_level=1)
    assert custodian_client.post(reverse("manage:inventory_restock", args=[item.pk]), {"qty": "3"}).status_code == 404
    item.refresh_from_db()
    assert item.quantity_available == 4


def test_low_stock_filter(custodian_client, markers, lpu, room):
    InventoryItem.objects.create(institution=lpu, name="Dusters", sku="DST-1", kind="consumable", resource=room,
                                 quantity_total=10, quantity_available=10, reorder_level=2)
    html = custodian_client.get(reverse("manage:inventory"), {"low": "1"}).content.decode()
    assert "Markers" in html and "Dusters" not in html
