"""
Configuration console (Setup): resources, rules, workflows, timetable, users, audit, ops.

Each screen renders for the roles that use it and refuses the rest server-side; the
end-to-end flows (photo upload, CSV import, workflow builder, timetable publish, role
changes, Run now) go through the real views.
"""

import io
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import Department, Role, User
from apps.approvals.models import ApprovalWorkflow, Decision
from apps.approvals.services import resolve_workflow
from apps.audit.models import AuditLog
from apps.bookings import services as bookings
from apps.bookings.models import Booking, BookingSlot, BookingStatus, SlotKind
from apps.catalogue.models import Feature, Resource
from apps.core.models import SweepRun
from apps.core.timeutil import trange
from apps.rules.models import AvailabilityRule, Blackout, BookingPolicy, Quota, Scope
from apps.timetable.models import AcademicTerm, PublicationStatus, TimetablePublication

from .conftest import at

pytestmark = pytest.mark.django_db

CONSOLE = [
    "manage:setup",
    "manage:resources",
    "manage:resource_new",
    "manage:policies",
    "manage:workflows",
    "manage:timetable",
    "manage:users",
    "manage:audit",
    "manage:ops",
]


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def ece(lpu):
    return Department.objects.create(institution=lpu, code="ECE", name="Electronics & Communication")


@pytest.fixture
def hod(make_user):
    return make_user(Role.DEPT_HEAD)


def _png(size=(32, 24), noise=False) -> bytes:
    img = Image.new("RGB", size, (246, 129, 33))
    if noise:
        img = Image.frombytes("RGB", size, __import__("os").urandom(size[0] * size[1] * 3))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _resource_post(r, **extra):
    data = {
        "name": r.name,
        "code": r.code,
        "type": r.type_id,
        "capacity": r.capacity,
        "status": r.status,
        "is_bookable": "on",
        "building": r.building_id or "",
        "department": r.department_id or "",
        "attr_key": [""],
        "attr_value": [""],
    }
    data.update(extra)
    return data


# ── Rendering and access ────────────────────────────────────────────────────


@pytest.mark.parametrize("role", [Role.ADMIN, Role.FACILITY_MANAGER])
@pytest.mark.parametrize("name", CONSOLE)
def test_console_renders_for_admin_and_facility_manager(client, make_user, room, name, role):
    client.force_login(make_user(role, department=None))
    assert client.get(reverse(name)).status_code == 200, name


@pytest.mark.parametrize("name", CONSOLE)
def test_students_are_refused_everywhere(client, student, room, name):
    client.force_login(student)
    assert client.get(reverse(name)).status_code == 403


@pytest.mark.parametrize(
    "name",
    [
        "manage:setup",
        "manage:resource_new",
        "manage:policies",
        "manage:workflows",
        "manage:timetable",
        "manage:users",
        "manage:audit",
        "manage:ops",
    ],
)
def test_custodians_cannot_reach_configuration(client, custodian, room, name):
    client.force_login(custodian)
    assert client.get(reverse(name)).status_code == 403


def test_setup_hub_only_shows_allowed_cards(client, hod, facility_manager, room):
    client.force_login(hod)
    body = client.get(reverse("manage:setup")).content.decode()
    assert "Booking rules" in body and "Approval workflows" in body
    assert "Operations" not in body and "Timetable" not in body
    client.force_login(facility_manager)
    body = client.get(reverse("manage:setup")).content.decode()
    assert "Operations" in body and "Timetable" in body


def test_door_qr_renders_svg(client, custodian, room):
    client.force_login(custodian)
    resp = client.get(reverse("manage:door_qr", args=[room.pk]))
    assert resp.status_code == 200
    assert b"<svg" in resp.content and b"Scan to check in" in resp.content


# ── Resources ───────────────────────────────────────────────────────────────


def test_custodian_edits_own_resource_but_not_others(client, custodian, room, room2):
    client.force_login(custodian)
    assert client.get(reverse("manage:resource_edit", args=[room.pk])).status_code == 200
    assert client.get(reverse("manage:resource_edit", args=[room2.pk])).status_code == 404
    resp = client.post(reverse("manage:resource_edit", args=[room2.pk]), _resource_post(room2, name="Hijacked"))
    assert resp.status_code == 404
    room2.refresh_from_db()
    assert room2.name == "Room 34-302"

    resp = client.post(
        reverse("manage:resource_edit", args=[room.pk]),
        _resource_post(
            room, name="Room 34-301 (renovated)", code="HACK-1", attr_key=["Seating"], attr_value=["Tiered"]
        ),
    )
    assert resp.status_code == 302
    room.refresh_from_db()
    assert room.name == "Room 34-301 (renovated)"
    assert room.code == "34-301"  # custodians can't change identity fields
    assert list(room.attributes.values_list("key", "value")) == [("Seating", "Tiered")]
    log = AuditLog.objects.get(action="resource.update", target_id=str(room.pk))
    assert log.before["name"] == "Room 34-301" and log.after["name"] == "Room 34-301 (renovated)"


def test_custodian_list_is_scoped_and_cannot_create(client, custodian, room, room2):
    client.force_login(custodian)
    body = client.get(reverse("manage:resources")).content.decode()
    assert "Room 34-301" in body and "Room 34-302" not in body
    assert client.get(reverse("manage:resource_new")).status_code == 403


def test_out_of_service_needs_a_reason(client, facility_manager, room):
    client.force_login(facility_manager)
    resp = client.post(reverse("manage:resource_edit", args=[room.pk]), _resource_post(room, status="out_of_service"))
    assert resp.status_code == 200
    assert b"Say why it" in resp.content
    room.refresh_from_db()
    assert room.status == "active"


def test_photo_upload_accepts_png_and_reencodes_to_webp(client, facility_manager, room, media):
    client.force_login(facility_manager)
    photo = SimpleUploadedFile("room.png", _png(), content_type="image/png")
    resp = client.post(reverse("manage:resource_edit", args=[room.pk]), _resource_post(room, photo=photo))
    assert resp.status_code == 302
    room.refresh_from_db()
    assert room.image.name.endswith(".webp")
    with Image.open(room.image.path) as img:
        assert img.format == "WEBP"
        assert not img.info.get("exif")


def test_photo_upload_rejects_non_image(client, facility_manager, room, media):
    client.force_login(facility_manager)
    fake = SimpleUploadedFile("room.png", b"<?php echo 'hi'; ?>" * 10, content_type="image/png")
    resp = client.post(reverse("manage:resource_edit", args=[room.pk]), _resource_post(room, photo=fake))
    assert resp.status_code == 200
    assert b"isn&#x27;t a JPEG, PNG or WebP" in resp.content
    room.refresh_from_db()
    assert not room.image


def test_photo_upload_rejects_oversized_file(client, facility_manager, room, media, settings):
    settings.MAX_IMAGE_UPLOAD_BYTES = 2000
    client.force_login(facility_manager)
    big = SimpleUploadedFile("big.png", _png((120, 120), noise=True), content_type="image/png")
    resp = client.post(reverse("manage:resource_edit", args=[room.pk]), _resource_post(room, photo=big))
    assert resp.status_code == 200
    assert b"Photos can be up to" in resp.content
    room.refresh_from_db()
    assert not room.image


def test_create_resource_as_facility_manager(client, facility_manager, room_type, block34, custodian):
    client.force_login(facility_manager)
    resp = client.post(
        reverse("manage:resource_new"),
        {
            "name": "Room 34-410",
            "code": "34-410",
            "type": room_type.pk,
            "capacity": 40,
            "status": "active",
            "is_bookable": "on",
            "building": block34.pk,
            "custodians": [custodian.pk],
            "attr_key": [""],
            "attr_value": [""],
        },
    )
    assert resp.status_code == 302
    r = Resource.objects.get(code="34-410")
    assert r.custodians.filter(user=custodian).exists()
    assert r.search_vector is not None
    assert AuditLog.objects.filter(action="resource.create", target_id=str(r.pk)).exists()


IMPORT_OK = (
    "code,name,type_code,building_code,capacity,floor,room,department_code,features,description\n"
    "34-501,Room 34-501,classroom,34,45,5,501,CSE,Projector,Top floor\n"
    "34-502,Room 34-502,classroom,34,45,5,502,,,\n"
)
IMPORT_BAD = IMPORT_OK + "34-503,Room 34-503,spaceship,34,0,5,503,ZZZ,Teleporter,\n"


def test_csv_import_preview_then_confirm_creates_all(client, facility_manager, room_type, block34, cse, lpu):
    Feature.objects.create(institution=lpu, name="Projector")
    client.force_login(facility_manager)
    url = reverse("manage:resources")
    resp = client.post(
        url, {"action": "import_preview", "file": SimpleUploadedFile("r.csv", IMPORT_OK.encode(), "text/csv")}
    )
    assert resp.status_code == 200
    assert b"All 2 rows look right" in resp.content
    assert not Resource.objects.filter(code__startswith="34-50").exists()  # preview writes nothing

    resp = client.post(url, {"action": "import_confirm", "csv_text": IMPORT_OK})
    assert resp.status_code == 302
    created = Resource.objects.filter(code__in=["34-501", "34-502"])
    assert created.count() == 2
    assert created.get(code="34-501").features.filter(name="Projector").exists()
    assert AuditLog.objects.filter(action="resource.import").count() == 2


def test_csv_import_with_bad_rows_imports_nothing(client, facility_manager, room_type, block34, cse, lpu):
    Feature.objects.create(institution=lpu, name="Projector")
    client.force_login(facility_manager)
    url = reverse("manage:resources")
    resp = client.post(
        url, {"action": "import_preview", "file": SimpleUploadedFile("r.csv", IMPORT_BAD.encode(), "text/csv")}
    )
    body = resp.content.decode()
    assert "1 of 3 rows needs fixing" in body
    assert "Type &#x27;spaceship&#x27; doesn&#x27;t exist" in body
    # Even if someone posts the bad text straight to confirm, nothing is written.
    resp = client.post(url, {"action": "import_confirm", "csv_text": IMPORT_BAD})
    assert resp.status_code == 200
    assert not Resource.objects.filter(code__startswith="34-50").exists()


def test_csv_import_refuses_spreadsheet_binary(client, facility_manager, room_type):
    client.force_login(facility_manager)
    xlsx = SimpleUploadedFile("r.csv", b"PK\x03\x04" + b"\x00" * 64, "text/csv")
    resp = client.post(reverse("manage:resources"), {"action": "import_preview", "file": xlsx})
    assert b"spreadsheet file, not a CSV" in resp.content


# ── Policies ────────────────────────────────────────────────────────────────


def test_booking_policy_override_is_audited_and_applies(client, facility_manager, room):
    from apps.rules.services import policy_for

    client.force_login(facility_manager)
    resp = client.post(
        reverse("manage:policies"),
        {
            "action": "policy.save",
            "scope": "resource",
            "resource": room.pk,
            "slot_minutes": 30,
            "lead_time_minutes": 60,
            "min_duration_minutes": 60,
            "max_duration_minutes": 120,
            "max_advance_days": 14,
            "requires_checkin": "on",
            "checkin_opens_minutes": 10,
            "checkin_grace_minutes": 10,
            "enforce_capacity": "on",
        },
    )
    assert resp.status_code == 302
    assert policy_for(room).max_duration_minutes == 120
    assert AuditLog.objects.filter(action="rules.policy.create").exists()


def test_policy_validation_speaks_in_sentences(client, facility_manager, room_type):
    client.force_login(facility_manager)
    resp = client.post(
        reverse("manage:policies"),
        {
            "action": "policy.save",
            "scope": "type",
            "resource_type": room_type.pk,
            "slot_minutes": 30,
            "lead_time_minutes": 0,
            "min_duration_minutes": 45,
            "max_duration_minutes": 30,
            "max_advance_days": 14,
            "checkin_opens_minutes": 10,
            "checkin_grace_minutes": 10,
        },
    )
    body = resp.content.decode()
    assert resp.status_code == 200
    assert "The longest booking can&#x27;t be shorter than the shortest one." in body
    assert BookingPolicy.objects.filter(resource_type=room_type).count() == 1


def test_hours_add_refuses_overlap(client, facility_manager, room_type):
    client.force_login(facility_manager)
    resp = client.post(
        reverse("manage:policies"),
        {
            "action": "hours.add",
            "scope": "type",
            "resource_type": room_type.pk,
            "weekdays": ["0"],
            "opens": "19:00",
            "closes": "21:00",
        },
    )
    assert resp.status_code == 200
    assert b"already has 08:00" in resp.content
    resp = client.post(
        reverse("manage:policies"),
        {
            "action": "hours.add",
            "scope": "type",
            "resource_type": room_type.pk,
            "weekdays": ["6"],
            "opens": "09:00",
            "closes": "13:00",
        },
    )
    assert resp.status_code == 302
    assert AvailabilityRule.objects.filter(resource_type=room_type, weekday=6).exists()


def test_blackout_create(client, facility_manager, room):
    client.force_login(facility_manager)
    start = timezone.localtime() + timedelta(days=3)
    resp = client.post(
        reverse("manage:policies"),
        {
            "action": "blackout.save",
            "title": "Convocation",
            "kind": "event",
            "scope": "campus",
            "starts": start.strftime("%Y-%m-%dT09:00"),
            "ends": start.strftime("%Y-%m-%dT18:00"),
            "exempt_roles": ["faculty"],
        },
    )
    assert resp.status_code == 302
    b = Blackout.objects.get(title="Convocation")
    assert b.exempt_roles == ["faculty"] and b.scope == Scope.CAMPUS
    assert AuditLog.objects.filter(action="rules.blackout.create").exists()


def test_dept_head_manages_only_own_department_quota(client, hod, cse, ece, lpu):
    theirs = Quota.objects.create(institution=lpu, name="ECE lab hours", department=ece, period="week", max_hours=10)
    client.force_login(hod)
    url = reverse("manage:policies")
    body = client.get(url + "?tab=quotas").content.decode()
    assert "ECE lab hours" not in body

    resp = client.post(
        url, {"action": "quota.save", "pk": theirs.pk, "name": "Taken over", "period": "week", "max_hours": 99}
    )
    assert resp.status_code == 404
    assert client.post(url, {"action": "quota.toggle", "pk": theirs.pk}).status_code == 404
    assert client.post(url, {"action": "quota.delete", "pk": theirs.pk}).status_code == 404
    theirs.refresh_from_db()
    assert theirs.name == "ECE lab hours" and theirs.active

    # Creating a quota always lands on their own department, whatever is posted.
    resp = client.post(
        url,
        {
            "action": "quota.save",
            "name": "CSE seminar hours",
            "target": "role",
            "role": "student",
            "department": ece.pk,
            "period": "week",
            "max_hours": 12,
            "active": "on",
        },
    )
    assert resp.status_code == 302
    q = Quota.objects.get(name="CSE seminar hours")
    assert q.department_id == cse.pk and q.role == ""

    # Campus-wide rules are read-only for heads of department.
    assert (
        client.post(
            url, {"action": "tier.save", "no_shows": 9, "window_days": 30, "restrict_days": 1, "label": "x"}
        ).status_code
        == 403
    )


# ── Workflows ───────────────────────────────────────────────────────────────


def test_workflow_builder_applies_to_the_next_booking(client, facility_manager, student, room, room_type, monday, now):
    client.force_login(facility_manager)
    resp = client.post(
        reverse("manage:workflows"),
        {
            "action": "save",
            "name": "Long student classroom bookings",
            "applies": "type",
            "resource_type": room_type.pk,
            "requester_roles": ["student"],
            "min_duration_minutes": 120,
            "priority": 100,
            "active": "on",
            "step_role": ["custodian", "dept_head"],
            "step_user": ["", ""],
            "step_sla": ["12", "24"],
        },
    )
    assert resp.status_code == 302
    w = ApprovalWorkflow.objects.get(name="Long student classroom bookings")
    assert [s.approver_role for s in w.steps.all()] == ["custodian", "dept_head"]
    assert AuditLog.objects.filter(action="workflow.create", target_id=str(w.pk)).exists()

    # No code change, no restart: the engine picks it for the very next request...
    assert resolve_workflow(room, student, 30, 120) == w
    assert resolve_workflow(room, student, 30, 60) is None
    b = bookings.create_booking(
        requester=student,
        resource=room,
        start=at(monday, 10),
        end=at(monday, 12),
        title="Mock interviews",
        attendees=30,
        notify=False,
        now=now,
    )
    assert b.status == BookingStatus.PENDING
    chain = list(b.approvals.order_by("step_order").values_list("approver_role", "decision"))
    assert chain == [("custodian", Decision.PENDING), ("dept_head", Decision.WAITING)]


def test_workflow_needs_steps_or_auto_approve(client, facility_manager, room_type):
    client.force_login(facility_manager)
    resp = client.post(
        reverse("manage:workflows"),
        {
            "action": "save",
            "name": "Empty",
            "applies": "any",
            "priority": 100,
            "step_role": [""],
            "step_user": [""],
            "step_sla": ["24"],
        },
    )
    assert resp.status_code == 200
    assert b"Add at least one approver" in resp.content
    assert not ApprovalWorkflow.objects.filter(name="Empty").exists()


def test_workflow_tester_partial_and_dept_head_read_only(client, hod, facility_manager, room, room_type, lpu):
    w = ApprovalWorkflow.objects.create(institution=lpu, name="Big groups", resource_type=room_type, min_attendees=50)
    w.steps.create(order=1, approver_role="facility_manager", sla_hours=24)
    client.force_login(facility_manager)
    resp = client.get(
        reverse("manage:workflows"),
        {"test": 1, "resource": room.pk, "role": "faculty", "attendees": 55, "minutes": 60},
        HTTP_HX_REQUEST="true",
    )
    body = resp.content.decode()
    assert "Held for approval" in body and "Big groups" in body and "<html" not in body
    client.force_login(hod)
    assert client.get(reverse("manage:workflows")).status_code == 200
    assert client.post(reverse("manage:workflows"), {"action": "toggle", "pk": w.pk}).status_code == 403


# ── Timetable ───────────────────────────────────────────────────────────────

TIMETABLE = (
    "room_code,day,start,end,course_code,course_title,section,faculty,kind\n"
    "34-301,Mon,09:00,10:00,CSE326,Internet Programming,K23KF,Dr A,Lecture\n"
    "34-301,Wed,14:00,15:00,CSE310,Java,K23KG,Dr B,Lecture\n"
)


@pytest.fixture
def term(lpu):
    today = timezone.localdate()
    return AcademicTerm.objects.create(
        institution=lpu,
        code="26271",
        name="Autumn 2026",
        starts=today - timedelta(days=7),
        ends=today + timedelta(days=35),
    )


def test_timetable_upload_check_stage_publish(client, facility_manager, room, term):
    client.force_login(facility_manager)
    url = reverse("manage:timetable")
    resp = client.post(
        url, {"action": "check", "term": term.pk, "file": SimpleUploadedFile("t.csv", TIMETABLE.encode(), "text/csv")}
    )
    assert b"All 2 classes in 1 room look right" in resp.content
    resp = client.post(url, {"action": "stage", "term": term.pk, "csv_text": TIMETABLE})
    assert resp.status_code == 302
    draft = TimetablePublication.objects.get(term=term, status=PublicationStatus.DRAFT)
    assert client.get(url + f"?draft={draft.pk}").status_code == 200
    assert not BookingSlot.objects.filter(kind=SlotKind.CLASS).exists()

    resp = client.post(url, {"action": "publish", "pub": draft.pk})
    assert resp.status_code == 302
    draft.refresh_from_db()
    assert draft.status == PublicationStatus.PUBLISHED
    assert BookingSlot.objects.filter(resource=room, kind=SlotKind.CLASS).count() == draft.occurrence_count > 0
    assert AuditLog.objects.filter(action="timetable.publish").exists()
    csv_resp = client.get(url + f"?download={draft.pk}")
    assert b"CSE326" in csv_resp.content


def test_timetable_check_highlights_bad_rows_and_stages_nothing(client, facility_manager, room, term):
    client.force_login(facility_manager)
    bad = TIMETABLE + "99-999,Fri,10:00,11:00,CSE111,,,,\n34-301,Mon,09:30,10:30,CSE999,,,,\n"
    resp = client.post(reverse("manage:timetable"), {"action": "check", "term": term.pk, "csv_text": bad})
    body = resp.content.decode()
    assert "Unknown room &#x27;99-999&#x27;" in body
    assert "Clashes with row" in body
    assert 'value="stage"' not in body
    resp = client.post(reverse("manage:timetable"), {"action": "stage", "term": term.pk, "csv_text": bad})
    assert resp.status_code == 200
    assert not TimetablePublication.objects.filter(term=term).exists()


def test_timetable_requires_capability(client, hod, term):
    client.force_login(hod)
    assert client.get(reverse("manage:timetable")).status_code == 403


# ── Users ───────────────────────────────────────────────────────────────────


def test_role_change_is_audited(client, admin_user, faculty):
    client.force_login(admin_user)
    resp = client.post(reverse("manage:users"), {"action": "role", "user": faculty.pk, "role": Role.CUSTODIAN})
    assert resp.status_code == 302
    faculty.refresh_from_db()
    assert faculty.role == Role.CUSTODIAN
    assert faculty.groups.filter(name="role:custodian").exists()
    log = AuditLog.objects.get(action="user.role_change", target_id=str(faculty.pk))
    assert log.before == {"role": "faculty"} and log.after == {"role": "custodian"}


def test_last_admin_cannot_be_demoted_or_deactivated(client, admin_user, make_user):
    client.force_login(admin_user)
    url = reverse("manage:users")
    client.post(url, {"action": "role", "user": admin_user.pk, "role": Role.FACULTY})
    admin_user.refresh_from_db()
    assert admin_user.role == Role.ADMIN
    assert not AuditLog.objects.filter(action="user.role_change").exists()
    assert client.post(url, {"action": "deactivate", "user": admin_user.pk}).status_code == 302
    admin_user.refresh_from_db()
    assert admin_user.is_active

    other = make_user(Role.ADMIN, department=None)
    client.post(url, {"action": "role", "user": admin_user.pk, "role": Role.FACULTY})
    admin_user.refresh_from_db()
    assert admin_user.role == Role.FACULTY  # allowed once another admin exists
    assert other.role == Role.ADMIN


def test_facility_manager_sees_users_read_only(client, facility_manager, student):
    client.force_login(facility_manager)
    resp = client.get(reverse("manage:users"))
    assert resp.status_code == 200 and b"data-submit-on-change" not in resp.content
    assert client.post(reverse("manage:users"), {"action": "deactivate", "user": student.pk}).status_code == 403
    student.refresh_from_db()
    assert student.is_active


def test_deactivate_never_deletes(client, admin_user, student):
    client.force_login(admin_user)
    client.post(reverse("manage:users"), {"action": "deactivate", "user": student.pk})
    assert User.objects.filter(pk=student.pk, is_active=False).exists()
    assert AuditLog.objects.filter(action="user.deactivate", target_id=str(student.pk)).exists()


# ── Audit ───────────────────────────────────────────────────────────────────


def test_audit_viewer_lists_filters_and_exports(client, facility_manager, admin_user, faculty):
    client.force_login(admin_user)
    client.post(reverse("manage:users"), {"action": "role", "user": faculty.pk, "role": Role.STAFF})
    client.force_login(facility_manager)
    resp = client.get(reverse("manage:audit"), {"action": "user."})
    body = resp.content.decode()
    assert "user.role_change" in body and "faculty" in body and "staff" in body
    resp = client.get(reverse("manage:audit"), {"action": "timetable."})
    assert b"user.role_change" not in resp.content
    csv_resp = client.get(reverse("manage:audit"), {"format": "csv"})
    assert csv_resp["Content-Type"].startswith("text/csv")
    assert "user.role_change" in b"".join(csv_resp.streaming_content).decode()


def test_audit_requires_capability(client, hod):
    client.force_login(hod)
    assert client.get(reverse("manage:audit")).status_code == 403


# ── Ops ─────────────────────────────────────────────────────────────────────


def test_ops_run_now_releases_overdue_booking(client, facility_manager, student, room, monday, now):
    b = bookings.create_booking(
        requester=student, resource=room, start=at(monday, 10), end=at(monday, 11), title="Study", notify=False, now=now
    )
    real_now = timezone.now()
    # Pretend the booking started an hour ago and nobody checked in.
    Booking.objects.filter(pk=b.pk).update(
        period=trange(real_now - timedelta(hours=1), real_now + timedelta(minutes=30))
    )
    client.force_login(facility_manager)
    resp = client.post(reverse("manage:ops"), {"task": "checkins.sweep_no_shows"})
    assert resp.status_code == 302
    b.refresh_from_db()
    assert b.status == BookingStatus.NO_SHOW
    run = SweepRun.objects.get(task="checkins.sweep_no_shows")
    assert run.ok and run.affected == 1
    assert AuditLog.objects.filter(action="ops.run_sweep").exists()
    assert b"Released 1 booking" in client.get(reverse("manage:ops")).content


def test_ops_is_campus_wide_only(client, hod, custodian):
    for u in (hod, custodian):
        client.force_login(u)
        assert client.get(reverse("manage:ops")).status_code == 403
        assert client.post(reverse("manage:ops"), {"task": "checkins.sweep_no_shows"}).status_code == 403
