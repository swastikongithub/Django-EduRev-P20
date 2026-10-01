"""
/health/ (liveness) and /ready/ (readiness) probes.

The Client tests run against a tiny urlconf defined in this module (the same two
lines the project urlconf uses), so they pass whether or not config/urls.py has been
wired yet. ``test_project_urlconf_exposes_probes`` checks the real wiring and skips
until the routes exist.
"""

import pytest
from django.db.utils import OperationalError
from django.test import RequestFactory, override_settings
from django.urls import Resolver404, path, resolve

from apps.core import health

urlpatterns = [
    path("health/", health.liveness, name="health"),
    path("ready/", health.readiness, name="ready"),
]

probe_urls = override_settings(ROOT_URLCONF=__name__)


def _broken_cursor(*args, **kwargs):
    raise OperationalError("connection refused")


@probe_urls
@pytest.mark.django_db
def test_health_is_200(client):
    resp = client.get("/health/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert any(d in resp["Cache-Control"] for d in ("no-store", "no-cache", "max-age=0"))


@probe_urls
@pytest.mark.django_db
def test_health_rejects_writes(client):
    assert client.post("/health/").status_code == 405


@probe_urls
@pytest.mark.django_db
@override_settings(REDIS_URL="")
def test_ready_ok_when_database_up(client):
    resp = client.get("/ready/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert "redis" not in body["checks"]  # only checked when REDIS_URL is configured


@probe_urls
@pytest.mark.django_db
def test_ready_503_when_database_down(client, monkeypatch):
    monkeypatch.setattr(
        health, "check_database", lambda alias="default": {"status": "error", "error": "OperationalError", "ms": 0}
    )
    resp = client.get("/ready/")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"] == {"status": "error", "error": "OperationalError", "ms": 0}


@probe_urls
@pytest.mark.django_db
@override_settings(REDIS_URL="redis://127.0.0.1:1/0")  # nothing listens on port 1
def test_ready_503_when_redis_unreachable(client):
    resp = client.get("/ready/")
    assert resp.status_code == 503
    checks = resp.json()["checks"]
    assert checks["database"]["status"] == "ok"
    assert checks["redis"]["status"] == "error"


def test_check_database_reports_failure_without_leaking_details(monkeypatch):
    from django.db import connections

    monkeypatch.setattr(connections["default"], "cursor", _broken_cursor)
    result = health.check_database()
    assert result["status"] == "error"
    assert result["error"] == "OperationalError"
    assert "refused" not in str(result)


def test_middleware_liveness_needs_no_database_or_allowed_host(monkeypatch):
    """With HealthCheckMiddleware first in MIDDLEWARE, /health/ answers even with the DB down and an unknown Host."""
    from django.db import connections

    monkeypatch.setattr(connections["default"], "cursor", _broken_cursor)
    mw = health.HealthCheckMiddleware(lambda request: pytest.fail("probe must not reach the rest of the stack"))
    request = RequestFactory().get("/health/", HTTP_HOST="10.1.2.3:8000")
    resp = mw(request)
    assert resp.status_code == 200
    assert resp["Cache-Control"] == "no-store"


def test_middleware_readiness_503_when_database_down(monkeypatch):
    from django.db import connections

    monkeypatch.setattr(connections["default"], "cursor", _broken_cursor)
    mw = health.HealthCheckMiddleware(lambda request: pytest.fail("probe must not reach the rest of the stack"))
    with override_settings(REDIS_URL=""):
        resp = mw(RequestFactory().get("/ready/"))
    assert resp.status_code == 503


def test_middleware_passes_other_requests_through():
    sentinel = object()
    mw = health.HealthCheckMiddleware(lambda request: sentinel)
    assert mw(RequestFactory().get("/")) is sentinel
    assert mw(RequestFactory().post("/health/")) is sentinel  # only GET/HEAD are short-circuited


def test_project_urlconf_exposes_probes():
    try:
        live, ready = resolve("/health/"), resolve("/ready/")
    except Resolver404:
        pytest.skip("config/urls.py does not route /health/ and /ready/ yet")
    assert live.func is health.liveness
    assert ready.func is health.readiness
