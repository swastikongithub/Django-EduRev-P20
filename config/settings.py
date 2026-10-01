"""
LPU Reserve — Django settings.

All configuration comes from environment variables (see docs/environment.md).
Nothing secret lives in this file.
"""

import os
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    CELERY_TASK_ALWAYS_EAGER=(bool, False),
    SECURE_SSL_REDIRECT=(bool, False),
    DEMO_MODE=(bool, False),
    LOG_JSON=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)
# An empty variable means "not set": Railway resolves a reference to a shared variable that was
# never defined (an optional email key, SENTRY_DSN, ...) to "", which must fall back to the
# default rather than become an empty backend name or an empty host.
for _name in [k for k, v in os.environ.items() if v == ""]:
    del os.environ[_name]

DEBUG = env("DEBUG")
# The dev fallback exists only so `DEBUG=1` works out of the box. With DEBUG off the key signs
# sessions, CSRF and password-reset tokens and derives the MFA encryption key, so a missing,
# placeholder or short key is a start-up error, never a silent fallback (SEC-05).
# The public `dev-only-*` keys (this file, docker-compose.yml) are tolerated with DEBUG off only on
# a DEMO_MODE stack, which offers one-click sign-in and is never a real deployment.
DEMO_MODE = env("DEMO_MODE")
_DEV_SECRET_KEY = "dev-only-insecure-key-change-me"
_PLACEHOLDER_SECRET_KEYS = {_DEV_SECRET_KEY, "replace-me-with-a-long-random-string", "changeme", "secret"}
SECRET_KEY = env("DJANGO_SECRET_KEY", default=_DEV_SECRET_KEY if DEBUG else "")
# Previous keys, newest first, while rotating (Django's SECRET_KEY_FALLBACKS). Sessions and tokens
# signed with them stay valid, and TOTP secrets encrypted under them stay readable; each is
# re-encrypted with the current key at its next sign-in, or all at once by
# `manage.py mfa_keys --rotate`. Remove a fallback once `manage.py mfa_keys` reports none left on it.
SECRET_KEY_FALLBACKS = env.list("DJANGO_SECRET_KEY_FALLBACKS", default=[])


def _weak_secret_key(key: str) -> bool:
    return (
        key in _PLACEHOLDER_SECRET_KEYS
        or len(key) < 32
        or key.startswith("django-insecure-")
        or (key.startswith("dev-only-") and not DEMO_MODE)
    )


if not DEBUG and (_weak_secret_key(SECRET_KEY) or any(_weak_secret_key(k) for k in SECRET_KEY_FALLBACKS)):
    from django.core.exceptions import ImproperlyConfigured

    # A weak fallback is as dangerous as a weak key: signatures made with it are still accepted.
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY (and every DJANGO_SECRET_KEY_FALLBACKS entry) must be a private random value of at "
        "least 32 characters when DEBUG is off. "
        'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(50))"'
    )
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.contrib.humanize",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    # Domain modules — one Django app per P20 functional module.
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.notifications",
    "apps.catalogue",  # M1
    "apps.rules",  # M2
    "apps.bookings",  # M3
    "apps.timetable",  # M4
    "apps.approvals",  # M5
    "apps.checkins",  # M6
    "apps.maintenance",  # M7
    "apps.inventory",  # M8
    "apps.analytics",  # M9
]

MIDDLEWARE = [
    "apps.core.health.HealthCheckMiddleware",  # answers probes before host checks and DB access
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.MFASessionMiddleware",  # MFA-verified sessions only for those who need MFA
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.InstitutionMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.shell",
                "apps.core.context_processors.brand",
            ],
            "builtins": ["apps.core.templatetags.ui", "django.templatetags.i18n"],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": env.db("DATABASE_URL", default="postgres://edurev@localhost:5433/edurev")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"]["TEST"] = {"NAME": env("TEST_DATABASE_NAME", default="test_edurev")}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
# English at launch; Hindi and Punjabi externalised (CES §1.3). Names are shown in their own script.
LANGUAGES = [("en", "English"), ("hi", "हिन्दी"), ("pa", "ਪੰਜਾਬੀ")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# Static files are only ever used by this site's own pages; no "Access-Control-Allow-Origin: *".
WHITENOISE_ALLOW_ALL_ORIGINS = False
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": env(
            "STATICFILES_BACKEND",
            default="whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage",
        )
    },
}
# Uploaded media (resource photos). Development: local disk outside the static root, served by
# runserver only when DEBUG is on. Production: S3-compatible object storage (USE_S3=1). Container
# filesystems are ephemeral on every platform we target, so a production deployment without
# USE_S3 fails `check --deploy` (lpu.E001). The bucket stays private: every photo URL is a
# pre-signed GET that expires (CES §1.4 "served only via pre-signed URL"). On Railway, wire the
# bucket's BUCKET, ACCESS_KEY_ID, SECRET_ACCESS_KEY, ENDPOINT and REGION into the S3_* variables
# below (docs/deployment-railway.md).
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / ".media")))
USE_S3 = env.bool("USE_S3", default=False)
if USE_S3:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("S3_BUCKET"),
            "endpoint_url": env("S3_ENDPOINT_URL", default=None),
            "access_key": env("S3_ACCESS_KEY_ID", default=None),
            "secret_key": env("S3_SECRET_ACCESS_KEY", default=None),
            "region_name": env("S3_REGION", default=None),
            # Railway buckets use virtual-hosted-style URLs; some older buckets and MinIO need "path".
            "addressing_style": env("S3_ADDRESSING_STYLE", default="virtual"),
            "signature_version": "s3v4",
            "location": env("S3_MEDIA_PREFIX", default="media"),
            "default_acl": None,  # the bucket's own (private) policy; never public-read
            "querystring_auth": True,
            "querystring_expire": env.int("S3_URL_EXPIRY_SECONDS", default=900),
            "file_overwrite": False,
        },
    }
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
MAX_IMAGE_UPLOAD_BYTES = 4 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Cache / Redis ───────────────────────────────────────────────────────────
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# ── Celery ──────────────────────────────────────────────────────────────────
# Redis is only the broker. Booking correctness never depends on it.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL or "memory://")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = env("CELERY_TASK_ALWAYS_EAGER")
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULE = {
    "auto-release-no-shows": {"task": "checkins.sweep_no_shows", "schedule": 60.0},
    "complete-finished-bookings": {"task": "checkins.sweep_completed", "schedule": 300.0},
    "expire-stale-approvals": {"task": "approvals.sweep_expired", "schedule": 300.0},
    "send-reminders": {"task": "notifications.send_reminders", "schedule": 300.0},
    "check-in-open-nudges": {"task": "notifications.send_checkin_nudges", "schedule": 60.0},
    "maintenance-transitions": {"task": "maintenance.sweep_windows", "schedule": 300.0},
    "lift-expired-restrictions": {"task": "checkins.sweep_restrictions", "schedule": 3600.0},
    "nightly-utilisation-snapshot": {
        "task": "analytics.build_snapshots",
        "schedule": crontab(hour=1, minute=15),
    },
}

# ── REST API ────────────────────────────────────────────────────────────────
# Reverse proxies in front of the app that append to X-Forwarded-For (Render, Railway, a load
# balancer: 1). 0 means clients connect directly and the header is ignored (SEC-07). The audit
# log, the sign-in rate limiter and the API throttle all derive the client address from it.
TRUSTED_PROXY_HOPS = env.int("TRUSTED_PROXY_HOPS", default=0)
# Alternatively, name a header that the edge proxy *sets* (overwriting anything the client sent).
# Railway documents X-Real-IP as its client-address header and does not document how it treats
# X-Forwarded-For, so on Railway use TRUSTED_CLIENT_IP_HEADER=X-Real-IP and leave the hop count
# at 0. Never set this when clients can reach the app without passing through that proxy.
TRUSTED_CLIENT_IP_HEADER = env("TRUSTED_CLIENT_IP_HEADER", default="")

REST_FRAMEWORK = {
    # DRF's own X-Forwarded-For handling, for any throttle other than apps.core.throttling's.
    "NUM_PROXIES": TRUSTED_PROXY_HOPS,
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        # Same client address as the sign-in limiter and the audit log (apps.core.http.client_ip).
        "apps.core.throttling.ClientUserRateThrottle",
        "apps.core.throttling.ClientAnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"user": env("API_USER_RATE", default="600/min"), "anon": "60/min"},
    "EXCEPTION_HANDLER": "apps.core.api.exception_handler",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "LPU Reserve API",
    "DESCRIPTION": "Campus Resource, Laboratory & Facility Booking Platform (EduRev P20).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # The live schema and Swagger UI are for signed-in users (SEC-14). Integrators who are not
    # users (the P13 timetable feed) use the published docs/openapi.yaml.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "ENUM_NAME_OVERRIDES": {
        "BookingStatusEnum": "apps.bookings.models.BookingStatus",
        "ResourceStatusEnum": "apps.catalogue.models.ResourceStatus",
        "MaintenanceWindowStatusEnum": "apps.maintenance.models.WindowStatus",
        "BreakdownReportStatusEnum": "apps.maintenance.models.ReportStatus",
        "PublicationStatusEnum": "apps.timetable.models.PublicationStatus",
        "MaintenanceKindEnum": "apps.maintenance.models.MaintenanceKind",
        "NotificationKindEnum": "apps.notifications.models.Kind",
    },
}

# ── Security ────────────────────────────────────────────────────────────────
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 10
CSRF_COOKIE_SAMESITE = "Lax"
# No script reads the CSRF cookie (htmx sends the token from the page via hx-headers), so it
# need not be visible to JavaScript.
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
if not DEBUG:  # pragma: no cover - production hardening
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT")
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # Submitting a domain to the browsers' HSTS preload list is a domain-wide, effectively
    # irreversible decision for whoever owns the university's domain, so it is opt-in. While it
    # is off, Django's reminder about it (security.W021) is a known, accepted state.
    SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
    if not SECURE_HSTS_PRELOAD:
        SILENCED_SYSTEM_CHECKS = ["security.W021"]
RATELIMIT_USE_CACHE = "default"
RATELIMIT_IP_META_KEY = "apps.core.http.client_ip"
LOGIN_LOCKOUT_THRESHOLD = 5
# CES §1.1: TOTP MFA for admin roles. Demo persona sign-in (DEMO_MODE only) skips it.
MFA_REQUIRED_ROLES = env.list("MFA_REQUIRED_ROLES", default=["admin", "facility_manager"])
MFA_ENFORCED = env.bool("MFA_ENFORCED", default=True)
LOGIN_LOCKOUT_MINUTES = 15

# ── Email ───────────────────────────────────────────────────────────────────
# Two delivery paths, chosen by EMAIL_BACKEND:
#   * SMTP  — django.core.mail.backends.smtp.EmailBackend with the EMAIL_HOST* settings below.
#   * HTTPS API — anymail.backends.{resend,postmark,sendgrid,mailgun}.EmailBackend with that
#     provider's key. Railway disables outbound SMTP on its Free, Trial and Hobby plans, so an
#     HTTPS provider is the portable choice there (docs/deployment-railway.md#email).
# Console output is the default for development; production with it fails check --deploy (lpu.E002).
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="LPU Reserve <reserve@lpu.example>")
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)
ANYMAIL = {
    k: v
    for k, v in {
        "RESEND_API_KEY": env("RESEND_API_KEY", default=""),
        "POSTMARK_SERVER_TOKEN": env("POSTMARK_SERVER_TOKEN", default=""),
        "SENDGRID_API_KEY": env("SENDGRID_API_KEY", default=""),
        "MAILGUN_API_KEY": env("MAILGUN_API_KEY", default=""),
        "MAILGUN_SENDER_DOMAIN": env("MAILGUN_SENDER_DOMAIN", default=""),
    }.items()
    if v
}

# Railway injects the service's public hostname. Trust it automatically (it is ours), so a fresh
# deployment answers on its *.up.railway.app domain without hand-editing ALLOWED_HOSTS and
# CSRF_TRUSTED_ORIGINS; custom domains still go in those variables explicitly.
RAILWAY_PUBLIC_DOMAIN = env("RAILWAY_PUBLIC_DOMAIN", default="")
if RAILWAY_PUBLIC_DOMAIN:
    if RAILWAY_PUBLIC_DOMAIN not in ALLOWED_HOSTS:
        ALLOWED_HOSTS = [*ALLOWED_HOSTS, RAILWAY_PUBLIC_DOMAIN]
    if f"https://{RAILWAY_PUBLIC_DOMAIN}" not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS = [*CSRF_TRUSTED_ORIGINS, f"https://{RAILWAY_PUBLIC_DOMAIN}"]
SITE_URL = env(
    "SITE_URL", default=f"https://{RAILWAY_PUBLIC_DOMAIN}" if RAILWAY_PUBLIC_DOMAIN else "http://localhost:8000"
)

# ── Error tracking (optional) ───────────────────────────────────────────────
# CES §1.1 asks for Sentry. Off unless SENTRY_DSN is set. No personal data is sent: no request
# bodies, cookies, user details or IP addresses (CES §1.4 "no personal data in logs").
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:  # pragma: no cover - exercised only with a real DSN
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", default=env("RAILWAY_ENVIRONMENT_NAME", default="production")),
        release=env("RAILWAY_GIT_COMMIT_SHA", default=None),
        integrations=[DjangoIntegration(), CeleryIntegration()],
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
    )

# ── Logging ─────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "pythonjsonlogger.json.JsonFormatter", "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s"},
        "plain": {"format": "%(asctime)s %(levelname)-7s %(name)s: %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json" if env("LOG_JSON") else "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}

# ── Product configuration ───────────────────────────────────────────────────
DEFAULT_INSTITUTION_CODE = env("DEFAULT_INSTITUTION_CODE", default="LPU")
SLOT_MINUTES = 30
