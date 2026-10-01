"""
TOTP MFA end to end, through the real views and the real pyotp parameters (SHA-1, 6 digits,
30-second steps; what Google Authenticator uses).

Includes the regression for the local sign-in failure of 2026-10-01: a secret enrolled under one
DJANGO_SECRET_KEY was unreadable after the key changed, so every correct code was reported as
"didn't match" and counted towards the lockout.
"""

import re
import time
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.accounts import mfa
from apps.accounts.models import User
from apps.accounts.views import MFA_UNREADABLE_MESSAGE
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

PW = "x-test-password-123"  # conftest.make_user's password
OLD_KEY = "old-key-" + "a" * 40
NEW_KEY = "new-key-" + "b" * 40
DIDNT_MATCH = "didn&#x27;t match"


def _password_step(client, user):
    resp = client.post(reverse("accounts:login"), {"username": user.username, "password": PW})
    assert resp.status_code == 302 and resp.url == reverse("accounts:mfa")


def _submit(client, code):
    return client.post(reverse("accounts:mfa"), {"code": code})


def _enrol(user) -> str:
    secret = pyotp.random_base32()
    user.mfa_secret = mfa.encrypt(secret)
    user.mfa_enabled = True
    user.save(update_fields=["mfa_secret", "mfa_enabled"])
    return secret


def _signed_in(client, user) -> bool:
    return client.session.get("_auth_user_id") == str(user.pk) and mfa.session_verified(
        type("R", (), {"session": client.session})(), user
    )


# ── The verification function with the application's parameters ────────────


def test_known_secret_and_time_give_the_expected_step():
    secret = "JBSWY3DPEHPK3PXP"  # a fixed test secret
    at = 1_700_000_000
    expected = pyotp.TOTP(secret, digits=6, interval=30, digest="sha1").at(at)
    assert mfa.matched_step(secret, expected, for_time=at) == at // 30
    assert mfa.matched_step(secret, expected[:3] + " " + expected[3:], for_time=at) == at // 30  # grouped
    assert mfa.matched_step(secret, expected, for_time=at + 30) == at // 30  # one step of drift
    assert mfa.matched_step(secret, expected, for_time=at + 90) is None  # beyond the window
    wrong = f"{(int(expected) + 1) % 1_000_000:06d}"
    assert mfa.matched_step(secret, wrong, for_time=at) is None


def test_provisioning_uri_uses_authenticator_defaults():
    secret = pyotp.random_base32()
    user = User(username="someone", vid="12345678")
    uri = urlparse(mfa.provisioning_uri(user, secret))
    params = parse_qs(uri.query)
    assert uri.scheme == "otpauth" and uri.netloc == "totp"
    assert params["secret"] == [secret] and params["issuer"] == ["LPU Reserve"]
    # Absent algorithm/digits/period mean SHA1/6/30 to every authenticator, which is what we verify with.
    assert not {"algorithm", "digits", "period"} & params.keys()


# ── Enrolment and sign-in through the views ─────────────────────────────────


def test_enrolment_creates_a_valid_secret_and_the_same_secret_is_used_at_sign_in(client, admin_user):
    _password_step(client, admin_user)
    page = client.get(reverse("accounts:mfa")).content.decode()
    shown = re.search(r'<code class="mfa-key">([A-Z2-7]+)</code>', page).group(1)
    assert len(shown) >= 32  # 160-bit base32 secret
    assert _submit(client, pyotp.TOTP(shown).now()).status_code == 302
    admin_user.refresh_from_db()
    assert admin_user.mfa_enabled and mfa.decrypt(admin_user.mfa_secret) == shown
    assert AuditLog.objects.filter(action="auth.mfa_enrolled", target_id=str(admin_user.pk)).exists()

    # Next sign-in: a code from the secret the person scanned is accepted (next step: no replay).
    client.logout()
    _password_step(client, admin_user)
    next_code = pyotp.TOTP(shown).at(time.time() + 30)
    assert _submit(client, next_code).status_code == 302
    assert _signed_in(client, admin_user)


def test_valid_current_code_is_accepted_and_session_state_is_cleaned(client, admin_user):
    secret = _enrol(admin_user)
    _password_step(client, admin_user)
    assert client.session.get("mfa_pending") == admin_user.pk
    resp = _submit(client, pyotp.TOTP(secret).now())
    assert resp.status_code == 302
    assert _signed_in(client, admin_user)
    assert not {"mfa_pending", "mfa_pending_at", "mfa_next", "mfa_new_secret"} & set(client.session.keys())


def test_invalid_code_is_rejected_and_counted(client, admin_user):
    secret = _enrol(admin_user)
    totp = pyotp.TOTP(secret)
    valid = {totp.at(time.time() + d) for d in (-60, -30, 0, 30, 60)}
    wrong = next(c for c in ("000000", "111111", "222222") if c not in valid)
    _password_step(client, admin_user)
    resp = _submit(client, wrong)
    assert resp.status_code == 200 and DIDNT_MATCH in resp.content.decode()
    assert not _signed_in(client, admin_user)
    admin_user.refresh_from_db()
    assert admin_user.failed_logins == 1


def test_first_use_code_is_not_mistaken_for_a_replay(client, admin_user):
    secret = _enrol(admin_user)
    assert admin_user.mfa_last_step is None  # never used: nothing to replay
    _password_step(client, admin_user)
    assert _submit(client, pyotp.TOTP(secret).now()).status_code == 302
    admin_user.refresh_from_db()
    assert admin_user.mfa_last_step == int(time.time() // 30) or admin_user.mfa_last_step == int(time.time() // 30) - 1


def test_replayed_code_is_rejected(client, admin_user):
    secret = _enrol(admin_user)
    code = pyotp.TOTP(secret).now()
    _password_step(client, admin_user)
    assert _submit(client, code).status_code == 302
    client.logout()
    _password_step(client, admin_user)
    resp = _submit(client, code)
    assert resp.status_code == 200 and "already been used" in resp.content.decode()
    assert not _signed_in(client, admin_user)


# ── Root cause regression: the secret key changed ───────────────────────────


def test_secret_from_an_old_key_is_reported_as_unreadable_not_as_a_wrong_code(client, admin_user, settings):
    settings.SECRET_KEY = OLD_KEY
    secret = _enrol(admin_user)
    settings.SECRET_KEY = NEW_KEY  # the key changed, no fallback configured
    settings.SECRET_KEY_FALLBACKS = []
    _password_step(client, admin_user)
    for _ in range(6):  # more than the lockout threshold
        resp = _submit(client, pyotp.TOTP(secret).now())
        body = resp.content.decode()
        assert resp.status_code == 200
        assert DIDNT_MATCH not in body
        assert "server configuration problem" in body
    admin_user.refresh_from_db()
    assert admin_user.failed_logins == 0 and not admin_user.is_locked  # not the person's fault
    assert not _signed_in(client, admin_user)  # and still no way in without a readable secret
    assert AuditLog.objects.filter(action="auth.mfa_secret_unreadable", target_id=str(admin_user.pk)).count() == 1
    assert MFA_UNREADABLE_MESSAGE


def test_old_key_as_fallback_restores_sign_in_and_moves_the_secret(client, admin_user, settings):
    settings.SECRET_KEY = OLD_KEY
    secret = _enrol(admin_user)
    settings.SECRET_KEY = NEW_KEY
    settings.SECRET_KEY_FALLBACKS = [OLD_KEY]
    _password_step(client, admin_user)
    assert _submit(client, pyotp.TOTP(secret).now()).status_code == 302
    assert _signed_in(client, admin_user)
    admin_user.refresh_from_db()
    assert mfa.under_current_key(admin_user.mfa_secret)  # re-encrypted at sign-in
    settings.SECRET_KEY_FALLBACKS = []  # so the fallback can now be removed
    assert mfa.decrypt(admin_user.mfa_secret) == secret


def test_key_change_during_enrolment_restarts_cleanly(client, admin_user, settings):
    settings.SECRET_KEY = OLD_KEY
    _password_step(client, admin_user)
    client.get(reverse("accounts:mfa"))
    settings.SECRET_KEY = NEW_KEY  # sessions are signed too: the half-finished sign-in is gone
    resp = client.get(reverse("accounts:mfa"))
    assert resp.status_code == 302 and resp.url == reverse("accounts:login")
    _password_step(client, admin_user)
    page = client.get(reverse("accounts:mfa")).content.decode()
    shown = re.search(r'<code class="mfa-key">([A-Z2-7]+)</code>', page).group(1)
    assert "server configuration problem" not in page
    assert _submit(client, pyotp.TOTP(shown).now()).status_code == 302
    admin_user.refresh_from_db()
    assert mfa.under_current_key(admin_user.mfa_secret)


def test_mfa_keys_command_reports_and_rotates(admin_user, make_user, settings, capsys):
    from apps.accounts.models import Role

    settings.SECRET_KEY = OLD_KEY
    _enrol(admin_user)
    lost = make_user(Role.FACILITY_MANAGER, department=None)
    settings.SECRET_KEY = "lost-key-" + "c" * 40
    _enrol(lost)
    settings.SECRET_KEY = NEW_KEY
    settings.SECRET_KEY_FALLBACKS = [OLD_KEY]
    with pytest.raises(CommandError, match=lost.username):
        call_command("mfa_keys")
    assert f"fallback key only: 1 ({admin_user.username})" in capsys.readouterr().out
    with pytest.raises(CommandError):
        call_command("mfa_keys", "--rotate")
    admin_user.refresh_from_db()
    assert mfa.under_current_key(admin_user.mfa_secret)


def test_production_refuses_a_weak_fallback_key(monkeypatch):
    import runpy
    from pathlib import Path

    import environ
    from django.core.exceptions import ImproperlyConfigured

    monkeypatch.setattr(environ.Env, "read_env", lambda *a, **k: None)
    monkeypatch.setenv("DEBUG", "0")
    monkeypatch.setenv("DEMO_MODE", "0")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "k" * 50)
    monkeypatch.setenv("DJANGO_SECRET_KEY_FALLBACKS", "dev-only-insecure-key-change-me")
    with pytest.raises(ImproperlyConfigured):
        runpy.run_path(str(Path(__file__).resolve().parent.parent / "config" / "settings.py"))
