"""
Production configuration (Railway): object storage, email, client addresses behind the edge,
the single Celery Beat, analytics catch-up, health probes on the platform's host name, and the
deployment checks that refuse a configuration which would lose data or mail.
"""

from datetime import timedelta

import psycopg
import pytest
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.analytics.models import UtilisationSnapshot
from apps.analytics.tasks import CATCH_UP_MAX_DAYS, days_to_build
from apps.core.checks import production_configuration
from apps.core.http import client_ip
from apps.core.management.commands import run_beat
from apps.core.throttling import ClientAnonRateThrottle

rf = RequestFactory()


# ── Client address behind Railway's edge ────────────────────────────────────


@override_settings(TRUSTED_CLIENT_IP_HEADER="X-Real-IP", TRUSTED_PROXY_HOPS=0)
def test_trusted_header_wins_and_spoofed_forwarded_for_is_ignored():
    req = rf.get("/", HTTP_X_REAL_IP="203.0.113.9", HTTP_X_FORWARDED_FOR="6.6.6.6", REMOTE_ADDR="10.0.0.2")
    assert client_ip(req) == "203.0.113.9"


@override_settings(TRUSTED_CLIENT_IP_HEADER="X-Real-IP", TRUSTED_PROXY_HOPS=0)
def test_malformed_trusted_header_falls_back_to_the_peer():
    req = rf.get("/", HTTP_X_REAL_IP="not-an-ip, 1.2.3.4", REMOTE_ADDR="10.0.0.2")
    assert client_ip(req) == "10.0.0.2"


@override_settings(TRUSTED_CLIENT_IP_HEADER="", TRUSTED_PROXY_HOPS=0)
def test_without_configuration_client_headers_are_never_trusted():
    req = rf.get("/", HTTP_X_REAL_IP="203.0.113.9", HTTP_X_FORWARDED_FOR="203.0.113.9", REMOTE_ADDR="10.0.0.2")
    assert client_ip(req) == "10.0.0.2"


@override_settings(TRUSTED_CLIENT_IP_HEADER="X-Real-IP")
def test_api_throttle_keys_on_the_same_client_address():
    throttle = ClientAnonRateThrottle()
    a = rf.get("/", HTTP_X_REAL_IP="203.0.113.1", REMOTE_ADDR="10.0.0.2")
    b = rf.get("/", HTTP_X_REAL_IP="203.0.113.2", REMOTE_ADDR="10.0.0.2")
    # Two people behind the same edge address must not share one anonymous rate-limit bucket.
    assert throttle.get_ident(a) == "203.0.113.1"
    assert throttle.get_ident(b) == "203.0.113.2"


# ── Health probes from Railway's health checker ─────────────────────────────


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=["reserve.example.edu"], DEBUG=False)
def test_probes_answer_railways_healthcheck_host(client):
    # Railway probes with Host: healthcheck.railway.app, which is not (and need not be) allowed.
    assert client.get("/health/", HTTP_HOST="healthcheck.railway.app").status_code == 200
    assert client.get("/ready/", HTTP_HOST="healthcheck.railway.app").status_code == 200
    assert client.get("/login/", HTTP_HOST="healthcheck.railway.app").status_code == 400


# ── Deployment checks ───────────────────────────────────────────────────────


def _ids(**overrides):
    with override_settings(**overrides):
        return {m.id for m in production_configuration()}


PROD = {"DEBUG": False, "DEMO_MODE": False, "REDIS_URL": "redis://r:6379/0", "SITE_URL": "https://reserve.example.edu"}
S3 = {"USE_S3": True, "STORAGES": {"default": {"OPTIONS": {"bucket_name": "media"}}, "staticfiles": {}}}


def test_ephemeral_media_and_console_email_are_deployment_errors():
    ids = _ids(**PROD, USE_S3=False, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    assert {"lpu.E001", "lpu.E002"} <= ids


def test_a_complete_production_configuration_passes():
    ok = _ids(**PROD, **S3, EMAIL_BACKEND="anymail.backends.resend.EmailBackend", ANYMAIL={"RESEND_API_KEY": "re_x"})
    assert ok == set()


def test_email_api_without_its_key_is_an_error():
    assert "lpu.E004" in _ids(**PROD, **S3, EMAIL_BACKEND="anymail.backends.resend.EmailBackend", ANYMAIL={})


def test_development_and_demo_stacks_are_exempt():
    assert _ids(DEBUG=True, DEMO_MODE=False, USE_S3=False) == set()
    assert _ids(DEBUG=False, DEMO_MODE=True, USE_S3=False) == set()


@pytest.mark.django_db
def test_check_deploy_command_fails_on_ephemeral_media():
    with override_settings(**PROD, USE_S3=False), pytest.raises(SystemCheckError):
        call_command("check", "--deploy", "--fail-level", "ERROR")


# ── Exactly one Celery Beat ─────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_only_one_scheduler_can_hold_the_lock():
    info = run_beat._conninfo()
    leader = psycopg.connect(info, autocommit=True)
    follower = psycopg.connect(info, autocommit=True)
    try:
        assert run_beat.try_lead(leader) is True
        assert run_beat.try_lead(follower) is False  # a second Beat waits
        leader.close()  # leader dies: PostgreSQL releases the lock with the session
        assert run_beat.try_lead(follower) is True  # and the follower takes over
    finally:
        follower.close()


# ── Nightly analytics never leaves a hole ───────────────────────────────────


@pytest.mark.django_db
def test_nightly_job_catches_up_missed_days(room):
    today = timezone.localdate()
    assert days_to_build(today) == (today - timedelta(days=1), today - timedelta(days=1))
    UtilisationSnapshot.objects.create(resource=room, date=today - timedelta(days=5))
    assert days_to_build(today) == (today - timedelta(days=4), today - timedelta(days=1))
    UtilisationSnapshot.objects.create(resource=room, date=today - timedelta(days=400))
    UtilisationSnapshot.objects.filter(date=today - timedelta(days=5)).delete()
    start, end = days_to_build(today)
    assert (end - start).days + 1 == CATCH_UP_MAX_DAYS
