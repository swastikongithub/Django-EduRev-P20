"""
First-run setup (apps.accounts.bootstrap): the first administrator of an installation that has no
accounts, and nothing else.

Covers the state detection, what the created account is (and is not), validation, the audit
record, the takeover cases (any existing account closes the page for GET and POST), CSRF, rate
limiting, the optional setup code, MFA at first sign-in, `createsuperuser` as the operator
fallback, and concurrent attempts: exactly one administrator however many requests race.
"""

from __future__ import annotations

import json
import threading

import pyotp
import pytest
from django.contrib.auth.hashers import identify_hasher
from django.core.management import call_command
from django.db import connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts import bootstrap
from apps.accounts.bootstrap import BootstrapClosed, BootstrapForm, create_first_administrator
from apps.accounts.models import Role, User
from apps.audit.models import AuditLog

URL = "/setup/bootstrap/"
PASSWORD = "x-test-password-456"


def form_data(**over):
    data = {
        "full_name": "Asha Verma",
        "email": "Asha.Verma@example.test",
        "username": "asha.admin",
        "password1": PASSWORD,
        "password2": PASSWORD,
    }
    data.update(over)
    return data


@pytest.fixture
def empty(db):
    assert not User.objects.exists()


# ── State detection ─────────────────────────────────────────────────────────


def test_required_only_while_there_are_no_accounts(empty, make_user):
    assert bootstrap.is_system_bootstrap_required()
    make_user(Role.STUDENT)
    assert not bootstrap.is_system_bootstrap_required()


def test_an_inactive_account_still_closes_setup(empty, make_user):
    make_user(Role.STUDENT, is_active=False)
    assert not bootstrap.is_system_bootstrap_required()
    assert Client().get(URL).status_code == 404


def test_nothing_from_the_client_can_reopen_it(student):
    c = Client()
    c.cookies["bootstrap"] = "1"
    for path in (URL, URL + "?bootstrap=1&force=true"):
        assert c.get(path).status_code == 404
    assert c.post(URL, {**form_data(), "bootstrap": "1"}).status_code == 404
    assert User.objects.count() == 1


# ── The page and the account it creates ─────────────────────────────────────


def test_empty_installation_shows_the_form_and_no_privilege_fields(client, empty):
    resp = client.get(URL)
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Set up the first administrator" in html
    for name in ("full_name", "email", "username", "password1", "password2"):
        assert f'name="{name}"' in html
    for name in ("role", "is_superuser", "is_staff", "groups", "user_permissions", "setup_code"):
        assert f'name="{name}"' not in html
    assert 'class="input' in html  # design-system inputs
    assert resp["Cache-Control"].startswith("max-age=0")  # never_cache


def test_valid_setup_creates_an_administrator_who_must_sign_in(client, empty):
    resp = client.post(URL, form_data())
    assert resp.status_code == 302
    assert resp.url == "/login/?next=/manage/setup/"
    assert "_auth_user_id" not in client.session  # not signed in: the normal sign-in and MFA follow

    user = User.objects.get()
    assert (user.username, user.email, user.first_name, user.last_name) == (
        "asha.admin",
        "asha.verma@example.test",
        "Asha",
        "Verma",
    )
    assert user.role == Role.ADMIN
    assert user.is_active and not user.is_superuser and not user.is_staff
    assert list(user.groups.values_list("name", flat=True)) == ["role:admin"]
    assert user.has_perm("accounts.manage_users") and user.has_perm("accounts.manage_resources")
    assert not user.mfa_enabled and not user.mfa_secret

    page = client.get(resp.url)
    assert "Administrator account created. Continue to sign in as asha.admin" in page.content.decode()


def test_password_is_hashed(client, empty):
    client.post(URL, form_data())
    user = User.objects.get()
    assert user.password != PASSWORD and PASSWORD not in user.password
    identify_hasher(user.password)  # a real Django hash
    assert user.check_password(PASSWORD)


def test_privileges_from_the_request_are_ignored(client, empty):
    client.post(
        URL,
        form_data(
            role=Role.STUDENT,
            is_superuser="on",
            is_staff="on",
            is_active="",
            groups="1",
            user_permissions="1",
            institution="999",
            mfa_enabled="on",
        ),
    )
    user = User.objects.get()
    assert user.role == Role.ADMIN and user.is_active
    assert not user.is_superuser and not user.is_staff and not user.mfa_enabled
    assert not user.user_permissions.exists()


def test_single_word_names_are_fine(client, empty):
    client.post(URL, form_data(full_name="  Asha  "))
    assert User.objects.get().get_full_name() == "Asha"


# ── Validation ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "over, field, message",
    [
        ({"password1": "short1!", "password2": "short1!"}, "password1", "too short"),
        ({"password1": "password123", "password2": "password123"}, "password1", "too common"),
        ({"password1": "asha.admin.1", "password2": "asha.admin.1"}, "password1", "too similar"),
        ({"password1": "1234567890123", "password2": "1234567890123"}, "password1", "entirely numeric"),
        ({"password2": "x-test-password-789"}, "password2", "don't match"),
        ({"email": "not-an-email"}, "email", "valid email"),
        ({"username": "asha admin!"}, "username", "Enter a valid username"),
        ({"full_name": "   "}, "full_name", "required"),
        ({"username": ""}, "username", "required"),
    ],
)
def test_invalid_input_is_rejected_and_nothing_is_created(client, empty, over, field, message):
    resp = client.post(URL, form_data(**over))
    assert resp.status_code == 200
    form = resp.context["form"]
    assert message in " ".join(form.errors[field])
    assert "No account was created" in resp.content.decode()
    assert not User.objects.exists()
    assert not AuditLog.objects.filter(action="auth.bootstrap_admin").exists()


def test_passwords_are_never_echoed_back(client, empty):
    resp = client.post(URL, form_data(email="not-an-email"))
    assert PASSWORD not in resp.content.decode()


def test_duplicate_username_and_email_are_rejected_case_insensitively(make_user):
    existing = make_user(Role.STUDENT, username="asha.admin", email="asha.verma@example.test")
    form = BootstrapForm(form_data(username="ASHA.Admin", email="ASHA.VERMA@example.test"))
    assert not form.is_valid()
    assert "already signs in as" in form.errors["username"][0]
    assert "already belongs to another account" in form.errors["email"][0]
    assert User.objects.get() == existing


# ── Takeover: once any account exists ──────────────────────────────────────


def test_get_and_post_are_gone_once_an_account_exists(client, empty):
    assert client.post(URL, form_data()).status_code == 302
    assert client.get(URL).status_code == 404
    resp = client.post(URL, form_data(username="mallory", email="mallory@example.test"))
    assert resp.status_code == 404
    assert list(User.objects.values_list("username", flat=True)) == ["asha.admin"]
    assert b"first administrator" not in resp.content


def test_the_service_refuses_when_an_account_exists(make_user):
    make_user(Role.STUDENT)
    with pytest.raises(BootstrapClosed):
        create_first_administrator(
            username="mallory", email="m@example.test", first_name="M", last_name="", password=PASSWORD
        )
    assert not User.objects.filter(username="mallory").exists()


def test_a_signed_in_person_cannot_use_it(client, admin_user):
    client.force_login(admin_user)
    assert client.get(URL).status_code == 404
    assert client.post(URL, form_data()).status_code == 404
    assert User.objects.count() == 1


def test_csrf_is_required(empty):
    c = Client(enforce_csrf_checks=True)
    assert c.get(URL).status_code == 200
    assert c.post(URL, form_data()).status_code == 403
    assert not User.objects.exists()


def test_repeated_posts_are_rate_limited(client, empty):
    for _ in range(5):
        client.post(URL, form_data(password2="nope-nope-nope"))
    resp = client.post(URL, form_data())  # valid, but the sixth attempt this minute
    assert resp.status_code == 200
    assert "Too many attempts" in resp.content.decode()
    assert not User.objects.exists()
    assert PASSWORD not in resp.content.decode()


def test_the_sign_in_rate_limit_is_separate(client, empty, make_user):
    for _ in range(5):
        client.post(URL, form_data(password2="nope-nope-nope"))
    user = make_user(Role.STUDENT)
    resp = client.post(reverse("accounts:login"), {"username": user.username, "password": "x-test-password-123"})
    assert resp.status_code == 302


# ── Optional setup code ─────────────────────────────────────────────────────


def test_setup_code_when_configured(client, empty, settings):
    settings.BOOTSTRAP_SETUP_CODE = "orange-lantern-42"
    assert 'name="setup_code"' in client.get(URL).content.decode()

    resp = client.post(URL, form_data(setup_code="wrong-code"))
    assert resp.status_code == 200 and resp.context["form"].errors["setup_code"] == ["That setup code isn't right."]
    resp = client.post(URL, form_data())
    assert "setup_code" in resp.context["form"].errors
    assert not User.objects.exists()

    assert client.post(URL, form_data(setup_code="orange-lantern-42")).status_code == 302
    assert User.objects.get().role == Role.ADMIN
    assert "orange-lantern-42" not in json.dumps(list(AuditLog.objects.values("before", "after")))


# ── Audit ───────────────────────────────────────────────────────────────────


def test_creation_is_audited_without_secrets(client, empty):
    client.post(URL, form_data(), REMOTE_ADDR="203.0.113.9")
    user = User.objects.get()
    entry = AuditLog.objects.get(action="auth.bootstrap_admin")
    assert entry.actor is None and entry.actor_label == "system"
    assert (entry.target_type, entry.target_id) == ("accounts.user", str(user.pk))
    assert entry.after == {
        "username": "asha.admin",
        "email": "asha.verma@example.test",
        "role": "admin",
        "is_superuser": False,
        "is_staff": False,
        "via": "first-run setup",
    }
    assert entry.ip == "203.0.113.9"
    everything = json.dumps(list(AuditLog.objects.values()), default=str)
    assert PASSWORD not in everything and user.password not in everything
    assert "password" not in everything.lower()


def test_password_never_reaches_the_logs(client, empty, caplog):
    caplog.set_level("DEBUG")
    client.post(URL, form_data())
    assert PASSWORD not in caplog.text
    assert User.objects.get().password not in caplog.text


# ── Sign-in page and MFA ────────────────────────────────────────────────────


def test_sign_in_page_offers_setup_only_while_there_are_no_accounts(client, empty):
    html = client.get(reverse("accounts:login")).content.decode()
    assert "This installation has no accounts yet" in html and f'href="{URL}"' in html
    assert "Sign up" not in html and "sign up" not in html

    client.post(URL, form_data())
    html = client.get(reverse("accounts:login")).content.decode()
    assert "no accounts yet" not in html and URL not in html


def test_first_sign_in_requires_mfa_enrolment_then_lands_in_setup(client, empty):
    client.post(URL, form_data())
    resp = client.post(
        reverse("accounts:login"), {"username": "asha.admin", "password": PASSWORD, "next": "/manage/setup/"}
    )
    assert resp.url == reverse("accounts:mfa")
    assert "_auth_user_id" not in client.session
    # Privileged pages refuse a half-signed-in session.
    assert client.get("/manage/setup/").status_code == 302

    page = client.get(reverse("accounts:mfa"))
    assert page.context["enrolling"] is True
    secret = page.context["secret"]
    resp = client.post(reverse("accounts:mfa"), {"code": pyotp.TOTP(secret).now()})
    assert resp.url == "/manage/setup/"
    user = User.objects.get()
    assert user.mfa_enabled and secret not in user.mfa_secret  # stored encrypted
    setup = client.get("/manage/setup/")
    assert setup.status_code == 200 and "Getting started" in setup.content.decode()


def test_mfa_is_still_required_for_the_role(empty):
    from apps.accounts import mfa

    create_first_administrator(username="a", email="a@example.test", first_name="A", last_name="", password=PASSWORD)
    assert mfa.required_for(User.objects.get())


# ── Operator fallback ───────────────────────────────────────────────────────


def test_createsuperuser_still_works_and_closes_setup(empty, monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", PASSWORD)
    call_command("createsuperuser", interactive=False, username="ops", email="ops@example.test", verbosity=0)
    user = User.objects.get()
    assert user.is_superuser and user.check_password(PASSWORD)
    assert Client().get(URL).status_code == 404


# ── Concurrency ─────────────────────────────────────────────────────────────


def _race(n, fire):
    barrier = threading.Barrier(n)
    results, errors = [None] * n, []

    def worker(i):
        try:
            barrier.wait(timeout=30)
            results[i] = fire(i)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(repr(exc))
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert errors == []
    return results


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_setups_create_exactly_one_administrator():
    assert not User.objects.exists()
    clients = [Client(), Client()]
    for c in clients:
        assert c.get(URL).status_code == 200

    def fire(i):
        return clients[i].post(URL, form_data(username=f"admin{i}", email=f"admin{i}@example.test")).status_code

    codes = _race(2, fire)
    assert sorted(codes) == [302, 404]
    assert User.objects.count() == 1
    assert User.objects.get().role == Role.ADMIN
    assert AuditLog.objects.filter(action="auth.bootstrap_admin").count() == 1


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_a_burst_of_setups_creates_exactly_one_administrator():
    def fire(i):
        try:
            create_first_administrator(
                username=f"admin{i}", email=f"a{i}@example.test", first_name="A", last_name=str(i), password=PASSWORD
            )
            return "created"
        except BootstrapClosed:
            return "closed"

    results = _race(8, fire)
    assert results.count("created") == 1 and results.count("closed") == 7
    assert User.objects.count() == 1


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_the_table_lock_turns_away_an_attempt_that_passed_the_first_check():
    """
    Both attempts see an empty table before either writes. The second must wait for the first's
    lock, see its committed account, and be refused, not insert a second administrator.
    """
    holding, release = threading.Event(), threading.Event()
    outcome = {}

    def first():
        try:
            with transaction.atomic():
                bootstrap._lock_user_table()
                holding.set()
                release.wait(timeout=30)
                User.objects.create_user(username="first", password=PASSWORD, role=Role.ADMIN)
        finally:
            connection.close()

    def second():
        holding.wait(timeout=30)
        try:
            assert bootstrap.is_system_bootstrap_required()  # nothing committed yet
            create_first_administrator(
                username="second", email="s@example.test", first_name="S", last_name="", password=PASSWORD
            )
            outcome["second"] = "created"
        except BootstrapClosed:
            outcome["second"] = "closed"
        finally:
            connection.close()

    a, b = threading.Thread(target=first), threading.Thread(target=second)
    a.start()
    b.start()
    holding.wait(timeout=30)
    b.join(timeout=2)
    assert b.is_alive()  # blocked on the lock, not racing past it
    release.set()
    a.join(timeout=30)
    b.join(timeout=30)
    assert outcome == {"second": "closed"}
    assert list(User.objects.values_list("username", flat=True)) == ["first"]
