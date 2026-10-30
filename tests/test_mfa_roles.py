"""
The MFA policy for every role: everyone except students must pass TOTP (CES §1.1), through the
real sign-in views and MFASessionMiddleware. Superusers and Django admin access (is_staff) always
need it, whatever their role. Students keep a password-only sign-in.
"""

import time

import pyotp
import pytest
from django.conf import settings
from django.core.checks import run_checks
from django.test import override_settings
from django.urls import reverse

from apps.accounts import mfa
from apps.accounts.manage_views import change_role
from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db

PW = "x-test-password-123"  # conftest.make_user's password
REQUIRED = [Role.FACULTY, Role.STAFF, Role.CUSTODIAN, Role.DEPT_HEAD, Role.FACILITY_MANAGER, Role.ADMIN]


def _make(make_user, role, **kw):
    campus_wide = role in (Role.FACILITY_MANAGER, Role.ADMIN)
    return make_user(role, department=None, **kw) if campus_wide else make_user(role, **kw)


def _password(client, user, **extra):
    return client.post(reverse("accounts:login"), {"username": user.username, "password": PW, **extra})


def _enrol(user) -> str:
    secret = pyotp.random_base32()
    user.mfa_secret = mfa.encrypt(secret)
    user.mfa_enabled = True
    user.save(update_fields=["mfa_secret", "mfa_enabled"])
    return secret


def _session_user(client):
    return client.session.get("_auth_user_id")


def _verified(client, user) -> bool:
    return _session_user(client) == str(user.pk) and client.session.get(mfa.SESSION_KEY) == user.pk


# ── The configured policy ───────────────────────────────────────────────────


def test_default_policy_covers_every_role_except_student():
    assert settings.MFA_ENFORCED is True
    assert set(settings.MFA_REQUIRED_ROLES) == set(Role.values) - {Role.STUDENT}
    assert set(settings.MFA_REQUIRED_ROLES) <= set(Role.values)  # real identifiers only


@pytest.mark.parametrize("role", REQUIRED)
def test_required_roles_need_mfa(make_user, role):
    assert mfa.required_for(_make(make_user, role))


def test_student_does_not_need_mfa(student):
    assert not mfa.required_for(student) and not mfa.needs_mfa(student)


def test_django_admin_access_needs_mfa_whatever_the_role(make_user):
    # is_staff is Django's admin-site flag, not the `staff` role: it can never exempt anyone.
    assert mfa.required_for(make_user(Role.STUDENT, is_staff=True))
    assert mfa.required_for(make_user(Role.STUDENT, is_superuser=True))


def test_unknown_role_identifier_fails_the_system_check():
    with override_settings(MFA_REQUIRED_ROLES=["faculty", "dept-head", "Admin"]):
        errors = [e for e in run_checks() if e.id == "lpu.E005"]
    assert len(errors) == 1 and "Admin, dept-head" in errors[0].msg
    assert not [e for e in run_checks() if e.id == "lpu.E005"]


# ── Required roles: enrolment, then verification ────────────────────────────


@pytest.mark.parametrize("role", REQUIRED)
def test_required_role_without_mfa_must_enrol_before_any_session(client, make_user, role):
    user = _make(make_user, role)
    resp = _password(client, user)
    assert resp.status_code == 302 and resp.url == reverse("accounts:mfa")
    assert _session_user(client) is None  # a correct password alone signs nobody in
    assert client.get(reverse("core:home")).status_code == 302  # still anonymous

    page = client.get(reverse("accounts:mfa"))
    assert page.context["enrolling"] is True
    secret = page.context["secret"]
    resp = client.post(reverse("accounts:mfa"), {"code": pyotp.TOTP(secret).now()})
    assert resp.status_code == 302 and _verified(client, user)

    user.refresh_from_db()
    assert user.mfa_enabled
    assert secret not in user.mfa_secret and mfa.decrypt(user.mfa_secret) == secret  # encrypted at rest
    assert client.get(reverse("core:home")).status_code == 200


@pytest.mark.parametrize("role", REQUIRED)
def test_enrolled_required_role_signs_in_with_password_and_code(client, make_user, role):
    user = _make(make_user, role)
    secret = _enrol(user)
    assert _password(client, user).url == reverse("accounts:mfa")
    assert client.get(reverse("accounts:mfa")).context["enrolling"] is False
    client.post(reverse("accounts:mfa"), {"code": pyotp.TOTP(secret).now()})
    assert _verified(client, user)
    user.refresh_from_db()
    assert mfa.decrypt(user.mfa_secret) == secret  # signing in never re-enrols


def test_enrolled_superuser_administrator_keeps_working(client, make_user):
    admin = make_user(Role.ADMIN, department=None, is_staff=True, is_superuser=True)
    secret = _enrol(admin)
    _password(client, admin)
    client.post(reverse("accounts:mfa"), {"code": pyotp.TOTP(secret).now()})
    assert _verified(client, admin)
    assert client.get("/django-admin/").status_code == 200


# ── Students keep a password-only sign-in ───────────────────────────────────


def test_student_signs_in_with_password_only(client, student):
    resp = _password(client, student)
    assert resp.status_code == 302 and resp.url != reverse("accounts:mfa")
    assert _session_user(client) == str(student.pk)
    assert client.get(reverse("core:home")).status_code == 200
    student.refresh_from_db()
    assert not student.mfa_enabled


def test_student_who_enrolled_voluntarily_is_held_to_it(client, student):
    _enrol(student)
    assert _password(client, student).url == reverse("accounts:mfa")


# ── No way around it ────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", REQUIRED)
@pytest.mark.parametrize("path", ["/home/", "/manage/", "/manage/approvals/", "/django-admin/", "/api/v1/me/"])
def test_unverified_session_reaches_nothing(client, make_user, role, path):
    """A session without the MFA stamp (here: signed in as a student, then the role changed) is ended."""
    user = make_user(Role.STUDENT)
    client.force_login(user)  # a student session carries no MFA stamp
    User.objects.filter(pk=user.pk).update(role=role)
    resp = client.get(path)
    if path.startswith("/api/"):
        assert resp.status_code == 401 and resp.json()["error"]["code"] == "mfa_required"
    else:
        assert resp.status_code == 302 and reverse("accounts:login") in resp.url
    assert _session_user(client) is None  # the session itself is gone, not just this request


@pytest.mark.parametrize("role", REQUIRED)
def test_request_parameters_cannot_skip_the_second_factor(client, make_user, role):
    user = _make(make_user, role)
    resp = _password(client, user, role="student", mfa="1", mfa_verified="1", next="/manage/")
    assert resp.url == reverse("accounts:mfa") and _session_user(client) is None
    assert client.get(reverse("core:home"), {"mfa": "1", "role": "student"}).status_code == 302
    # The pending user comes from the server-side session only, never from the request.
    other = make_user(Role.STUDENT)
    client.post(reverse("accounts:mfa"), {"code": "000000", "user": other.pk, "mfa_pending": other.pk})
    assert _session_user(client) is None


def test_mfa_step_without_a_password_step_cannot_enrol(client, faculty):
    assert client.get(reverse("accounts:mfa")).url == reverse("accounts:login")
    resp = client.post(reverse("accounts:mfa"), {"code": "123456"})
    assert resp.status_code == 302 and resp.url == reverse("accounts:login")
    faculty.refresh_from_db()
    assert not faculty.mfa_enabled and not faculty.mfa_secret


def test_changing_role_reevaluates_the_requirement(client, student, admin_user):
    client.force_login(student)
    assert client.get(reverse("core:home")).status_code == 200
    change_role(student, Role.FACULTY, actor=admin_user)
    assert client.get(reverse("core:home")).status_code == 302 and _session_user(client) is None
    assert _password(client, student).url == reverse("accounts:mfa")  # next sign-in must enrol


def test_people_cannot_change_their_own_role(client, faculty):
    client.force_login(faculty)
    assert client.patch("/api/v1/me/", {"role": "student"}, content_type="application/json").status_code == 405
    assert client.post(
        reverse("manage:users"), {"user": faculty.pk, "action": "role", "role": "student"}
    ).status_code in (
        302,
        403,
    )
    faculty.refresh_from_db()
    assert faculty.role == Role.FACULTY


def test_demoted_but_enrolled_user_still_needs_mfa(client, faculty, admin_user):
    _enrol(faculty)
    change_role(faculty, Role.STUDENT, actor=admin_user)
    faculty.refresh_from_db()
    assert mfa.needs_mfa(faculty)  # an enrolment is never silently dropped by a role change


# ── Expiry, wrong codes, replay ─────────────────────────────────────────────


def test_expired_pending_sign_in_is_rejected(client, faculty):
    secret = _enrol(faculty)
    _password(client, faculty)
    session = client.session
    session["mfa_pending_at"] = int(time.time()) - 11 * 60
    session.save()
    resp = client.post(reverse("accounts:mfa"), {"code": pyotp.TOTP(secret).now()})
    assert resp.url == reverse("accounts:login") and _session_user(client) is None
    assert "mfa_pending" not in client.session


def test_wrong_code_is_rejected_and_counted(client, custodian):
    secret = _enrol(custodian)
    _password(client, custodian)
    wrong = f"{(int(pyotp.TOTP(secret).now()) + 1) % 1_000_000:06d}"
    resp = client.post(reverse("accounts:mfa"), {"code": wrong})
    assert resp.status_code == 200 and _session_user(client) is None
    custodian.refresh_from_db()
    assert custodian.failed_logins == 1


def test_wrong_codes_lock_the_account(client, make_user):
    head = make_user(Role.DEPT_HEAD)
    _enrol(head)
    _password(client, head)
    for _ in range(settings.LOGIN_LOCKOUT_THRESHOLD):
        client.post(reverse("accounts:mfa"), {"code": "000000"})
    head.refresh_from_db()
    assert head.is_locked


@pytest.mark.parametrize("role", [Role.FACULTY, Role.STAFF])
def test_a_used_code_is_never_accepted_again(client, make_user, role):
    user = make_user(role)
    secret = _enrol(user)
    code = pyotp.TOTP(secret).now()
    _password(client, user)
    client.post(reverse("accounts:mfa"), {"code": code})
    assert _verified(client, user)
    client.post(reverse("accounts:logout"))
    _password(client, user)
    replay = client.post(reverse("accounts:mfa"), {"code": code})
    assert replay.status_code == 200 and "already been used" in replay.content.decode()
    assert _session_user(client) is None


def test_session_stamped_for_someone_else_is_rejected(client, faculty, make_user):
    other = make_user(Role.FACULTY)
    client.force_login(faculty)
    session = client.session
    session[mfa.SESSION_KEY] = other.pk  # a stamp that is not this user's
    session.save()
    assert client.get(reverse("core:home")).status_code == 302 and _session_user(client) is None
