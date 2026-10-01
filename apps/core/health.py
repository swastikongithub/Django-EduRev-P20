"""
Liveness and readiness probes (CES: "/health and /ready").

* ``/health/`` — liveness. Answers 200 as long as the Python process can serve a
  request. It never touches PostgreSQL or Redis, so a database outage does not make
  the orchestrator restart healthy web containers.
* ``/ready/``  — readiness. Runs ``SELECT 1`` on the default database and, when
  ``REDIS_URL`` is configured, a Redis ``PING``. Returns JSON with one entry per check
  and HTTP 503 if any check fails, so a load balancer stops routing traffic here.

Wire-up (config/urls.py, owned by the lead)::

    path("health/", health.liveness, name="health"),
    path("ready/", health.readiness, name="ready"),

Optional hardening: add ``"apps.core.health.HealthCheckMiddleware"`` as the *first*
entry in ``MIDDLEWARE``. It answers both probes before any other middleware runs, so
they work even when the probe's Host header is not in ALLOWED_HOSTS (container/pod
IPs) and ``/health/`` stays 200 while the database is down (InstitutionMiddleware
queries the database on anonymous requests).
"""

from __future__ import annotations

import time

from django.conf import settings
from django.db import connections
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

HEALTH_PATH = "/health/"
READY_PATH = "/ready/"
CHECK_TIMEOUT_SECONDS = 2


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def check_database(alias: str = "default") -> dict:
    started = time.perf_counter()
    try:
        with connections[alias].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # any failure means "not ready"; details stay in logs, not the response
        return {"status": "error", "error": type(exc).__name__, "ms": _elapsed_ms(started)}
    return {"status": "ok", "ms": _elapsed_ms(started)}


def check_redis(url: str) -> dict:
    started = time.perf_counter()
    try:
        import redis
        from redis.backoff import NoBackoff
        from redis.retry import Retry

        client = redis.Redis.from_url(
            url,
            socket_connect_timeout=CHECK_TIMEOUT_SECONDS,
            socket_timeout=CHECK_TIMEOUT_SECONDS,
            retry=Retry(NoBackoff(), 0),  # a probe answers fast; redis-py retries by default
        )
        try:
            client.ping()
        finally:
            client.close()
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__, "ms": _elapsed_ms(started)}
    return {"status": "ok", "ms": _elapsed_ms(started)}


def run_checks() -> dict[str, dict]:
    checks = {"database": check_database()}
    redis_url = getattr(settings, "REDIS_URL", "")
    if redis_url:
        checks["redis"] = check_redis(redis_url)
    return checks


def _liveness_response() -> JsonResponse:
    return JsonResponse({"status": "ok"})


def _readiness_response() -> JsonResponse:
    checks = run_checks()
    ok = all(c["status"] == "ok" for c in checks.values())
    return JsonResponse({"status": "ok" if ok else "unavailable", "checks": checks}, status=200 if ok else 503)


def _no_store(response: JsonResponse) -> JsonResponse:
    response["Cache-Control"] = "no-store"
    return response


@never_cache
@require_safe
def liveness(request: HttpRequest) -> JsonResponse:
    return _liveness_response()


@never_cache
@require_safe
def readiness(request: HttpRequest) -> JsonResponse:
    return _readiness_response()


class HealthCheckMiddleware:
    """Short-circuit GET/HEAD probes on /health/ and /ready/ before host validation and DB-backed middleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        if request.method in ("GET", "HEAD"):
            if request.path == HEALTH_PATH:
                return _no_store(_liveness_response())
            if request.path == READY_PATH:
                return _no_store(_readiness_response())
        return self.get_response(request)
