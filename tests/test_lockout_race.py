"""
The account lockout must hold under concurrent requests (Phase 3 security QA).

Twelve wrong answers fired at the same instant, from twelve separate connections, must lock
the account just as twelve one-after-the-other would. A read-modify-write of the failure count
lets concurrent requests overwrite each other, so a burst of guesses never reaches the
threshold; the count is now changed under a row lock.
"""

from __future__ import annotations

import threading

import pyotp
import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.urls import reverse

from apps.accounts import mfa
from apps.accounts.models import Role, User

pytestmark = [pytest.mark.concurrency, pytest.mark.django_db(transaction=True)]

ATTEMPTS = 12  # below the 20/min per-IP rate limit, so only the lockout can stop them
PW = "x-test-password-123"


def _burst(prepare, fire):
    """Prepare one client per thread, then release all requests together."""
    clients = [prepare() for _ in range(ATTEMPTS)]
    barrier = threading.Barrier(ATTEMPTS)
    errors = []

    def worker(c):
        try:
            barrier.wait(timeout=30)
            fire(c)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(repr(exc))
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(c,)) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert errors == []


@pytest.fixture(autouse=True)
def _empty_rate_limit_buckets():
    cache.clear()
    yield
    cache.clear()


def test_concurrent_wrong_passwords_lock_the_account(make_user):
    victim = make_user(Role.STUDENT)
    login = reverse("accounts:login")
    _burst(Client, lambda c: c.post(login, {"username": victim.username, "password": "wrong-guess"}))

    victim.refresh_from_db()
    assert victim.is_locked
    resp = Client().post(login, {"username": victim.username, "password": PW})
    assert resp.status_code == 200 and "_auth_user_id" not in resp.client.session


def test_concurrent_wrong_codes_lock_the_account(make_user):
    admin = make_user(Role.ADMIN, department=None)
    secret = pyotp.random_base32()
    User.objects.filter(pk=admin.pk).update(mfa_secret=mfa.encrypt(secret), mfa_enabled=True)
    totp = pyotp.TOTP(secret)
    wrong = next(c for c in ("000000", "111111", "222222", "333333") if not totp.verify(c, valid_window=2))
    login, verify = reverse("accounts:login"), reverse("accounts:mfa")

    def signed_in_with_password():
        c = Client()
        assert c.post(login, {"username": admin.username, "password": PW}).url == verify
        return c

    _burst(signed_in_with_password, lambda c: c.post(verify, {"code": wrong}))

    admin.refresh_from_db()
    assert admin.is_locked
