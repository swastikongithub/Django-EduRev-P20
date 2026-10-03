# Environment variables

All configuration comes from environment variables, read by `django-environ` in
`config/settings.py`. A `.env` file in the project root is loaded for local development
(`cp .env.example .env`) and never overrides variables already set in the environment. No
secret is committed; CI runs gitleaks on every push.

Booleans accept `1/0`, `true/false`, `yes/no`, `on/off`. Lists are comma-separated. An empty
value counts as unset and falls back to the default. Railway, for example, resolves a reference to an
undefined shared variable to an empty string. For the Railway service-by-service configuration,
see [deployment-railway.md](deployment-railway.md).

## Application settings (`config/settings.py`)

### Core

| Variable | Default | Purpose | Production guidance |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | `dev-only-insecure-key-change-me` with `DEBUG=1`; none otherwise | Django signing key (sessions, CSRF, password reset tokens) and the source of the MFA encryption key | **Required.** 50+ random characters from a secrets store. With `DEBUG=0` start-up fails (`ImproperlyConfigured`) if the key is missing, shorter than 32 characters, a known placeholder, `django-insecure-*`, or a public `dev-only-*` key outside `DEMO_MODE=1`. Rotate it through `DJANGO_SECRET_KEY_FALLBACKS`: changing it without a fallback signs everyone out and makes every stored MFA secret unreadable ([runbook](runbook.md#secret-rotation)) |
| `DJANGO_SECRET_KEY_FALLBACKS` | empty | Previous keys, newest first, during a rotation (Django's `SECRET_KEY_FALLBACKS`). Sessions and tokens signed with them stay valid, and TOTP secrets encrypted under them stay readable until moved (`manage.py mfa_keys --rotate`) | Only during a rotation ([runbook](runbook.md#secret-rotation)). With `DEBUG=0` each entry must meet the same rules as the key, because signatures made with it are still accepted |
| `DEBUG` | `False` | Debug pages, plain static storage, insecure cookies | `0`. With `0`, secure cookies, HSTS (30 days) and proxy SSL header handling are switched on |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Host header allow-list | The public host name(s). Probes on `/health/` and `/ready/` work without it |
| `CSRF_TRUSTED_ORIGINS` | empty | Origins allowed to POST over HTTPS | `https://reserve.example.edu` (scheme included) |
| `SECURE_SSL_REDIRECT` | `False` | Redirect HTTP to HTTPS (only read when `DEBUG=0`) | `1` unless the proxy or platform already redirects |
| `SECURE_HSTS_PRELOAD` | `False` | Adds `preload` to the HSTS header (only read when `DEBUG=0`). While off, Django's reminder `security.W021` is silenced | Leave off unless the university decides to submit its domain to the browsers' HSTS preload list, a domain-wide and effectively irreversible step |
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
| `BOOTSTRAP_SETUP_CODE` | empty | When set, first-run setup (`/setup/bootstrap/`, open only while the database has no accounts) also asks for this value | Optional. Set a random value before the first deploy of a public site, so nobody who finds a fresh deployment first can claim it; it has no effect once any account exists |
| `TRUSTED_PROXY_HOPS` | `0` | Number of reverse proxies in front of the app that append to `X-Forwarded-For`. The client address used by the audit log, the sign-in rate limiter and the API throttles is the entry that many places from the right; with `0` the header is ignored and `REMOTE_ADDR` is used | `1` behind a single proxy that appends to `X-Forwarded-For` (nginx, Render). On Railway leave `0` and use `TRUSTED_CLIENT_IP_HEADER`. Never higher than the real number of proxies: every extra hop lets clients choose their own address |
| `TRUSTED_CLIENT_IP_HEADER` | empty | A header that the edge proxy itself *sets*, overwriting anything the client sent, holding the client address. When set and valid, it wins over `TRUSTED_PROXY_HOPS`; a malformed value falls back to the connection address | `X-Real-IP` on Railway (its documented client-address header). Never set it where clients can reach the app without passing through that proxy, or they could choose their own address |
| `API_USER_RATE` | `600/min` | DRF throttle per signed-in user (anonymous is fixed at `60/min`) | Lower for public exposure; raise for integrations such as the load test |

Fixed in code (not environment): sign-in lockout after 5 failures for 15 minutes (password and
TOTP failures count together, under a row lock so concurrent guesses cannot race past it; a locked
account gets the same answer as a wrong password); IP rate limits of 20/min on sign-in and MFA,
30/min on demo sign-in, and 5/min and 20/hour on first-run setup; single-use TOTP codes; a password-verified sign-in waits at most 10 minutes
for its TOTP code; session lifetime 10 hours; `HttpOnly`, `SameSite=Lax` session and CSRF cookies
(`Secure` with `DEBUG=0`); static files without a wildcard CORS header; the live API schema
(`/api/v1/schema/`, `/api/v1/docs/`) requires sign-in.

### Email

| Variable | Default | Purpose | Production guidance |
|---|---|---|---|
| `EMAIL_BACKEND` | `django.core.mail.backends.console.EmailBackend` | How notification email is sent | An HTTPS API through django-anymail: `anymail.backends.resend.EmailBackend`, `…postmark…`, `…sendgrid…` or `…mailgun…`. Railway blocks SMTP except on Pro. Otherwise `django.core.mail.backends.smtp.EmailBackend`. `check --deploy` refuses a backend that does not deliver (`lpu.E002`) |
| `DEFAULT_FROM_EMAIL` | `LPU Reserve <reserve@lpu.example>` | Sender address | An address on a domain verified with the provider (SPF and DKIM) |
| `SERVER_EMAIL` | `DEFAULT_FROM_EMAIL` | Sender of Django's own error mail | Leave |
| `EMAIL_HOST`, `EMAIL_PORT` | `localhost`, `587` | SMTP relay | The provider's relay. `check --deploy` warns on `localhost` (`lpu.W005`) |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | empty | SMTP credentials | From the secrets store |
| `EMAIL_USE_TLS`, `EMAIL_USE_SSL` | `True`, `False` | STARTTLS (587) or implicit TLS (465) | Keep STARTTLS on 587 |
| `EMAIL_TIMEOUT` | `15` | Seconds before an SMTP attempt fails (the worker retries on its next sweep) | Leave |
| `RESEND_API_KEY` | empty | Resend API key (anymail) | Required with the Resend backend (`lpu.E004`) |
| `POSTMARK_SERVER_TOKEN`, `SENDGRID_API_KEY`, `MAILGUN_API_KEY`, `MAILGUN_SENDER_DOMAIN` | empty | Keys for the other anymail backends | Required with the matching backend |

### Files and static assets

| Variable | Default | Purpose | Production guidance |
|---|---|---|---|
| `MEDIA_ROOT` | `<project>/.media` | Where uploaded resource photos are written when `USE_S3=0`. `runserver` serves them under `/media/` with `DEBUG=1` | Development and docker compose only: container disks are lost on redeploy |
| `USE_S3` | `False` | Store uploads in S3-compatible object storage (`django-storages`); every photo URL is a pre-signed `GET` | **`1` in production.** `check --deploy` refuses `0` (`lpu.E001`). Check with `python manage.py verify_storage` |
| `S3_BUCKET` | none (required when `USE_S3=1`) | Bucket name | Railway: the bucket's `BUCKET` |
| `S3_ENDPOINT_URL` | none | S3 endpoint; omit for AWS | Railway: `ENDPOINT` (for example `https://t3.storageapi.dev`) |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | none (boto3's default chain) | Bucket credentials | Railway: `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY` |
| `S3_REGION` | none | Signing region | Railway: `REGION` (`auto`) |
| `S3_ADDRESSING_STYLE` | `virtual` | `virtual` (bucket in the host name) or `path` | `virtual` for Railway buckets; `path` for MinIO-style emulators |
| `S3_MEDIA_PREFIX` | `media` | Key prefix for uploads inside the bucket | Leave |
| `S3_URL_EXPIRY_SECONDS` | `900` | Lifetime of pre-signed photo URLs | Leave (15 minutes) |
| `STATICFILES_BACKEND` | `whitenoise.storage.CompressedManifestStaticFilesStorage` when `DEBUG=0`, else plain | Static file storage | Keep the default; the image runs `collectstatic` at build |

### Logging

| Variable | Default | Purpose | Production guidance |
|---|---|---|---|
| `LOG_JSON` | `False` (`1` in the Docker image) | JSON log lines via `python-json-logger` | `1` |
| `LOG_LEVEL` | `INFO` | Root log level (`django.db.backends` is pinned to `WARNING`) | `INFO` |

### Error tracking

| Variable | Default | Purpose | Production guidance |
|---|---|---|---|
| `SENTRY_DSN` | empty (off) | Send exceptions from web, worker and beat to Sentry. No personal data: no request bodies, cookies, users or IP addresses | Recommended (CES §1.1) |
| `SENTRY_ENVIRONMENT` | `RAILWAY_ENVIRONMENT_NAME`, else `production` | Environment tag | Leave on Railway |
| `SENTRY_TRACES_SAMPLE_RATE` | `0` | Fraction of requests traced for performance | `0` unless investigating |

### Provided by the platform

| Variable | Read by | Purpose |
|---|---|---|
| `RAILWAY_PUBLIC_DOMAIN` | settings | Added to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` automatically, and the default for `SITE_URL` (`https://<domain>`) on the service that has it |
| `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_GIT_COMMIT_SHA` | settings | Sentry environment and release |

## Container and process variables

Read by the `Dockerfile`, `docker/entrypoint.sh` or `docker-compose.yml`, not by Django.

| Variable | Default | Read by | Purpose |
|---|---|---|---|
| `PORT` | `8000` | Dockerfile `CMD` | gunicorn bind port |
| `WEB_CONCURRENCY` | `3` | Dockerfile `CMD` | gunicorn worker processes |
| `RUN_MIGRATIONS` | `0` (`1` on compose `web`) | entrypoint | Run `manage.py migrate --noinput` before starting (docker compose). On Railway leave unset: the `web` pre-deploy command runs `docker/predeploy.sh` (deployment checks, then migrate) once per release |
| `DB_WAIT_TIMEOUT` | `60` | entrypoint | Seconds to wait for PostgreSQL before giving up |
| `DJANGO_SETTINGS_MODULE` | `config.settings` | Dockerfile | Settings module |
| `CELERY_CONCURRENCY` | `2` | compose `worker` | Celery worker processes |
| `POSTGRES_PASSWORD` | `edurev` | compose `db`, `DATABASE_URL` | Local database password (development only) |
| `POSTGRES_HOST_PORT` | `5434` | compose `db` | Host port for the compose database |
| `WEB_PORT` | `8000` | compose `web` | Host port for the web container |

## Backup service (`docker/backup/`)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | required | Database to dump |
| `BACKUP_S3_BUCKET`, `BACKUP_S3_ENDPOINT_URL`, `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY`, `BACKUP_S3_REGION` | required (endpoint and region optional for AWS) | Destination bucket, separate from `media` |
| `BACKUP_S3_ADDRESSING_STYLE` | `virtual` | As `S3_ADDRESSING_STYLE` |
| `BACKUP_S3_PREFIX` | `pg` | Key prefix |
| `BACKUP_RETENTION_DAYS` | `14` | Older dumps are deleted after each backup; the newest is always kept. `0` keeps everything |
| `BACKUP_AGE_RECIPIENT` | empty | age public key; when set, dumps are encrypted before upload |
| `PG_MAJOR` | `17` | **Build argument**: PostgreSQL client major version, which must equal the server's |

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

For a container platform other than Railway (Railway: [deployment-railway.md](deployment-railway.md)):

```bash
DJANGO_SECRET_KEY=<from secrets store>
DEBUG=0
DEMO_MODE=0
ALLOWED_HOSTS=reserve.example.edu
CSRF_TRUSTED_ORIGINS=https://reserve.example.edu
SITE_URL=https://reserve.example.edu
SECURE_SSL_REDIRECT=1
TRUSTED_PROXY_HOPS=1                      # or TRUSTED_CLIENT_IP_HEADER=<header the edge sets>
DATABASE_URL=postgres://reserve:<password>@db.internal:5432/reserve
REDIS_URL=redis://redis.internal:6379/0
CELERY_BROKER_URL=redis://redis.internal:6379/1
USE_S3=1
S3_BUCKET=<bucket>
S3_ENDPOINT_URL=<endpoint>
S3_ACCESS_KEY_ID=<from secrets store>
S3_SECRET_ACCESS_KEY=<from secrets store>
EMAIL_BACKEND=anymail.backends.resend.EmailBackend
RESEND_API_KEY=<from secrets store>
DEFAULT_FROM_EMAIL=LPU Reserve <reserve@example.edu>
LOG_JSON=1
```

`python manage.py check --deploy` must pass against this environment. The release step
(`docker/predeploy.sh`) runs it with `--fail-level ERROR` before migrating, and CI runs it with
`--fail-level WARNING`.
