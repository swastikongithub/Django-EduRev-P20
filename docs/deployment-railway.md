# Deploying to Railway

LPU Reserve is ready to deploy to [Railway](https://railway.com), but **has not been deployed**.
This guide is the complete configuration, plus what is still needed from a person
([blockers](#what-is-still-needed-before-the-first-deploy)).

The platform configuration is code: [`.railway/railway.ts`](../.railway/railway.ts), written for Railway's
[Infrastructure as Code](https://docs.railway.com/infrastructure-as-code) (TypeScript SDK `railway`
3.12, Railway CLI 5.42.1 or newer). CI type-checks it against the pinned SDK on every push. The
older `railway.toml` / `railway.json` config-as-code files are deprecated by Railway and are not
used here. A service managed by them must be migrated before IaC can manage it.

## Topology

| Railway resource | Kind | Built from | Runs | Replicas |
|---|---|---|---|---|
| `web` | service | `Dockerfile` | gunicorn on `$PORT` (image default command) | 1 (more is safe) |
| `worker` | service | `Dockerfile` | `sh /app/docker/entrypoint.sh celery -A config worker -l info --concurrency 2` | 1 (more is safe) |
| `beat` | service | `Dockerfile` | `sh /app/docker/entrypoint.sh python manage.py run_beat` | 1 |
| `backup` | cron service, `30 20 * * *` UTC (02:00 IST) | `docker/backup/Dockerfile` | `pgbackup.py backup` | n/a |
| `postgres` | database | Railway PostgreSQL | | |
| `redis` | database | Railway Redis | cache + Celery broker | |
| `media` | bucket (private) | | uploaded resource photos | |
| `backups` | bucket (private) | | nightly database dumps | |

All four services deploy from `main` of `swastikongithub/Django-EduRev-P20` with
`checkSuites: true`: Railway waits for the GitHub checks (the whole CI workflow) to pass before it
deploys a commit. A start command on Railway replaces the image's `ENTRYPOINT`, so `worker`,
`beat` and the pre-deploy command name `docker/entrypoint.sh` explicitly. The entrypoint waits
for PostgreSQL, then runs the command.

## Variables

### Shared variables (Project Settings → Shared Variables)

These are set by a person, once, and referenced by `web`, `worker` and `beat`
(`ctx.shared.NAME` in the IaC file). None of them is in the repository.

| Variable | Required | Value |
|---|---|---|
| `DJANGO_SECRET_KEY` | **yes** | `python -c "import secrets; print(secrets.token_urlsafe(50))"`. Mark it **sealed**. Rotate only through a `DJANGO_SECRET_KEY_FALLBACKS` shared variable holding the old key (then `railway ssh --service web -- python manage.py mfa_keys --rotate`): it also encrypts stored TOTP secrets ([runbook](runbook.md#secret-rotation)) |
| `DJANGO_SECRET_KEY_FALLBACKS` | only while rotating | The previous key. Sealed. Remove it once `mfa_keys` reports `fallback key only: 0` |
| `SITE_URL` | **yes** | The public HTTPS URL, for example `https://reserve.lpu.in` or `https://<web>.up.railway.app`. Used in email links and printed door QR codes. Without it, worker emails would link to `localhost` |
| `ALLOWED_HOSTS` | with a custom domain | The custom host, for example `reserve.lpu.in`. The `*.up.railway.app` domain is trusted automatically from `RAILWAY_PUBLIC_DOMAIN` |
| `CSRF_TRUSTED_ORIGINS` | with a custom domain | `https://reserve.lpu.in` |
| `DEFAULT_FROM_EMAIL` | **yes** | For example `LPU Reserve <reserve@lpu.in>`, on a domain verified with the email provider |
| `EMAIL_BACKEND` | **yes** | `anymail.backends.resend.EmailBackend` (recommended, HTTPS) or `django.core.mail.backends.smtp.EmailBackend` (Railway Pro only) |
| `RESEND_API_KEY` | with Resend | The provider API key. Mark it **sealed** |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | with SMTP | The relay, on port 587 with STARTTLS (`EMAIL_USE_TLS` defaults to on) |
| `SENTRY_DSN` | optional | Error tracking ([below](#error-tracking)) |
| `BACKUP_AGE_RECIPIENT` | recommended | The public half of an [age](https://age-encryption.org) key pair (`age1…`), so dumps are encrypted before upload ([backup-restore.md](backup-restore.md)) |

A shared variable that is never defined resolves to an empty string. The settings treat empty as
unset, so optional ones can be left out.

### Set by the IaC file (no action needed)

| Variable | Services | Value |
|---|---|---|
| `DEBUG`, `DEMO_MODE` | web, worker, beat | `0` |
| `SECURE_SSL_REDIRECT` | web, worker, beat | `1` |
| `TRUSTED_CLIENT_IP_HEADER` / `TRUSTED_PROXY_HOPS` | web, worker, beat | `X-Real-IP` / `0` ([client addresses](#client-addresses-and-rate-limits)) |
| `LOG_JSON` | web, worker, beat | `1` |
| `DATABASE_URL` | web, worker, beat, backup | `${{postgres.DATABASE_URL}}` (private network) |
| `REDIS_URL` | web, worker, beat | `${{redis.REDIS_URL}}`; the Celery broker defaults to it |
| `USE_S3` | web, worker, beat | `1` |
| `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION` | web, worker, beat | the `media` bucket's `BUCKET`, `ENDPOINT`, `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY`, `REGION` |
| `WEB_CONCURRENCY` | web | `3` gunicorn workers |
| `PG_MAJOR` | backup | `17`. **Must equal the `postgres` service's major version** (`SHOW server_version`). It is passed to the backup image build |
| `BACKUP_S3_*` | backup | the `backups` bucket's credentials |
| `BACKUP_RETENTION_DAYS` | backup | `14` |

Railway itself provides `PORT`, `RAILWAY_PUBLIC_DOMAIN`, `RAILWAY_ENVIRONMENT_NAME` and
`RAILWAY_GIT_COMMIT_SHA`. The app uses them to bind, to trust its own domain, and to tag Sentry events.

## Object storage

Uploaded resource photos go to the private `media` bucket through `django-storages`. Every photo
URL the app renders is an S3 v4 pre-signed `GET` that expires after 15 minutes
(`S3_URL_EXPIRY_SECONDS`), as CES §1.4 requires. Railway buckets are private-only, so nothing is
public by accident. Railway volumes are not used: a volume is mounted as `root`, and the image
deliberately runs as an unprivileged user (uid 10001).

`check --deploy` refuses a production configuration without `USE_S3=1` (`lpu.E001`). After the
first deploy, prove the bucket works end to end:

```bash
railway ssh --service web -- python manage.py verify_storage
# Media storage OK (S3Storage): write, read via pre-signed URL, delete.
```

CI runs the same command against an S3 emulator on every push.

## Email

Booking confirmations, approval requests, reminders and check-in nudges are sent by the
`worker`. Railway disables outbound SMTP on the Free, Trial and Hobby plans and enables it on
Pro. The configuration therefore supports both:

* **HTTPS API (recommended, any plan).** Use [django-anymail](https://anymail.dev) with
  `EMAIL_BACKEND=anymail.backends.resend.EmailBackend` and `RESEND_API_KEY`. Postmark
  (`POSTMARK_SERVER_TOKEN`), SendGrid (`SENDGRID_API_KEY`) and Mailgun (`MAILGUN_API_KEY`,
  `MAILGUN_SENDER_DOMAIN`) are wired the same way. To use one of them, add its variable to the
  `app` block in `.railway/railway.ts`.
* **SMTP (Railway Pro).** Use `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` with
  `EMAIL_HOST`, `EMAIL_PORT` (587), `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`. `EMAIL_USE_TLS`
  defaults on; set `EMAIL_USE_SSL=1` and `EMAIL_USE_TLS=0` for port 465.

The sender domain must be verified with the provider (SPF and DKIM), or mail lands in spam.
`check --deploy` refuses the console backend (`lpu.E002`) and an API backend without its key
(`lpu.E004`). After deploying, send a test message:

```bash
railway ssh --service worker -- python manage.py sendtestemail you@lpu.in
```

## Migrations

The `web` service's **pre-deploy command** is
`sh /app/docker/entrypoint.sh sh /app/docker/predeploy.sh`. It runs once per deployment, in a
separate container from the same image, inside the private network, before the new release
takes traffic:

1. `python manage.py check --deploy --fail-level ERROR`. A release with a configuration that
   would lose uploads or never deliver mail never goes live.
2. `python manage.py migrate --noinput`.

If either step fails, the deployment stops and the previous release keeps serving. Railway does
not retry it. `RUN_MIGRATIONS` stays unset on Railway; it exists for docker compose only.
Because the old release serves traffic while the pre-deploy step runs, migrations must be
backwards compatible with the code that is still running. That means additive changes first, and
column or table removals in a later release (the expand/contract pattern). The `worker` and `beat` services have no
pre-deploy command, so migrations never run twice.

## Celery worker and exactly one Beat

`beat` runs `python manage.py run_beat`, which guarantees a single scheduler even if the
service is scaled, or if old and new deployments overlap during a redeploy:

* Before starting Celery Beat, it takes a PostgreSQL session advisory lock on a dedicated
  connection. A second instance logs `Another Celery Beat holds the scheduler lock` and waits.
* If the leader dies, PostgreSQL releases the lock with its session and a waiting instance takes
  over within 15 seconds. A watchdog exits the leader if its lock connection drops, so two
  schedulers never overlap.
* The schedule file lives in the container's temporary directory. Every interval sweep is
  idempotent, and the nightly analytics job rebuilds every day missed since the last snapshot,
  up to 31 days. A restart therefore loses nothing, and no volume is needed.

`tests/test_production_readiness.py` covers the lock, and CI exercises the takeover with two real
containers. The worker can be scaled freely: every sweep claims rows under row locks
([ADR 0006](adr/0006-celery-beat-sweeps-with-sweeprun.md)).

## Graceful shutdown

Each service's process runs as PID 1 (the entrypoint `exec`s it), so Railway's SIGTERM reaches it
directly. Railway then waits for the service's draining time before it sends SIGKILL:

| Service | On SIGTERM | Draining time |
|---|---|---|
| `web` | gunicorn stops accepting connections and lets in-flight requests finish (`--graceful-timeout 20`) | 25 s |
| `worker` | Celery warm shutdown: it takes no new tasks and finishes the running ones. Tasks are short (an email, a sweep); a killed sweep is simply re-run by the next tick, because sweeps are idempotent | 60 s |
| `beat` | Celery Beat exits; PostgreSQL releases its advisory lock with the connection, so the new deployment's `run_beat` takes over | 10 s |

Booking writes are single database transactions: a request cut off mid-way rolls back
completely and never leaves a half-made booking.

## Health checks

The `web` health check path is `/ready/`, which checks the database and Redis, with a 120 second
timeout. Railway calls it only while a deployment goes live (it is not continuous monitoring),
from the host `healthcheck.railway.app`. The probe middleware answers `/health/` and `/ready/`
before host validation and the HTTPS redirect, so the probe needs neither `ALLOWED_HOSTS` nor TLS.
A test covers exactly that host. For continuous monitoring, see
[what is still needed](#what-is-still-needed-before-the-first-deploy).

## Client addresses and rate limits

Railway's edge sets `X-Real-IP` to the client's address. It also documents `X-Forwarded-Proto`
(always `https`), `X-Forwarded-Host` and `X-Railway-Request-Id`. It does not document how it
treats an incoming `X-Forwarded-For`, so the app does not rely on that header on Railway.
`TRUSTED_CLIENT_IP_HEADER=X-Real-IP` makes `apps.core.http.client_ip` read it. That one function
feeds:

* the sign-in and MFA rate limits (django-ratelimit, `RATELIMIT_IP_META_KEY`);
* the audit log's IP column;
* the API throttles (`apps.core.throttling`), which previously used DRF's own `X-Forwarded-For` parsing.

A malformed header value falls back to the connection's address. It is never trusted as-is.
Without this setting, every visitor would appear to come from the edge's address and share one
anonymous rate-limit bucket. Only set it where clients cannot reach the app except through
that edge, which is true for Railway's public networking.

## Database and Redis

* **PostgreSQL**: Railway's PostgreSQL service, reached over the private network
  (`DATABASE_URL`, not `DATABASE_PUBLIC_URL`). The first `migrate` creates the `btree_gist` and
  `pg_trgm` extensions, which Railway's default superuser role allows. Connections are reused
  for 60 seconds (`DB_CONN_MAX_AGE`). Gunicorn (3 workers) plus the worker and beat use about 10
  connections, well under the default limit.
* **Redis**: Railway's Redis service. It backs the Django cache (rate limits, Insights) and is
  the Celery broker, in the same logical database. The app never calls `cache.clear()`, so the
  cache cannot flush queued tasks. A Redis outage degrades rate limiting, Insights and email, but
  never booking correctness ([OPS-4](known-issues.md#operations)).

## Backups

Two layers ([backup-restore.md](backup-restore.md)):

1. **Railway volume backups** of the `postgres` service (dashboard → postgres → Backups):
   daily (kept 6 days), weekly (kept 27 days) and monthly (kept 89 days) snapshots. A restore
   mounts the snapshot as a new volume.
2. **Nightly logical dumps** by the `backup` cron service: `pg_dump -Fc`, encrypted with age
   when `BACKUP_AGE_RECIPIENT` is set, streamed into the private `backups` bucket, with
   14-day retention. Railway buckets have no lifecycle rules, so the script prunes old dumps,
   always keeping the newest. CI restores such a dump into a fresh database on every push and
   compares row counts.

## Error tracking

Set `SENTRY_DSN` to enable Sentry for the web, worker and beat processes. The integration sends no
personal data: `send_default_pii=False`, no request bodies, no cookies, no IP addresses
(CES §1.4). The environment comes from `RAILWAY_ENVIRONMENT_NAME` and the release from the Git
commit. Performance tracing is off unless `SENTRY_TRACES_SAMPLE_RATE` is set.

## Applying the configuration

From the repository root, with the Railway CLI 5.42.1 or newer:

```bash
railway login
railway init  # or `railway link` to an existing project
cd .railway && npm ci && cd ..
railway config plan     # read the diff; nothing changes
# set the shared variables listed above in the dashboard
railway config apply    # creates services, databases and buckets
```

Then:

1. **web → Settings → Networking → Generate Domain** (or add the custom domain and its DNS
   records), then set `SITE_URL` (and `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` for a custom domain).
2. Check the PostgreSQL major version (`railway connect postgres`, then `SHOW server_version;`)
   and set `PG_MAJOR` on `backup` to match.
3. Enable volume backups on `postgres`.
4. Deploy, then verify:
   * `curl https://<domain>/ready/` returns `{"status": "ok", ...}`;
   * `railway ssh --service web -- python manage.py verify_storage`;
   * `railway ssh --service worker -- python manage.py sendtestemail <you>`;
   * the `beat` logs show `Scheduler lock acquired`;
   * trigger `backup` once from the dashboard and check that its log shows `pgbackup: wrote s3://…`.
5. Create the first administrator (`railway ssh --service web -- python manage.py createsuperuser`)
   and enrol MFA at first sign-in. **Do not run `seed_demo` in production.**

## What is still needed before the first deploy

These need a person with the relevant accounts. The repository can do nothing more about them.

| # | Blocker | Who |
|---|---|---|
| 1 | A Railway account and project, with the GitHub app allowed to read `swastikongithub/Django-EduRev-P20`; a plan that fits four services, two databases and two buckets | Project owner |
| 2 | The shared variables above, in particular a fresh `DJANGO_SECRET_KEY` | Project owner |
| 3 | An email provider account (for example Resend) with a **verified sender domain**, its API key, and `DEFAULT_FROM_EMAIL` on that domain. SMTP only on Railway Pro | Project owner / university IT |
| 4 | The public domain: either the generated `*.up.railway.app` or a university subdomain with DNS records | University IT |
| 5 | `PG_MAJOR` matching the provisioned PostgreSQL major version | Whoever applies the config |
| 6 | An age key pair for backups: the public key goes in `BACKUP_AGE_RECIPIENT`, and the private key stays offline with two custodians | Project owner |
| 7 | Optional: a Sentry project (DSN) and an external uptime monitor on `/health/` | Project owner |

`railway config plan` has not been run against a real project, because there is no account
yet. The IaC file is checked against the SDK's types on every CI run, and its evaluated graph
has been inspected. The first `plan` is the remaining check.
