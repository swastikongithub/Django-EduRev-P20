"""
REST API v1 integration tests: every endpoint, happy path plus the authorisation-failure paths.

Wall-clock note: requests run at the real "now", so bookings made through the API use the
`monday` fixture (7-13 days ahead). Check-in tests build a booking around the real now via the ORM.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role
from apps.approvals.models import ApprovalStep, ApprovalWorkflow
from apps.bookings import services as bookings
from apps.bookings.models import Booking, BookingSlot, BookingStatus, SlotKind
from apps.catalogue.models import Custodian, Feature, Resource, ResourceType
from apps.checkins.models import Restriction
from apps.core.models import Institution
from apps.core.timeutil import trange
from apps.maintenance.models import MaintenanceWindow
from apps.notifications.models import Notification
from apps.rules.models import Quota
from apps.timetable.models import AcademicTerm

from .conftest import at

pytestmark = pytest.mark.django_db

API = "/api/v1"


def client_for(user=None) -> APIClient:
    c = APIClient()
    if user is not None:
        c.force_login(user)
    return c


def assert_error(resp, status, code=None):
    assert resp.status_code == status, resp.content
    body = resp.json()
    assert set(body) == {"error"}, body
    assert set(body["error"]) == {"code", "message", "detail"}
    assert body["error"]["message"]
    if code is not None:
        assert body["error"]["code"] == code, body
    return body["error"]


def book_api(user, resource, d, h1, h2, **extra):
    payload = {"resource": resource.pk, "start": at(d, *h1).isoformat(), "end": at(d, *h2).isoformat(), **extra}
    return client_for(user).post(f"{API}/bookings/", payload, format="json")


def book(user, resource, d, h1, h2, now, **kw):
    return bookings.create_booking(
        requester=user, resource=resource, start=at(d, *h1), end=at(d, *h2), title="Study", now=now, notify=False, **kw
    )


@pytest.fixture
def custodian_workflow(lpu, room_type):
    wf = ApprovalWorkflow.objects.create(institution=lpu, name="Rooms need the custodian", resource_type=room_type)
    ApprovalStep.objects.create(workflow=wf, order=1, approver_role="custodian")
    return wf


@pytest.fixture
def other_custodian(make_user, room2):
    user = make_user(Role.CUSTODIAN)
    Custodian.objects.create(resource=room2, user=user)
    return user


@pytest.fixture
def dept_head(make_user):
    return make_user(Role.DEPT_HEAD)


@pytest.fixture
def pending_booking(student, room, monday, now, custodian_workflow):
    b = book(student, room, monday, (10,), (11,), now)
    assert b.status == BookingStatus.PENDING
    return b


@pytest.fixture
def live_booking(lpu, student, room):
    """An approved booking that started two minutes ago (check-in window open right now)."""
    start = timezone.now() - timedelta(minutes=2)
    b = Booking.objects.create(
        institution=lpu,
        resource=room,
        requester=student,
        booked_for=student,
        title="Right now",
        period=trange(start, start + timedelta(hours=1)),
        status=BookingStatus.APPROVED,
    )
    BookingSlot.objects.create(resource=room, period=b.period, kind=SlotKind.BOOKING, booking=b, label=b.title)
    return b


# ── Envelope and authentication ─────────────────────────────────────────────

ANON_ENDPOINTS = [
    ("get", "/resources/"),
    ("get", "/resources/1/"),
    ("get", "/resources/1/availability/"),
    ("post", "/resources/1/report-breakdown/"),
    ("get", "/bookings/"),
    ("post", "/bookings/"),
    ("get", "/bookings/LR-AAAAAA/"),
    ("post", "/bookings/LR-AAAAAA/cancel/"),
    ("post", "/bookings/LR-AAAAAA/approve/"),
    ("post", "/bookings/LR-AAAAAA/reject/"),
    ("post", "/bookings/LR-AAAAAA/check-in/"),
    ("post", "/bookings/LR-AAAAAA/check-out/"),
    ("get", "/bookings/LR-AAAAAA/ics/"),
    ("post", "/series/"),
    ("post", "/series/preview/"),
    ("get", "/approvals/"),
    ("get", "/maintenance/"),
    ("post", "/maintenance/"),
    ("post", "/maintenance/1/cancel/"),
    ("post", "/maintenance/1/complete/"),
    ("get", "/timetable/publications/"),
    ("post", "/timetable/publications/"),
    ("get", "/analytics/utilisation/"),
    ("get", "/me/"),
    ("get", "/notifications/"),
    ("post", "/notifications/read-all/"),
]


@pytest.mark.parametrize(("method", "path"), ANON_ENDPOINTS)
def test_anonymous_requests_are_refused_on_every_endpoint(lpu, method, path):
    resp = (
        getattr(client_for(), method)(API + path, {}, format="json")
        if method == "post"
        else client_for().get(API + path)
    )
    assert resp.status_code in (401, 403)
    assert resp.json()["error"]["code"] == "not_authenticated"


def test_schema_and_docs_are_served(student):
    resp = client_for(student).get(f"{API}/schema/")
    assert resp.status_code == 200
    assert b"/api/v1/bookings/{reference}/approve/" in resp.content


# ── Resources ───────────────────────────────────────────────────────────────


def test_resource_list_and_filters(student, room, room2, lab_type, lpu):
    projector = Feature.objects.create(institution=lpu, name="Projector")
    room.features.add(projector)
    lab = Resource.objects.create(institution=lpu, type=lab_type, code="LAB-1", name="Systems Lab", capacity=30)
    c = client_for(student)

    codes = lambda resp: sorted(r["code"] for r in resp.json()["results"])  # noqa: E731
    resp = c.get(f"{API}/resources/")
    assert resp.status_code == 200
    assert codes(resp) == ["34-301", "34-302", "LAB-1"]
    assert codes(c.get(f"{API}/resources/", {"type": "classroom"})) == ["34-301", "34-302"]
    assert codes(c.get(f"{API}/resources/", {"category": "lab"})) == ["LAB-1"]
    assert codes(c.get(f"{API}/resources/", {"building": "34"})) == ["34-301", "34-302"]
    assert codes(c.get(f"{API}/resources/", {"min_capacity": 50})) == ["34-301", "34-302"]
    assert codes(c.get(f"{API}/resources/", {"features": "projector"})) == ["34-301"]
    assert codes(c.get(f"{API}/resources/", {"features": str(projector.pk)})) == ["34-301"]
    assert codes(c.get(f"{API}/resources/", {"q": "systems"})) == ["LAB-1"]
    assert codes(c.get(f"{API}/resources/", {"q": "Sytems Lab"})) == ["LAB-1"]  # trigram tolerates typos
    assert c.get(f"{API}/resources/", {"q": "34-302"}).json()["results"][0]["code"] == "34-302"  # exact first
    assert lab.pk in [r["id"] for r in c.get(f"{API}/resources/").json()["results"]]


def test_resource_list_free_window(student, room, room2, monday, now):
    book(student, room, monday, (10,), (11,), now)
    c = client_for(student)
    resp = c.get(
        f"{API}/resources/", {"free_from": at(monday, 10, 30).isoformat(), "free_to": at(monday, 12).isoformat()}
    )
    assert [r["code"] for r in resp.json()["results"]] == ["34-302"]
    resp = c.get(f"{API}/resources/", {"free_from": at(monday, 11).isoformat(), "free_to": at(monday, 12).isoformat()})
    assert len(resp.json()["results"]) == 2

    err = assert_error(c.get(f"{API}/resources/", {"free_from": at(monday, 11).isoformat()}), 400, "invalid")
    assert "free_from" in err["detail"]
    assert_error(
        c.get(f"{API}/resources/", {"free_from": at(monday, 12).isoformat(), "free_to": at(monday, 11).isoformat()}),
        400,
        "invalid",
    )


def test_resource_detail_by_id_or_slug_and_tenant_isolation(student, room):
    c = client_for(student)
    assert c.get(f"{API}/resources/{room.pk}/").json()["code"] == "34-301"
    detail = c.get(f"{API}/resources/{room.slug}/").json()
    assert detail["id"] == room.pk and "attributes" in detail

    other = Institution.objects.create(code="OTH", name="Other University")
    t = ResourceType.objects.create(institution=other, code="hall", name="Hall", category="space")
    foreign = Resource.objects.create(institution=other, type=t, code="H-1", name="Foreign Hall")
    assert_error(c.get(f"{API}/resources/{foreign.pk}/"), 404, "not_found")
    assert foreign.pk not in [r["id"] for r in c.get(f"{API}/resources/").json()["results"]]


def test_availability_explains_every_cell(student, make_user, room, monday, now):
    book(make_user(), room, monday, (10,), (11,), now)
    bookings.claim_block(
        room, at(monday, 9), at(monday, 10), kind=SlotKind.CLASS, source_type="t", source_id=1, label="CSE326 Lecture"
    )
    resp = client_for(student).get(
        f"{API}/resources/{room.slug}/availability/", {"date": monday.isoformat(), "days": 2}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["resource"]["id"] == room.pk
    assert [d["date"] for d in body["days"]] == [monday.isoformat(), (monday + timedelta(days=1)).isoformat()]
    cells = {c["start"][11:16]: c for c in body["days"][0]["cells"]}
    assert cells["09:00"]["state"] == "class" and cells["09:00"]["reason"] == "CSE326 Lecture"
    assert cells["10:00"]["state"] == "booked" and not cells["10:00"]["selectable"]
    assert cells["12:00"] == {**cells["12:00"], "state": "free", "selectable": True}
    kinds = {b["kind"] for b in body["days"][0]["blocks"]}
    assert kinds == {"class", "booked"}
    # Someone else's booking never leaks its reference to a student.
    assert all(b["reference"] == "" for b in body["days"][0]["blocks"])


def test_availability_validates_query(student, room):
    c = client_for(student)
    assert_error(c.get(f"{API}/resources/{room.pk}/availability/", {"days": 8}), 400, "invalid")
    assert_error(c.get(f"{API}/resources/{room.pk}/availability/", {"date": "not-a-date"}), 400, "invalid")
    assert_error(c.get(f"{API}/resources/99999/availability/"), 404, "not_found")


# ── Bookings: create ────────────────────────────────────────────────────────


def test_create_booking(student, room, monday):
    resp = book_api(student, room, monday, (10,), (11,), title="Group study", attendees=4)
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["reference"].startswith("LR-")
    assert body["status"] == "approved"
    assert body["resource"]["id"] == room.pk
    assert body["qr_token"]  # the owner sees their pass token
    assert Booking.objects.get(reference=body["reference"]).booked_for == student


def test_create_conflict_is_409_with_the_reason(student, make_user, room, monday):
    assert book_api(student, room, monday, (10,), (11,)).status_code == 201
    err = assert_error(book_api(make_user(), room, monday, (10, 30), (11, 30)), 409, "conflict")
    assert "Already booked 10:00" in err["message"]
    assert err["detail"]["conflicts"][0]["kind"] == "booking"


def test_create_rule_violation_is_422(student, room, monday):
    err = assert_error(book_api(student, room, monday, (7,), (8,)), 422, "closed")
    assert "open 08:00" in err["message"]
    assert_error(book_api(student, room, monday, (9,), (10,), attendees=61), 422, "policy")


def test_create_validates_input(student, room, monday):
    err = assert_error(book_api(student, room, monday, (11,), (10,)), 400, "invalid")
    assert "end" in err["detail"]
    err = assert_error(client_for(student).post(f"{API}/bookings/", {"start": "x"}, format="json"), 400, "invalid")
    assert {"resource", "start", "end"} <= set(err["detail"])
    assert_error(book_api(student, room, monday, (10,), (11,), attendees=0), 400, "invalid")


def test_create_rejects_foreign_resource(student, monday):
    other = Institution.objects.create(code="OTH", name="Other University")
    t = ResourceType.objects.create(institution=other, code="hall", name="Hall", category="space")
    foreign = Resource.objects.create(institution=other, type=t, code="H-1", name="Foreign Hall")
    err = assert_error(book_api(student, foreign, monday, (10,), (11,)), 400, "invalid")
    assert "resource" in err["detail"]


def test_student_cannot_book_on_behalf(student, make_user, room, monday):
    friend = make_user()
    assert_error(book_api(student, room, monday, (10,), (11,), booked_for=friend.username), 403, "forbidden")


def test_faculty_can_book_on_behalf(faculty, student, room, monday):
    resp = book_api(faculty, room, monday, (10,), (11,), booked_for=student.username, group_label="K23KF")
    assert resp.status_code == 201
    assert resp.json()["booked_for"] == student.display_name


# ── Bookings: visibility ────────────────────────────────────────────────────


def test_list_is_scoped_to_what_the_user_may_see(
    student, make_user, custodian, facility_manager, room, room2, monday, now
):
    mine = book(student, room, monday, (10,), (11,), now)
    theirs = book(make_user(), room2, monday, (10,), (11,), now)

    def refs(user, **params):
        resp = client_for(user).get(f"{API}/bookings/", params)
        assert resp.status_code == 200
        return {b["reference"] for b in resp.json()["results"]}

    assert refs(student) == {mine.reference}
    assert refs(custodian) == {mine.reference}  # custodian of `room` only
    assert refs(facility_manager) == {mine.reference, theirs.reference}
    assert refs(facility_manager, resource=room2.pk) == {theirs.reference}
    assert refs(facility_manager, status="approved,pending") == {mine.reference, theirs.reference}
    assert refs(facility_manager, status="cancelled") == set()
    assert refs(facility_manager, date_from=(monday + timedelta(days=1)).isoformat()) == set()
    assert refs(facility_manager, date_from=monday.isoformat(), date_to=monday.isoformat()) == {
        mine.reference,
        theirs.reference,
    }
    assert refs(facility_manager, mine="true") == set()
    assert_error(client_for(student).get(f"{API}/bookings/", {"status": "bogus"}), 400, "invalid")


def test_retrieve_hides_other_peoples_bookings(student, make_user, custodian, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    assert_error(client_for(make_user()).get(f"{API}/bookings/{b.reference}/"), 404, "not_found")
    own = client_for(student).get(f"{API}/bookings/{b.reference}/").json()
    assert own["qr_token"] == b.qr_token
    assert own["checkin"]["state"] == "not_yet"
    managed = client_for(custodian).get(f"{API}/bookings/{b.reference}/").json()
    assert managed["reference"] == b.reference and managed["qr_token"] is None


# ── Bookings: cancel ────────────────────────────────────────────────────────


def test_cancel_own_booking(student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    resp = client_for(student).post(f"{API}/bookings/{b.reference}/cancel/", {"reason": "plans changed"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert not BookingSlot.objects.filter(booking=b).exists()
    assert_error(client_for(student).post(f"{API}/bookings/{b.reference}/cancel/"), 403, "forbidden")


def test_cannot_cancel_other_peoples_bookings(student, make_user, other_custodian, custodian, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    assert_error(client_for(make_user()).post(f"{API}/bookings/{b.reference}/cancel/"), 404)
    assert_error(client_for(other_custodian).post(f"{API}/bookings/{b.reference}/cancel/"), 404)
    b.refresh_from_db()
    assert b.status == BookingStatus.APPROVED
    # The resource's own custodian may.
    assert client_for(custodian).post(f"{API}/bookings/{b.reference}/cancel/").json()["status"] == "cancelled"


# ── Bookings: approvals ─────────────────────────────────────────────────────


def test_custodian_approves_own_resource(custodian, pending_booking):
    resp = client_for(custodian).post(
        f"{API}/bookings/{pending_booking.reference}/approve/", {"comment": "ok"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "approved"
    assert body["approvals"][0]["decision"] == "approved"
    assert body["approvals"][0]["decided_by"] == custodian.display_name
    # Deciding twice is a state conflict.
    assert_error(
        client_for(custodian).post(f"{API}/bookings/{pending_booking.reference}/approve/"), 409, "invalid_state"
    )


def test_approval_authorisation_failures(student, other_custodian, dept_head, pending_booking):
    url = f"{API}/bookings/{pending_booking.reference}/approve/"
    assert_error(client_for(student).post(url), 403, "permission_denied")  # capability gate
    assert_error(client_for(other_custodian).post(url), 404, "not_found")  # not their resource: invisible
    # The department head can see the booking but the current step belongs to the custodian.
    assert_error(client_for(dept_head).post(url), 403, "forbidden")
    pending_booking.refresh_from_db()
    assert pending_booking.status == BookingStatus.PENDING


def test_reject_requires_a_comment(custodian, pending_booking):
    url = f"{API}/bookings/{pending_booking.reference}/reject/"
    err = assert_error(client_for(custodian).post(url, {}, format="json"), 400, "invalid")
    assert "comment" in err["detail"]
    resp = client_for(custodian).post(url, {"comment": "Room reserved for exams"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert not BookingSlot.objects.filter(booking=pending_booking).exists()


def test_facility_manager_can_approve_anywhere(facility_manager, pending_booking):
    resp = client_for(facility_manager).post(f"{API}/bookings/{pending_booking.reference}/approve/")
    assert resp.status_code == 200 and resp.json()["status"] == "approved"


def test_approve_non_pending_booking_is_409(custodian, student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)  # no workflow -> confirmed instantly
    assert_error(client_for(custodian).post(f"{API}/bookings/{b.reference}/approve/"), 409, "invalid_state")


def test_approval_queue(custodian, other_custodian, student, pending_booking):
    resp = client_for(custodian).get(f"{API}/approvals/")
    assert resp.status_code == 200
    items = resp.json()["results"]
    assert [i["booking"]["reference"] for i in items] == [pending_booking.reference]
    assert items[0]["approver_role"] == "custodian"
    assert client_for(other_custodian).get(f"{API}/approvals/").json()["results"] == []
    assert_error(client_for(student).get(f"{API}/approvals/"), 403, "permission_denied")


# ── Bookings: check-in / check-out / ics ────────────────────────────────────


def test_check_in_and_out(student, live_booking):
    c = client_for(student)
    resp = c.post(f"{API}/bookings/{live_booking.reference}/check-in/", {"method": "app"}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == "checked_in"
    assert resp.json()["checkin"]["state"] == "in_use"
    resp = c.post(f"{API}/bookings/{live_booking.reference}/check-out/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
    assert_error(c.post(f"{API}/bookings/{live_booking.reference}/check-out/"), 409, "invalid_state")


def test_check_in_authorisation(student, make_user, other_custodian, custodian, live_booking):
    url = f"{API}/bookings/{live_booking.reference}/check-in/"
    assert_error(client_for(make_user()).post(url), 404)
    assert_error(client_for(other_custodian).post(url), 404)
    # The owner can't claim a custodian check-in.
    assert_error(client_for(student).post(url, {"method": "custodian"}, format="json"), 403, "forbidden")
    assert_error(client_for(student).post(url, {"method": "teleport"}, format="json"), 400, "invalid")
    resp = client_for(custodian).post(url, {"method": "custodian"}, format="json")
    assert resp.status_code == 200 and resp.json()["status"] == "checked_in"


def test_check_in_too_early_is_409(student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    err = assert_error(client_for(student).post(f"{API}/bookings/{b.reference}/check-in/"), 409, "invalid_state")
    assert "Check-in opens at" in err["message"]


def test_ics_download(student, make_user, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    resp = client_for(student).get(f"{API}/bookings/{b.reference}/ics/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/calendar")
    text = resp.content.decode()
    assert "BEGIN:VCALENDAR" in text and "BEGIN:VEVENT" in text and b.reference in text
    assert_error(client_for(make_user()).get(f"{API}/bookings/{b.reference}/ics/"), 404)


# ── Recurring series ────────────────────────────────────────────────────────


def series_payload(room, monday, **kw):
    return {
        "resource": room.pk,
        "title": "CSE326 extra lab",
        "frequency": "weekly",
        "weekdays": [0],
        "start_date": monday.isoformat(),
        "until_date": (monday + timedelta(days=14)).isoformat(),
        "start_time": "10:00",
        "end_time": "11:00",
        **kw,
    }


def test_series_preview_and_create(faculty, student, room, monday, now):
    book(student, room, monday + timedelta(days=7), (10,), (11,), now)  # the middle Monday is taken
    c = client_for(faculty)
    resp = c.post(f"{API}/series/preview/", series_payload(room, monday), format="json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["total"] == 3 and body["bookable"] == 2
    blocked = [o for o in body["occurrences"] if not o["ok"]]
    assert blocked[0]["code"] == "conflict" and "Already booked" in blocked[0]["reason"]

    resp = c.post(f"{API}/series/", series_payload(room, monday), format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["series"]["created_count"] == 2
    assert len(body["created"]) == 2 and len(body["skipped"]) == 1
    assert body["skipped"][0]["code"] == "conflict"


def test_series_authorisation_and_validation(student, faculty, room, monday):
    assert_error(client_for(student).post(f"{API}/series/preview/", series_payload(room, monday), format="json"), 403)
    assert_error(client_for(student).post(f"{API}/series/", series_payload(room, monday), format="json"), 403)
    bad = series_payload(room, monday, until_date=(monday - timedelta(days=1)).isoformat())
    assert "until_date" in assert_error(client_for(faculty).post(f"{API}/series/", bad, format="json"), 400)["detail"]
    bad = series_payload(room, monday, weekdays=[9])
    assert_error(client_for(faculty).post(f"{API}/series/preview/", bad, format="json"), 400, "invalid")


# ── Maintenance ─────────────────────────────────────────────────────────────


def maintenance_payload(resource, monday, **kw):
    return {
        "resource": resource.pk,
        "start": at(monday, 9).isoformat(),
        "end": at(monday, 12).isoformat(),
        "title": "Projector replacement",
        "kind": "repair",
        **kw,
    }


def test_custodian_schedules_maintenance_and_displaces_bookings(custodian, student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    resp = client_for(custodian).post(f"{API}/maintenance/", maintenance_payload(room, monday), format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["displaced_bookings"] == 1 and body["status"] == "scheduled"
    b.refresh_from_db()
    assert b.status == BookingStatus.CANCELLED
    # Booking into the window now explains why.
    err = assert_error(book_api(student, room, monday, (10,), (11,)), 409, "maintenance")
    assert "Projector replacement" in err["message"]


def test_maintenance_authorisation(student, custodian, other_custodian, room, room2, monday):
    assert_error(client_for(student).get(f"{API}/maintenance/"), 403, "permission_denied")
    assert_error(client_for(student).post(f"{API}/maintenance/", maintenance_payload(room, monday), format="json"), 403)
    # A custodian can't schedule on a resource they don't look after.
    assert_error(
        client_for(custodian).post(f"{API}/maintenance/", maintenance_payload(room2, monday), format="json"),
        403,
        "forbidden",
    )
    ours = client_for(custodian).post(f"{API}/maintenance/", maintenance_payload(room, monday), format="json").json()
    theirs = (
        client_for(other_custodian)
        .post(f"{API}/maintenance/", maintenance_payload(room2, monday), format="json")
        .json()
    )
    listed = [w["id"] for w in client_for(custodian).get(f"{API}/maintenance/").json()["results"]]
    assert listed == [ours["id"]]
    assert_error(client_for(custodian).post(f"{API}/maintenance/{theirs['id']}/cancel/"), 404)
    assert_error(client_for(custodian).get(f"{API}/maintenance/{theirs['id']}/"), 404)


def test_maintenance_validation(custodian, room, monday):
    bad = maintenance_payload(room, monday, end=at(monday, 8).isoformat())
    assert "end" in assert_error(client_for(custodian).post(f"{API}/maintenance/", bad, format="json"), 400)["detail"]
    bad = maintenance_payload(room, monday, kind="exorcism")
    assert_error(client_for(custodian).post(f"{API}/maintenance/", bad, format="json"), 400, "invalid")


def test_maintenance_cancel_and_complete(custodian, facility_manager, room, monday):
    c = client_for(custodian)
    w1 = c.post(f"{API}/maintenance/", maintenance_payload(room, monday), format="json").json()
    resp = c.post(f"{API}/maintenance/{w1['id']}/cancel/")
    assert resp.status_code == 200 and resp.json()["status"] == "cancelled"
    assert not BookingSlot.objects.filter(source_type="maintenance_window", source_id=w1["id"]).exists()
    assert_error(c.post(f"{API}/maintenance/{w1['id']}/cancel/"), 409, "invalid_state")

    w2 = c.post(
        f"{API}/maintenance/",
        maintenance_payload(room, monday, start=at(monday, 14).isoformat(), end=at(monday, 15).isoformat()),
        format="json",
    ).json()
    resp = client_for(facility_manager).post(f"{API}/maintenance/{w2['id']}/complete/")
    assert resp.status_code == 200 and resp.json()["status"] == "completed"
    assert c.get(f"{API}/maintenance/", {"status": "completed"}).json()["results"][0]["id"] == w2["id"]


def test_anyone_can_report_a_breakdown(student, room):
    c = client_for(student)
    resp = c.post(f"{API}/resources/{room.slug}/report-breakdown/", {"summary": "Projector dead"}, format="json")
    assert resp.status_code == 201
    assert resp.json()["severity"] == "high" and resp.json()["window"] is None

    resp = c.post(
        f"{API}/resources/{room.pk}/report-breakdown/",
        {"summary": "Ceiling leak", "severity": "critical"},
        format="json",
    )
    assert resp.status_code == 201
    room.refresh_from_db()
    assert room.status == "active" and resp.json()["window"] is None  # awaits a custodian (SEC-02)

    assert_error(c.post(f"{API}/resources/{room.pk}/report-breakdown/", {}, format="json"), 400, "invalid")
    assert_error(
        c.post(f"{API}/resources/{room.pk}/report-breakdown/", {"summary": "x", "severity": "meh"}, format="json"), 400
    )
    assert_error(c.post(f"{API}/resources/99999/report-breakdown/", {"summary": "x"}, format="json"), 404)


def test_custodian_critical_report_takes_resource_offline(custodian, room):
    resp = client_for(custodian).post(
        f"{API}/resources/{room.pk}/report-breakdown/",
        {"summary": "Ceiling leak", "severity": "critical"},
        format="json",
    )
    assert resp.status_code == 201
    room.refresh_from_db()
    assert room.status == "out_of_service"
    assert MaintenanceWindow.objects.filter(pk=resp.json()["window"]).exists()


# ── Timetable ───────────────────────────────────────────────────────────────


@pytest.fixture
def term(lpu, monday):
    return AcademicTerm.objects.create(
        institution=lpu,
        code="26271",
        name="Odd term",
        starts=monday - timedelta(days=7),
        ends=monday + timedelta(days=20),
    )


def timetable_payload(**kw):
    row = {"room_code": "34-301", "day": "Mon", "start": "09:00", "end": "10:00", "course_code": "CSE326"}
    return {"term": "26271", "entries": [{**row, **kw}]}


def test_publish_timetable(facility_manager, student, room, term, monday, now):
    b = book(student, room, monday, (9,), (10,), now)
    resp = client_for(facility_manager).post(
        f"{API}/timetable/publications/", timetable_payload(section="K23KF"), format="json"
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["publication"]["status"] == "published" and body["publication"]["term"] == "26271"
    assert body["occurrences"] >= 2 and body["displaced"] == 1
    b.refresh_from_db()
    assert b.status == BookingStatus.CANCELLED
    listed = client_for(facility_manager).get(f"{API}/timetable/publications/").json()["results"]
    assert listed[0]["id"] == body["publication"]["id"]


def test_publish_timetable_row_errors_are_422(facility_manager, room, term):
    payload = timetable_payload()
    payload["entries"].append(
        {"room_code": "NOPE", "day": "Funday", "start": "09:00", "end": "10:00", "course_code": "X"}
    )
    err = assert_error(
        client_for(facility_manager).post(f"{API}/timetable/publications/", payload, format="json"), 422, "invalid_rows"
    )
    assert any("unknown room 'NOPE'" in e for e in err["detail"]["rows"])
    assert not BookingSlot.objects.filter(kind=SlotKind.CLASS).exists()


def test_publish_timetable_validation_and_authorisation(facility_manager, custodian, student, room, term):
    url = f"{API}/timetable/publications/"
    assert_error(client_for(student).post(url, timetable_payload(), format="json"), 403, "permission_denied")
    assert_error(client_for(custodian).post(url, timetable_payload(), format="json"), 403, "permission_denied")
    assert_error(client_for(custodian).get(url), 403)
    fm = client_for(facility_manager)
    assert_error(fm.post(url, {**timetable_payload(), "term": "00000"}, format="json"), 404, "not_found")
    assert_error(fm.post(url, {"term": "26271", "entries": []}, format="json"), 400, "invalid")
    err = assert_error(fm.post(url, {"term": "26271", "entries": [{"room_code": "34-301"}]}, format="json"), 400)
    assert "entries" in err["detail"]


# ── Analytics ───────────────────────────────────────────────────────────────


def test_analytics_authorisation(student, custodian, faculty):
    for user in (student, custodian, faculty):
        assert_error(client_for(user).get(f"{API}/analytics/utilisation/"), 403, "permission_denied")


def test_analytics_scoped_to_own_department(dept_head, lpu, room):
    other = Department.objects.create(institution=lpu, code="ME", name="Mechanical")
    c = client_for(dept_head)
    assert_error(c.get(f"{API}/analytics/utilisation/", {"department": other.code}), 403, "forbidden")
    resp = c.get(f"{API}/analytics/utilisation/", {"by": "resource"})
    if resp.status_code == 503:  # analytics module not implemented yet
        assert_error(resp, 503, "analytics_unavailable")
        return
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["scope"]["department"] == "CSE" and body["by"] == "resource"
    assert "utilisation_pct" in body["overview"]


def test_analytics_campus_scope_and_validation(facility_manager, room):
    c = client_for(facility_manager)
    assert_error(c.get(f"{API}/analytics/utilisation/", {"by": "planet"}), 400, "invalid")
    assert_error(c.get(f"{API}/analytics/utilisation/", {"start": "2026-05-02", "end": "2026-05-01"}), 400, "invalid")
    assert_error(c.get(f"{API}/analytics/utilisation/", {"department": "NOPE"}), 404)
    resp = c.get(f"{API}/analytics/utilisation/", {"by": "type"})
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        assert resp.json()["scope"]["department"] is None


# ── Me & notifications ──────────────────────────────────────────────────────


def test_me(student, lpu, room, monday, now):
    Quota.objects.create(institution=lpu, name="Student weekly", role=Role.STUDENT, max_hours=6, period="week")
    Restriction.objects.create(
        institution=lpu,
        user=student,
        starts_at=timezone.now() - timedelta(hours=1),
        ends_at=timezone.now() + timedelta(days=2),
        reason="3 no-shows in 30 days",
        tier_label="7-day pause",
    )
    Notification.objects.create(user=student, kind="reminder", title="Soon")
    body = client_for(student).get(f"{API}/me/").json()
    assert body["username"] == student.username and body["role"] == "student"
    assert "book_resources" in body["capabilities"] and "approve_bookings" not in body["capabilities"]
    assert body["department"]["code"] == "CSE"
    assert body["quotas"][0]["name"] == "Student weekly" and body["quotas"][0]["max_hours"] == "6.0"
    assert body["restriction"]["tier_label"] == "7-day pause"
    assert body["unread_notifications"] == 1


def test_me_without_restriction(facility_manager):
    body = client_for(facility_manager).get(f"{API}/me/").json()
    assert body["restriction"] is None and body["department"] is None
    assert "view_campus_analytics" in body["capabilities"]


def test_notifications_are_private(student, make_user):
    other = make_user()
    mine = Notification.objects.create(user=student, kind="reminder", title="Mine")
    theirs = Notification.objects.create(user=other, kind="reminder", title="Theirs")
    c = client_for(student)
    assert [n["id"] for n in c.get(f"{API}/notifications/").json()["results"]] == [mine.pk]
    assert_error(c.post(f"{API}/notifications/{theirs.pk}/read/"), 404)
    resp = c.post(f"{API}/notifications/{mine.pk}/read/")
    assert resp.status_code == 200 and resp.json()["unread"] is False
    assert c.get(f"{API}/notifications/", {"unread": "true"}).json()["results"] == []


def test_notifications_read_all(student, make_user):
    other = make_user()
    Notification.objects.create(user=student, kind="reminder", title="A")
    Notification.objects.create(user=student, kind="reminder", title="B")
    Notification.objects.create(user=other, kind="reminder", title="C")
    resp = client_for(student).post(f"{API}/notifications/read-all/")
    assert resp.status_code == 200 and resp.json() == {"updated": 2}
    assert Notification.objects.filter(user=other, read_at__isnull=True).count() == 1
