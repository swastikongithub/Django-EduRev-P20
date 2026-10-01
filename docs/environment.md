# Environment variables

All configuration comes from environment variables, read by `django-environ` in
`config/settings.py`. A `.env` file in the project root is loaded for local development
(`cp .env.example .env`) and never overrides variables already set in the environment. No
secret is committed; CI runs gitleaks on every push.

Booleans accept `1/0`, `true/false`, `yes/no`, `on/off`. Lists are comma-separated.

## Application settings (`config/settings.py`)

### Core

| Variable | Default | Purpose | Production guidance |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | `dev-only-insecure-key-change-me` with `DEBUG=1`; none otherwise | Django signing key (sessions, CSRF, password reset tokens) and the source of the MFA encryption key | **Required.** 50+ random characters from a secrets store. With `DEBUG=0` start-up fails (`ImproperlyConfigured`) if the key is missing, shorter than 32 characters, a known placeholder, `django-insecure-*`, or a public `dev-only-*` key outside `DEMO_MODE=1`. Rotating it signs everyone out and makes every stored MFA secret undecryptable (see [runbook](runbook.md#secret-rotation)) |
| `DEBUG` | `False` | Debug pages, plain static storage, insecure cookies | `0`. With `0`, secure cookies, HSTS (30 days) and proxy SSL header handling are switched on |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Host header allow-list | The public host name(s). Probes on `/health/` and `/ready/` work without it |
| `CSRF_TRUSTED_ORIGINS` | empty | Origins allowed to POST over HTTPS | `https://reserve.example.edu` (scheme included) |
| `SECURE_SSL_REDIRECT` | `False` | Redirect HTTP to HTTPS (only read when `DEBUG=0`) | `1` unless the proxy or platform already redirects |
| `SITE_URL` | `http://localhost:8000` | Absolute base for links in emails, door QR codes and booking-pass QR codes | The public HTTPS URL. Changing it changes printed door QR codes; reprint them |
| `DEMO_MODE` | `False` | Shows one-click demo persona sign-in on the login page | **Must be `0`.** Personas bypass passwords and MFA |
| `DEFAULT_INSTITUTION_CODE` | `LPU` | Tenant used for anonymous requests and as the default `institution` on new rows | Leave as `LPU` for a single-tenant deployment |

### Database

| Variable | Default | Purpose | Production guidance |
|---|---|---|---|
| `DATABASE_URL` | `postgres://edurev@localhost:5433/edurev` | PostgreSQL connection (`postgres://user:password@host:port/db`) | Managed PostgreSQL 16+. The role needs to create the `btree_gist` and `pg_trgm` extensions on first migrate (or have them pre-created) |
| `DB_CONN_MAX_AGE` | `60` | Seconds a connection is reused (`CONN_MAX_AGE`); health checks enabled | Keep `60` without a pooler. With PgBouncer in transaction mode, set `0` |
| `TEST_DATABASE_NAME` | `test_edurev` | Name of the throwaway database pytest creates | Tests only |

### Redis, cache and Celery

| Variable | Default | Purpose | Production guidance |
|---|---|---|---|
| `REDIS_URL` | empty | Django cache (sign-in rate limits, API throttling, Insights cache) and default Celery broker. Empty means per-process in-memory cache | `redis://host:6379/0`. When set, Redis availability affects sign-in, the API and Insights (see [known issues](known-issues.md#operations)) |
| `CELERY_BROKER_URL` | `REDIS_URL`, else `memory://` | Celery broker | A separate Redis database from the cache, for example `redis://host:6379/1` (as in docker compose) |
| `CELERY_TASK_ALWAYS_EAGER` | `False` | Run tasks inline in the caller instead of through a broker | `0`. `1` only for local development and tests |

### Security and authentication

| Variable | Default | Purpose | Production guidance |
|---|---|---|---|
| `MFA_REQUIRED_ROLES` | `admin,facility_manager` | Roles that must pass TOTP after a password sign-in (superusers always) | Keep the default or add `dept_head`, `custodian` |
| `MFA_ENFORCED` | `True` | Master switch for the above | Must be `1` |
| `TRUSTED_PROXY_HOPS` | `0` | Number of reverse proxies in front of the app that append to `X-Forwarded-For`. The client address used by the audit log and the rate limiter is the entry that many places from the right; with `0` the header is ignored and `REMOTE_ADDR` is used | `1` behind a single platform load balancer (Render, Railway, nginx). Never higher than the real number of proxies: every extra hop lets clients choose their own address |
| `API_USER_RATE` | `600/min` | DRF throttle per signed-in user (anonymous is fixed at `60/min`) | Lower for public exposure; raise for integrations such as the load test |

Fixed in code (not environment): sign-in lockout after 5 failures for 15 minutes (password and
TOTP failures count together; a locked account gets the same answer as a wrong password); IP rate
limits of 20/min on sign-in and MFA and 30/min on demo sign-in; single-use TOTP codes; session
lifetime 10 hours; the live API schema (`/api/v1/schema/`, `/api/v1/docs/`) requires sign-in.

### Email

| Variable | Default | Purpose | Production guidance |
|---|---|---|---|
| `EMAIL_BACKEND` | `django.core.mail.backends.console.EmailBackend` | How notification email is sent | `django.core.mail.backends.smtp.EmailBackend`. Note: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` and `EMAIL_USE_TLS` are **not** read from the environment yet, so SMTP uses Django's defaults (`localhost:25`, no auth). Use a local relay or extend settings ([known issues](known-issues.md)) |
| `DEFAULT_FROM_EMAIL` | `LPU Reserve <reserve@lpu.example>` | Sender address | An address on a domain with SPF/DKIM for the relay |

### Files and static assets

| Variable | Default | Purpose | Production guidance |
|---|---|---|---|
| `MEDIA_ROOT` | `<project>/.media` | Where uploaded resource photos are written | A persistent volume shared by web replicas. Uploaded media is not served by any URL yet ([known issues](known-issues.md#files-and-storage)) |
| `USE_S3` | `False` | Switch default storage to S3-compatible object storage with 15-minute pre-signed URLs | Not usable yet: `django-storages` and `boto3` are not in `requirements.txt`, so `USE_S3=1` fails at start-up |
| `S3_BUCKET` | none (required when `USE_S3=1`) | Bucket name | |
| `S3_ENDPOINT_URL` | none | Endpoint for R2 / MinIO; omit for AWS | |
| `STATICFILES_BACKEND` | `whitenoise.storage.CompressedManifestStaticFilesStorage` when `DEBUG=0`, else plain | Static file storage | Keep the default; the image runs `collectstatic` at build |

### Logging

| Variable | Default | Purpose | Production guidance |
|---|---|---|---|
| `LOG_JSON` | `False` (`1` in the Docker image) | JSON log lines via `python-json-logger` | `1` |
| `LOG_LEVEL` | `INFO` | Root log level (`django.db.backends` is pinned to `WARNING`) | `INFO` |

## Container and process variables

Read by the `Dockerfile`, `docker/entrypoint.sh` or `docker-compose.yml`, not by Django.

| Variable | Default | Read by | Purpose |
|---|---|---|---|
| `PORT` | `8000` | Dockerfile `CMD` | gunicorn bind port |
| `WEB_CONCURRENCY` | `3` | Dockerfile `CMD` | gunicorn worker processes |
| `RUN_MIGRATIONS` | `0` (`1` on compose `web`) | entrypoint | Run `manage.py migrate --noinput` before starting. Set on exactly one process per release |
| `DB_WAIT_TIMEOUT` | `60` | entrypoint | Seconds to wait for PostgreSQL before giving up |
| `DJANGO_SETTINGS_MODULE` | `config.settings` | Dockerfile | Settings module |
| `CELERY_CONCURRENCY` | `2` | compose `worker` | Celery worker processes |
| `POSTGRES_PASSWORD` | `edurev` | compose `db`, `DATABASE_URL` | Local database password (development only) |
| `POSTGRES_HOST_PORT` | `5434` | compose `db` | Host port for the compose database |
| `WEB_PORT` | `8000` | compose `web` | Host port for the web container |

## Tooling variables

| Variable | Default | Read by | Purpose |
|---|---|---|---|
| `DEMO_PASSWORD` | empty | `manage.py seed_demo` | Password for every seeded account. Empty gives new accounts an unusable password (persona sign-in only) |
| `CONCURRENCY_ATTEMPTS` | `500` | `tests/test_concurrency.py` | Attempts in the full-service stampede |
| `RAW_CONCURRENCY_ATTEMPTS` | `100` | `tests/test_concurrency.py` | Attempts in the constraint-only stampede (500 verified locally) |
| `PG_BIN` | `/c/Program Files/PostgreSQL/18/bin` | `scripts/devdb.sh` | PostgreSQL binaries for the local cluster |
| `PGPORT` | `5433` | `scripts/devdb.sh` | Local cluster port |
| `LOCUST_PASSWORD`, `LOCUST_RESOURCE_ID` | required | `loadtest/locustfile.py` | Sign-in password and the resource to contend for |
| `LOCUST_USERNAMES` or `LOCUST_USERNAME_TEMPLATE`, `LOCUST_USERNAME_START`, `LOCUST_USERNAME_COUNT` | `student{n}`, `1`, `0` (unbounded) | locustfile | Which accounts the virtual users sign in as |
| `LOCUST_SLOT_START`, `LOCUST_SLOT_END`, `LOCUST_SLOT_MINUTES` | next Mon–Sat 10:00 IST two days ahead, 60 min | locustfile | The contested slot |
| `LOCUST_LOGIN_PATH`, `LOCUST_BOOKING_PATH` | `/login/`, `/api/v1/bookings/` | locustfile | Endpoints |
| `LOCUST_SESSION_COOKIE`, `LOCUST_CSRF_COOKIE` | `sessionid`, `csrftoken` | locustfile | Cookie names |
| `LOCUST_TITLE`, `LOCUST_BARRIER_TIMEOUT`, `LOCUST_ONE_SHOT`, `LOCUST_QUIT_WHEN_DONE` | `P20 peak load test`, `120`, `1`, `1` | locustfile | Run behaviour |

## Minimal production set

```bash
DJANGO_SECRET_KEY=<from secrets store>
DEBUG=0
DEMO_MODE=0
ALLOWED_HOSTS=reserve.example.edu
CSRF_TRUSTED_ORIGINS=https://reserve.example.edu
SITE_URL=https://reserve.example.edu
SECURE_SSL_REDIRECT=1
TRUSTED_PROXY_HOPS=1
DATABASE_URL=postgres://reserve:<password>@db.internal:5432/reserve
REDIS_URL=redis://redis.internal:6379/0
CELERY_BROKER_URL=redis://redis.internal:6379/1
CELERY_TASK_ALWAYS_EAGER=0
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DEFAULT_FROM_EMAIL=LPU Reserve <reserve@example.edu>
MEDIA_ROOT=/app/.media
LOG_JSON=1
```

Run `python manage.py check --deploy` against this environment before the first release.
