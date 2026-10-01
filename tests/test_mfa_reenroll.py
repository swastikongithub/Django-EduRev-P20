"""
Re-enrolling a local development account whose TOTP secret became unreadable
(`manage.py mfa_reenroll`), then signing in to Django admin through the normal MFA step.

Mirrors the local account repaired on 2026-10-02: role student, superuser, MFA enrolled under a
DJANGO_SECRET_KEY that is no longer configured.
"""

import re
import time

import pyotp
import pytest
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.urls import reverse

from apps.accounts import mfa
from apps.accounts.models import Role
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

PW = "x-test-password-123"  # conftest.make_user's password
GONE_KEY = "a-key-this-database-no-longer-uses-" + "z" * 20


@pytest.fixture
def stale_superuser(make_user, settings):
    """A superuser whose enrolment was encrypted under a key the server no longer has."""
    user = make_user(Role.STUDENT, is_staff=True, is_superuser=True)
    current = settings.SECRET_KEY
    settings.SECRET_KEY = GONE_KEY
    user.mfa_secret = mfa.encrypt(pyotp.random_base32())
    user.mfa_enabled = True
    user.mfa_last_step = int(time.time() // 30) - 10
    user.save(update_fields=["mfa_secret", "mfa_enabled", "mfa_last_step"])
    settings.SECRET_KEY = current
    assert mfa.decrypt(user.mfa_secret) is None  # the reported local state
    return user


def _admin_password_step(client, user):
    resp = client.post("/django-admin/login/", {"username": user.username, "password": PW, "next": "/django-admin/"})
    assert resp.status_code == 302 and resp.url == reverse("accounts:mfa")


def _enrolment_key(client) -> str:
    page = client.get(reverse("accounts:mfa")).content.decode()
    assert "Set up two-step sign-in" in page
    assert "<svg" in page  # the QR code
    return re.search(r'<code class="mfa-key">([A-Z2-7]+)</code>', page).group(1)


def _reenroll(settings, username):
    settings.DEBUG = True  # the command is local-development only
    call_command("mfa_reenroll", username)
    settings.DEBUG = False


def test_reenrolled_superuser_signs_in_to_django_admin(client, stale_superuser, settings):
    _reenroll(settings, stale_superuser.username)
    stale_superuser.refresh_from_db()
    assert not stale_superuser.mfa_enabled and stale_superuser.mfa_secret == ""
    assert stale_superuser.mfa_last_step is not None  # replay counter kept

    _admin_password_step(client, stale_superuser)
    key = _enrolment_key(client)
    resp = client.post(reverse("accounts:mfa"), {"code": pyotp.TOTP(key).now()})
    assert resp.status_code == 302 and resp.url == "/django-admin/"
    assert client.get("/django-admin/").status_code == 200  # the admin index, signed in with MFA

    stale_superuser.refresh_from_db()
    assert stale_superuser.mfa_enabled
    assert mfa.under_current_key(stale_superuser.mfa_secret)  # encrypted with the current key
    assert mfa.decrypt(stale_superuser.mfa_secret) == key  # the secret the authenticator scanned
    assert AuditLog.objects.filter(action="auth.mfa_reset", target_id=str(stale_superuser.pk)).exists()
    assert AuditLog.objects.filter(action="auth.mfa_enrolled", target_id=str(stale_superuser.pk)).exists()


def test_invalid_and_replayed_codes_are_rejected_after_reenrolment(client, stale_superuser, settings):
    _reenroll(settings, stale_superuser.username)
    _admin_password_step(client, stale_superuser)
    key = _enrolment_key(client)
    totp = pyotp.TOTP(key)
    valid = {totp.at(time.time() + d) for d in (-60, -30, 0, 30, 60)}
    wrong = next(c for c in ("000000", "111111", "222222") if c not in valid)

    resp = client.post(reverse("accounts:mfa"), {"code": wrong})
    assert resp.status_code == 200 and "didn&#x27;t match" in resp.content.decode()
    assert client.get("/django-admin/").status_code == 302  # still not signed in

    code = totp.now()
    assert client.post(reverse("accounts:mfa"), {"code": code}).status_code == 302

    other = Client()
    _admin_password_step(other, stale_superuser)
    resp = other.post(reverse("accounts:mfa"), {"code": code})  # the same code again
    assert resp.status_code == 200 and "already been used" in resp.content.decode()
    assert other.get("/django-admin/").status_code == 302


def test_reenrolment_ends_existing_sessions(stale_superuser, settings):
    c = Client()
    c.force_login(stale_superuser)
    assert Session.objects.count() == 1
    _reenroll(settings, stale_superuser.username)
    assert Session.objects.count() == 0


def test_command_is_local_development_only(stale_superuser, settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG is off"):
        call_command("mfa_reenroll", stale_superuser.username)
    stale_superuser.refresh_from_db()
    assert stale_superuser.mfa_enabled  # untouched


def test_command_refuses_a_remote_database(stale_superuser, settings, monkeypatch):
    from django.db import connection

    settings.DEBUG = True
    monkeypatch.setitem(connection.settings_dict, "HOST", "db.example.com")
    with pytest.raises(CommandError, match="db.example.com"):
        call_command("mfa_reenroll", stale_superuser.username)


def test_command_needs_an_existing_username(settings):
    settings.DEBUG = True
    with pytest.raises(CommandError, match="No account"):
        call_command("mfa_reenroll", "nobody-by-this-name")


def test_mfa_policy_is_untouched():
    assert settings.MFA_ENFORCED is True
    assert {"admin", "facility_manager"} <= set(settings.MFA_REQUIRED_ROLES)
