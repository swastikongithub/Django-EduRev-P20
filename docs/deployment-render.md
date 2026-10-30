# Demo deployment on free hosting (Render, Neon, Upstash)

The live demo at <https://django-edurev-p20.onrender.com> runs the same Docker image as every other
deployment, on free tiers only. It replaced the Railway deployment
([deployment-railway.md](deployment-railway.md)) when that trial ended; the Railway project and its
volumes are kept, paused. This page records how the demo is configured, how its data was restored,
and what a free single-instance setup does not do.

| Part | Service | Plan |
|---|---|---|
| Web (gunicorn, one worker) | Render web service `Django-EduRev-P20`, Docker runtime, Oregon | Free: 0.1 CPU, 512 MB, sleeps when idle |
| PostgreSQL 18 | Neon, **direct** endpoint (not the `-pooler` one), `sslmode=require` | Free |
| Redis (Django cache: sign-in and API rate limits, Insights) | Upstash, `rediss://` (TLS) | Free |

## Render service settings

| Setting | Value |
|---|---|
| Repository, branch, root | `swastikongithub/Django-EduRev-P20`, `main`, repository root |
| Dockerfile, command | the repository `Dockerfile` and its `CMD`, unchanged |
| Health check path | `/health/` |
| Auto-deploy | After CI checks pass |
| Pre-deploy command | none (not available on the free plan); `RUN_MIGRATIONS=1` makes the entrypoint migrate before gunicorn starts |

## Environment

Secrets live only in Render's environment settings. Everything else:

| Variable | Value | Why |
|---|---|---|
| `DJANGO_SECRET_KEY` | the original production key, unchanged | It signs sessions and derives the key that encrypts stored TOTP secrets ([environment.md](environment.md#core)); a new key would make every MFA enrolment unreadable |
| `DATABASE_URL` | Neon direct connection string | Django keeps one persistent connection per worker (`DB_CONN_MAX_AGE=60`); a transaction pooler would need server-side cursors disabled, which this settings module does not expose |
| `REDIS_URL` | Upstash `rediss://` URL | TLS is taken from the scheme |
| `CELERY_TASK_ALWAYS_EAGER`, `CELERY_BROKER_URL` | `1`, `memory://` | No worker exists, so notification email (the only task requests enqueue) runs in the request after commit; with the console email backend it cannot fail |
| `DEBUG`, `DEMO_MODE`, `MFA_ENFORCED` | `0`, `0`, `1` | |
| `MFA_REQUIRED_ROLES` | `faculty,staff,custodian,dept_head,facility_manager,admin` | Set explicitly, so the deployed policy does not depend on the code default: every role except `student` |
| `ALLOWED_HOSTS` | `django-edurev-p20.onrender.com` | |
| `CSRF_TRUSTED_ORIGINS`, `SITE_URL` | `https://django-edurev-p20.onrender.com` | |
| `SECURE_SSL_REDIRECT`, `TRUSTED_PROXY_HOPS` | `1`, `1` | |
| `RUN_MIGRATIONS`, `WEB_CONCURRENCY` | `1`, `1` | One gunicorn worker fits the 512 MB instance |
| `DB_CONN_MAX_AGE`, `DB_WAIT_TIMEOUT` | `60`, `90` | Neon suspends an idle database; the entrypoint waits for it to wake |
| `LOG_JSON`, `LOG_LEVEL` | `1`, `INFO` | |

`PORT` is set by Render. `USE_S3` and an email backend are not set, so `check --deploy` reports
`lpu.E001` and `lpu.E002`; the entrypoint does not run it, and both are listed below.

## How the data was restored (2026-10-30)

No dump of the Railway database after the 2026-10-03 import exists, and the paused database cannot
be read without a paid plan. Production had been built in two steps, so it was rebuilt the same way:

1. `migrate` on the empty Neon database.
2. `loaddata` of the verified pre-import production dump (`prod-dumpdata-20261003T091220Z-pre-import`):
   the `swastik` superuser with its encrypted MFA secret, `Demo1`, groups, the institution, the audit
   trail.
3. `import_state` of a bundle exported from the same local source database as on 2026-10-03
   ([state-transfer.md](state-transfer.md)), unchanged since then. Each imported account was given
   the password already issued to it in the private credentials file, so published demo
   credentials still work.

Result, checked against the production baseline: 157 accounts, 61 resources, 3,440 bookings, 6,140
booking slots, 346 timetable entries; every foreign key valid; all 155 issued passwords verify; the
`swastik` MFA secret decrypts under the deployed key; `state_inventory` availability digests equal
the source's. Anything done on Railway after 2026-10-03 was not recoverable.

## What does not run here

| Feature | State |
|---|---|
| Celery Beat sweeps: no-show release and the restriction ladder, completing finished bookings, approval expiry, reminders, check-in nudges, maintenance window transitions, lifting expired restrictions, nightly Insights snapshots | Not automatic. A facility manager or administrator can run each one from **Operations → Run now** |
| Email | Not configured (console backend). In-app notifications work |
| Photo uploads | Written to the container disk and lost at the next restart or deploy. The 61 catalogue photos are built into the image and unaffected |
| Backups | None automated. Neon keeps its own short point-in-time history on the free plan |
| Always on | The instance sleeps after about 15 minutes without traffic; the next request waits roughly a minute for it to start |
| Load | The 500-attempt concurrency proof and the load test ([load-test-report.md](load-test-report.md)) are engineering results from a production-like stack, not a statement about this 0.1-CPU instance; do not load-test it |

## Before a presentation

Open the site a few minutes beforehand so the instance and the database are awake, then sign in
once. `/ready/` returns 200 when PostgreSQL and Redis both answer.
