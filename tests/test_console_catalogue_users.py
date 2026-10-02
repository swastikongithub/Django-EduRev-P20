"""
Catalogue setup (resource types, blocks, departments) and administrator-created accounts.

Production started from an empty catalogue with no way to add types, blocks or people except a
shell; these are the console paths that replace it, with their permissions, validation, audit
trail and MFA behaviour. The last test runs the approval workflow end to end with two people
created through the new screen.
"""

import re

import pyotp
import pytest
from django.contrib.auth import authenticate
from django.test import Client
from django.urls import reverse

from apps.accounts import mfa
from apps.accounts.models import Department, Role, User
from apps.accounts.permissions import has_cap
from apps.approvals.models import Approval, ApprovalStep, ApprovalWorkflow, ApproverRole
from apps.audit.models import AuditLog
from apps.bookings import services as bookings
from apps.bookings.models import BookingStatus
from apps.catalogue.models import Building, ResourceType

from .conftest import at

pytestmark = pytest.mark.django_db

CATALOGUE = reverse("manage:catalogue")
USER_NEW = reverse("manage:user_new")
PASSWORD = "Campus-Reserve-2026!"


def post_catalogue(client, action, **data):
    return client.post(CATALOGUE, {"action": action, **data})


def new_person(client, **over):
    data = {
        "first_name": "Riya",
        "last_name": "Kapoor",
        "username": "riya.k",
        "email": "riya.k@example.test",
        "vid": "12312345",
        "role": Role.STUDENT,
        "department": "",
        "designation": "",
        "password1": PASSWORD,
        "password2": PASSWORD,
    }
    data.update(over)
    return client.post(USER_NEW, data)


@pytest.fixture
def fm_client(facility_manager):
    c = Client()
    c.force_login(facility_manager)
    return c


@pytest.fixture
def admin_client(admin_user):
    c = Client()
    c.force_login(admin_user)
    return c


# ── Catalogue: create, edit, validate, audit ─────────────────────────────────


def test_facility_manager_creates_a_resource_type_through_the_console(fm_client, lpu):
    resp = post_catalogue(
        fm_client, "types.save", name="Seminar Hall", plural="", code="", category="space", icon="mic",
        accent="ink", sort_order=50, description="Talks and workshops", allowed_roles=[Role.FACULTY, Role.STAFF],
    )  # fmt: skip
    assert resp.status_code == 302 and resp.url.endswith("?tab=types")
    t = ResourceType.objects.get(institution=lpu, name="Seminar Hall")
    assert (t.code, t.plural, t.icon, t.accent) == ("seminar-hall", "Seminar Halls", "mic", "ink")
    assert sorted(t.allowed_roles) == [Role.FACULTY, Role.STAFF]
    log = AuditLog.objects.get(action="catalogue.type.create", target_id=str(t.pk))
    assert log.after["name"] == "Seminar Hall" and log.before is None


def test_resource_type_codes_are_unique_regardless_of_case(fm_client, room_type):
    resp = post_catalogue(fm_client, "types.save", name="Rooms", code="CLASSROOM", category="space", icon="door-open",
                          accent="orange", sort_order=10)  # fmt: skip
    assert resp.status_code == 200
    assert "already uses the code" in resp.content.decode()
    assert ResourceType.objects.filter(code__iexact="classroom").count() == 1


def test_resource_type_rejects_an_icon_the_design_system_does_not_have(fm_client):
    resp = post_catalogue(fm_client, "types.save", name="X", category="space", icon="<script>", accent="orange",
                          sort_order=1)  # fmt: skip
    assert resp.status_code == 200 and not ResourceType.objects.filter(name="X").exists()


def test_building_and_department_are_created_validated_and_audited(fm_client, lpu, block34):
    assert post_catalogue(fm_client, "buildings.save", code="37", name="Block 37", zone="Academic Zone",
                          map_x=40, map_y=60).status_code == 302  # fmt: skip
    b = Building.objects.get(institution=lpu, code="37")
    assert AuditLog.objects.filter(action="catalogue.building.create", target_id=str(b.pk)).exists()

    dup = post_catalogue(fm_client, "buildings.save", code=block34.code.lower(), name="Again", map_x=1, map_y=1)
    assert dup.status_code == 200 and "already uses the block code" in dup.content.decode()
    off_map = post_catalogue(fm_client, "buildings.save", code="99", name="Far", map_x=150, map_y=1)
    assert off_map.status_code == 200 and not Building.objects.filter(code="99").exists()

    assert (
        post_catalogue(fm_client, "departments.save", code="ECE", name="Electronics", school="Engineering").status_code
        == 302
    )
    d = Department.objects.get(institution=lpu, code="ECE")
    assert AuditLog.objects.filter(action="catalogue.department.create", target_id=str(d.pk)).exists()


def test_editing_records_before_and_after(fm_client, block34):
    resp = post_catalogue(fm_client, "buildings.save", pk=block34.pk, code=block34.code, name="Block 34 (Library)",
                          map_x=50, map_y=50)  # fmt: skip
    assert resp.status_code == 302
    block34.refresh_from_db()
    assert block34.name == "Block 34 (Library)"
    log = AuditLog.objects.get(action="catalogue.building.update", target_id=str(block34.pk))
    assert log.before["name"] == "Block 34" and log.after["name"] == "Block 34 (Library)"


def test_records_in_use_cannot_be_removed_but_unused_ones_can(fm_client, room, room_type, lpu):
    post_catalogue(fm_client, "types.delete", pk=room_type.pk)
    assert ResourceType.objects.filter(pk=room_type.pk).exists()  # a resource still uses it
    spare = ResourceType.objects.create(institution=lpu, code="spare", name="Spare", category="space")
    post_catalogue(fm_client, "types.delete", pk=spare.pk)
    assert not ResourceType.objects.filter(pk=spare.pk).exists()
    assert AuditLog.objects.filter(action="catalogue.type.delete", target_id=str(spare.pk)).exists()


def test_a_resource_can_be_added_with_the_new_type_and_block(fm_client, lpu):
    post_catalogue(fm_client, "types.save", name="Classroom", category="space", icon="door-open", accent="orange",
                   sort_order=10)  # fmt: skip
    post_catalogue(fm_client, "buildings.save", code="34", name="Block 34", map_x=50, map_y=50)
    t, b = ResourceType.objects.get(code="classroom"), Building.objects.get(code="34")
    form = fm_client.get(reverse("manage:resource_new")).content.decode()
    assert f'value="{t.pk}"' in form and "Add a resource type first" not in form
    assert b.institution_id == lpu.pk


def test_resource_page_points_to_the_catalogue_when_there_are_no_types(fm_client):
    body = fm_client.get(reverse("manage:resource_new")).content.decode()
    assert "Add a resource type first" in body and reverse("manage:catalogue") in body


@pytest.mark.parametrize("who", ["custodian", "student", "faculty"])
def test_catalogue_is_campus_staff_only(request, who):
    c = Client()
    c.force_login(request.getfixturevalue(who))
    assert c.get(CATALOGUE).status_code == 403
    assert post_catalogue(c, "buildings.save", code="1", name="X", map_x=1, map_y=1).status_code == 403
    assert not Building.objects.filter(code="1").exists()


def test_head_of_department_cannot_edit_the_catalogue(make_user):
    c = Client()
    c.force_login(make_user(Role.DEPT_HEAD))
    assert c.get(CATALOGUE).status_code == 403


def test_anonymous_visitors_are_sent_to_sign_in(client):
    resp = client.get(CATALOGUE)
    assert resp.status_code == 302 and reverse("accounts:login") in resp.url


def test_setup_hub_lists_the_catalogue_for_campus_staff(fm_client):
    assert reverse("manage:catalogue") in fm_client.get(reverse("manage:setup")).content.decode()


# ── Administrator-created accounts ──────────────────────────────────────────


def test_administrator_creates_an_active_student(admin_client, admin_user, cse):
    resp = new_person(admin_client, department=cse.pk)
    assert resp.status_code == 302
    u = User.objects.get(username="riya.k")
    assert u.is_active and not u.is_staff and not u.is_superuser
    assert (u.role, u.department, u.institution_id) == (Role.STUDENT, cse, admin_user.institution_id)
    assert u.check_password(PASSWORD) and u.password != PASSWORD  # stored hashed only
    assert authenticate(username="riya.k", password=PASSWORD) == u
    assert has_cap(u, "book_resources") and not has_cap(u, "approve_bookings")  # role group assigned
    log = AuditLog.objects.get(action="user.create", target_id=str(u.pk))
    assert log.actor == admin_user and log.after["role"] == Role.STUDENT and log.after["department"] == "CSE"
    assert PASSWORD not in str(log.after) and PASSWORD not in str(log.before)


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("username", "Student1", "already signs in as"),
        ("email", "STUDENT1@example.test", "already belongs to another account"),
        ("vid", "dup-vid", "already belongs to another account"),
    ],
)
def test_duplicates_are_refused(admin_client, make_user, field, value, message):
    existing = make_user(Role.STUDENT, username="student1", email="student1@example.test", vid="dup-vid")
    resp = new_person(admin_client, **{field: value})
    assert resp.status_code == 200 and message in resp.content.decode()
    assert (
        User.objects.filter(**{f"{field}__iexact": value}).count() == 1 == User.objects.filter(pk=existing.pk).count()
    )


@pytest.mark.parametrize(
    "p1,p2,message",
    [
        ("short", "short", "too short"),
        ("password123", "password123", "too common"),
        (PASSWORD, PASSWORD + "x", "don&#x27;t match"),
        ("riya.k-2026", "riya.k-2026", "too similar"),
    ],
)
def test_weak_or_mismatched_passwords_are_refused(admin_client, p1, p2, message):
    resp = new_person(admin_client, password1=p1, password2=p2)
    assert resp.status_code == 200 and message in resp.content.decode()
    assert not User.objects.filter(username="riya.k").exists()


def test_a_head_of_department_needs_a_department(admin_client):
    resp = new_person(admin_client, role=Role.DEPT_HEAD)
    assert resp.status_code == 200 and "needs a department" in resp.content.decode()


def test_superuser_and_staff_flags_cannot_be_granted(admin_client):
    new_person(admin_client, is_superuser="on", is_staff="on")
    u = User.objects.get(username="riya.k")
    assert not u.is_superuser and not u.is_staff


@pytest.mark.parametrize("who", ["facility_manager", "custodian", "student"])
def test_only_administrators_can_create_accounts(request, who):
    c = Client()
    c.force_login(request.getfixturevalue(who))
    assert c.get(USER_NEW).status_code == 403
    assert new_person(c).status_code == 403
    assert not User.objects.filter(username="riya.k").exists()


def test_users_page_offers_the_button_to_administrators_only(admin_client, fm_client):
    assert USER_NEW in admin_client.get(reverse("manage:users")).content.decode()
    assert USER_NEW not in fm_client.get(reverse("manage:users")).content.decode()


# ── MFA for created accounts ────────────────────────────────────────────────


def sign_in_with_password(username):
    c = Client()
    resp = c.post(reverse("accounts:login"), {"username": username, "password": PASSWORD})
    return c, resp


def enrol_and_verify(c) -> str:
    page = c.get(reverse("accounts:mfa")).content.decode()
    assert "Set up two-step sign-in" in page
    key = re.search(r'<code class="mfa-key">([A-Z2-7]+)</code>', page).group(1)
    assert c.post(reverse("accounts:mfa"), {"code": pyotp.TOTP(key).now()}).status_code == 302
    return key


def test_a_created_privileged_account_must_enrol_mfa_before_anything_else(admin_client):
    new_person(admin_client, username="fm.new", email="fm.new@example.test", vid="", role=Role.FACILITY_MANAGER)
    u = User.objects.get(username="fm.new")
    assert mfa.required_for(u) and not u.mfa_enabled
    c, resp = sign_in_with_password("fm.new")
    assert resp.status_code == 302 and resp.url == reverse("accounts:mfa")
    assert "_auth_user_id" not in c.session  # the password alone does not sign them in
    enrol_and_verify(c)
    u.refresh_from_db()
    assert u.mfa_enabled and mfa.under_current_key(u.mfa_secret)
    assert c.get(reverse("manage:setup")).status_code == 200


def test_a_created_student_signs_in_without_mfa(admin_client):
    new_person(admin_client)
    c, resp = sign_in_with_password("riya.k")
    assert resp.status_code == 302 and resp.url == "/home/"
    assert c.session.get("_auth_user_id") == str(User.objects.get(username="riya.k").pk)


# ── Approval workflow with two people created through the console ───────────


def test_approval_workflow_with_two_created_people(admin_client, lpu, room, room_type, monday, now):
    workflow = ApprovalWorkflow.objects.create(institution=lpu, name="Classrooms", resource_type=room_type)
    ApprovalStep.objects.create(workflow=workflow, order=1, approver_role=ApproverRole.FACILITY_MANAGER)

    new_person(admin_client, username="req.student", email="req@example.test", vid="")
    new_person(admin_client, username="appr.fm", email="appr@example.test", vid="", role=Role.FACILITY_MANAGER)
    requester = User.objects.get(username="req.student")

    booking = bookings.create_booking(
        requester=requester, resource=room, start=at(monday, 10), end=at(monday, 11), title="Study group", now=now
    )
    assert booking.status == BookingStatus.PENDING

    approver, _ = sign_in_with_password("appr.fm")
    enrol_and_verify(approver)
    approval = Approval.objects.get(booking=booking)
    assert (
        approver.post(reverse("manage:approval_decide", args=[approval.pk]), {"action": "approve"}).status_code == 302
    )

    booking.refresh_from_db()
    assert booking.status == BookingStatus.APPROVED
    me, _ = sign_in_with_password("req.student")
    page = me.get(booking.get_absolute_url()).content.decode()
    assert "Study group" in page and "Confirmed" in page
    assert AuditLog.objects.filter(action__startswith="approval", actor__username="appr.fm").exists()
