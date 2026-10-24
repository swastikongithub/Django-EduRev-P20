"""
Production configuration as Railway runs it (docs/deployment-railway.md).

Settings are evaluated the way a container evaluates them at start-up: config/settings.py is run
from scratch with a given environment, never with the test settings already loaded.
"""

import runpy
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory

BASE_DIR = Path(__file__).resolve().parent.parent

REAL_KEY = "k" * 10 + uuid.uuid4().hex + uuid.uuid4().hex
BUCKET = "media-abc123"
ENDPOINT = "https://t3.storageapi.dev"

# What .railway/railway.ts gives the web, worker and beat services (secrets replaced).
RAILWAY_ENV = {
    "DEBUG": "0",
    "DEMO_MODE": "0",
    "DJANGO_SECRET_KEY": REAL_KEY,
    "ALLOWED_HOSTS": "reserve.up.railway.app",
    "CSRF_TRUSTED_ORIGINS": "https://reserve.up.railway.app",
    "SITE_URL": "https://reserve.up.railway.app",
    "SECURE_SSL_REDIRECT": "1",
    "CLIENT_IP_HEADER": "X-Real-IP",
    "DATABASE_URL": "postgres://u:p@postgres.railway.internal:5432/railway",
    "REDIS_URL": "redis://default:p@redis.railway.internal:6379",
    "CELERY_BROKER_URL": "redis://default:p@redis.railway.internal:6379/1",
    "CELERY_TASK_ALWAYS_EAGER": "0",
    "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "EMAIL_HOST": "smtp.example.edu",
    "EMAIL_PORT": "587",
    "EMAIL_HOST_USER": "reserve",
    "EMAIL_HOST_PASSWORD": "not-a-real-password",
    "USE_S3": "1",
    "S3_BUCKET": BUCKET,
    "S3_ENDPOINT_URL": ENDPOINT,
    "S3_REGION": "auto",
    "AWS_ACCESS_KEY_ID": "test-access-key",
    "AWS_SECRET_ACCESS_KEY": "test-secret-key",
}

_CLEARED = set(RAILWAY_ENV) | {"EMAIL_USE_TLS", "EMAIL_USE_SSL", "S3_ADDRESSING_STYLE", "TRUSTED_PROXY_HOPS"}


def load_settings(monkeypatch, **overrides):
    import environ

    monkeypatch.setattr(environ.Env, "read_env", lambda *a, **k: None)
    for key in _CLEARED:
        monkeypatch.delenv(key, raising=False)
    for key, value in {**RAILWAY_ENV, **overrides}.items():
        if value is not None:
            monkeypatch.setenv(key, value)
    return runpy.run_path(str(BASE_DIR / "config" / "settings.py"))


# ── The Railway configuration as a whole ─────────────────────────────────────


def test_railway_environment_gives_hardened_production_settings(monkeypatch):
    s = load_settings(monkeypatch)
    assert s["DEBUG"] is False and s["DEMO_MODE"] is False
    assert s["SESSION_COOKIE_SECURE"] and s["CSRF_COOKIE_SECURE"]
    assert s["SESSION_COOKIE_HTTPONLY"] and s["CSRF_COOKIE_HTTPONLY"]
    assert s["SECURE_PROXY_SSL_HEADER"] == ("HTTP_X_FORWARDED_PROTO", "https")
    assert s["SECURE_SSL_REDIRECT"] is True
    assert s["SECURE_HSTS_SECONDS"] >= 60 * 60 * 24 * 30
    assert s["ALLOWED_HOSTS"] == ["reserve.up.railway.app"]
    assert s["CSRF_TRUSTED_ORIGINS"] == ["https://reserve.up.railway.app"]
    assert s["CACHES"]["default"]["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
    assert s["CELERY_BROKER_URL"].endswith("/1")  # broker apart from the cache
    assert s["CELERY_TASK_ALWAYS_EAGER"] is False
    assert s["STORAGES"]["staticfiles"]["BACKEND"] == "whitenoise.storage.CompressedManifestStaticFilesStorage"


def test_debug_on_railway_is_refused_without_a_real_key(monkeypatch):
    with pytest.raises(ImproperlyConfigured):
        load_settings(monkeypatch, DJANGO_SECRET_KEY=None)


# ── Email ────────────────────────────────────────────────────────────────────


def test_smtp_settings_come_from_the_environment(monkeypatch):
    s = load_settings(monkeypatch)
    assert s["EMAIL_BACKEND"] == "django.core.mail.backends.smtp.EmailBackend"
    assert (s["EMAIL_HOST"], s["EMAIL_PORT"], s["EMAIL_HOST_USER"]) == ("smtp.example.edu", 587, "reserve")
    assert s["EMAIL_HOST_PASSWORD"] == "not-a-real-password"
    assert s["EMAIL_USE_TLS"] is True and s["EMAIL_USE_SSL"] is False
    assert 0 < s["EMAIL_TIMEOUT"] <= 30


def test_smtp_over_ssl_on_465(monkeypatch):
    s = load_settings(monkeypatch, EMAIL_PORT="465", EMAIL_USE_TLS="0", EMAIL_USE_SSL="1")
    assert (s["EMAIL_PORT"], s["EMAIL_USE_TLS"], s["EMAIL_USE_SSL"]) == (465, False, True)


def test_smtp_tls_and_ssl_together_is_refused(monkeypatch):
    with pytest.raises(ImproperlyConfigured):
        load_settings(monkeypatch, EMAIL_USE_TLS="1", EMAIL_USE_SSL="1")


# ── Uploaded media in a private bucket ───────────────────────────────────────


def test_media_goes_to_the_bucket_with_short_lived_presigned_urls(monkeypatch):
    s = load_settings(monkeypatch)
    storage = s["STORAGES"]["default"]
    assert storage["BACKEND"] == "storages.backends.s3.S3Storage"
    opts = storage["OPTIONS"]
    assert opts["bucket_name"] == BUCKET and opts["endpoint_url"] == ENDPOINT
    assert opts["querystring_auth"] is True and opts["querystring_expire"] == 900
    assert opts["default_acl"] is None and opts["file_overwrite"] is False
    assert s["MEDIA_ORIGIN"] == f"https://{BUCKET}.t3.storageapi.dev"


def test_path_style_buckets_use_the_endpoint_origin(monkeypatch):
    s = load_settings(monkeypatch, S3_ADDRESSING_STYLE="path")
    assert s["MEDIA_ORIGIN"] == "https://t3.storageapi.dev"


@pytest.mark.parametrize(
    "overrides",
    [
        {"S3_ENDPOINT_URL": "http://t3.storageapi.dev"},  # never fetch photos in the clear
        {"S3_ENDPOINT_URL": "not a url"},
        {"S3_ADDRESSING_STYLE": "sideways"},
    ],
)
def test_bucket_misconfiguration_stops_start_up(monkeypatch, overrides):
    with pytest.raises(ImproperlyConfigured):
        load_settings(monkeypatch, **overrides)


def test_without_s3_media_stays_on_local_disk_and_csp_is_unchanged(monkeypatch):
    s = load_settings(monkeypatch, USE_S3=None)
    assert s["STORAGES"]["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"
    assert s["MEDIA_ORIGIN"] == ""


@pytest.mark.parametrize("style", ["virtual", "path"])
def test_presigned_urls_point_at_the_origin_the_csp_allows(monkeypatch, style):
    """The URL the storage really generates (offline: signing needs no network) is CSP-allowed."""
    from storages.backends.s3 import S3Storage

    s = load_settings(monkeypatch, S3_ADDRESSING_STYLE=style)
    url = S3Storage(**s["STORAGES"]["default"]["OPTIONS"]).url("resources/photo.webp")
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}" == s["MEDIA_ORIGIN"]
    query = parse_qs(parts.query)
    assert query["X-Amz-Expires"] == ["900"] and "X-Amz-Signature" in query


def test_csp_allows_bucket_images_and_nothing_else(settings):
    from apps.core.middleware import SecurityHeadersMiddleware

    origin = f"https://{BUCKET}.t3.storageapi.dev"
    csp = dict(
        part.strip().split(" ", 1) for part in SecurityHeadersMiddleware.build_csp(origin).split(";") if part.strip()
    )
    assert csp["img-src"] == f"'self' data: blob: {origin}"
    for directive in ("default-src", "script-src", "connect-src", "font-src", "media-src", "form-action"):
        assert origin not in csp[directive]
    assert csp["script-src"] == "'self'"

    settings.MEDIA_ORIGIN = origin
    middleware = SecurityHeadersMiddleware(lambda request: __import__("django.http").http.HttpResponse())
    response = middleware(RequestFactory().get("/login/"))
    assert f"img-src 'self' data: blob: {origin};" in response["Content-Security-Policy"]


# ── Client address behind Railway's edge ─────────────────────────────────────


def _request(**meta):
    return RequestFactory().get("/", REMOTE_ADDR="10.0.0.9", **meta)


@pytest.mark.parametrize(
    "meta, expected",
    [
        ({"HTTP_X_REAL_IP": "198.51.100.7"}, "198.51.100.7"),
        ({"HTTP_X_REAL_IP": "2001:db8::7"}, "2001:db8::7"),
        # A client-sent X-Forwarded-For is irrelevant once the edge's own header is trusted.
        ({"HTTP_X_REAL_IP": "198.51.100.7", "HTTP_X_FORWARDED_FOR": "6.6.6.6"}, "198.51.100.7"),
        ({"HTTP_X_REAL_IP": "not-an-ip"}, "10.0.0.9"),
        ({}, "10.0.0.9"),
    ],
)
def test_client_ip_header_takes_precedence(settings, meta, expected):
    from apps.core.http import client_ip

    settings.CLIENT_IP_HEADER = "X-Real-IP"
    settings.TRUSTED_PROXY_HOPS = 1
    assert client_ip(_request(**meta)) == expected


def test_client_ip_header_is_off_by_default(settings):
    from apps.core.http import client_ip

    assert settings.CLIENT_IP_HEADER == ""
    assert client_ip(_request(HTTP_X_REAL_IP="198.51.100.7")) == "10.0.0.9"


def test_anonymous_api_throttle_keys_on_the_same_client_address(settings):
    from apps.core.api import AnonRateThrottle

    settings.CLIENT_IP_HEADER = "X-Real-IP"
    first = AnonRateThrottle().get_ident(_request(HTTP_X_REAL_IP="198.51.100.7"))
    second = AnonRateThrottle().get_ident(_request(HTTP_X_REAL_IP="198.51.100.8"))
    assert (first, second) == ("198.51.100.7", "198.51.100.8")
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] == [
        "apps.core.api.UserRateThrottle",
        "apps.core.api.AnonRateThrottle",
    ]


def test_sign_in_rate_limit_counts_each_client_behind_the_edge_separately(client, settings, student):
    """Behind Railway every request comes from the edge; without the header all of LPU is one client."""
    from django.urls import reverse

    settings.CLIENT_IP_HEADER = "X-Real-IP"
    for _ in range(20):
        client.post(reverse("accounts:login"), {"username": "nobody", "password": "x"}, HTTP_X_REAL_IP="203.0.113.1")
    blocked = client.post(
        reverse("accounts:login"), {"username": "nobody", "password": "x"}, HTTP_X_REAL_IP="203.0.113.1"
    )
    other = client.post(
        reverse("accounts:login"), {"username": "nobody", "password": "x"}, HTTP_X_REAL_IP="203.0.113.2"
    )
    assert b"Too many sign-in attempts" in blocked.content
    assert b"Too many sign-in attempts" not in other.content


# ── Railway's deploy healthcheck ─────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/health/", "/ready/"])
def test_probes_answer_railways_healthcheck_host_over_plain_http(client, settings, path):
    """Railway probes over plain HTTP with Host healthcheck.railway.app, which is not an allowed host."""
    settings.ALLOWED_HOSTS = ["reserve.up.railway.app"]
    settings.SECURE_SSL_REDIRECT = True
    response = client.get(path, HTTP_HOST="healthcheck.railway.app")
    assert response.status_code == 200
