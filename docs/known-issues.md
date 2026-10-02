# Known issues and technical debt

The register CES §1.6 asks for: what is missing, deliberately deferred, or known to be weak,
with its impact and the planned fix. Security findings from the review are all closed
([security-review.md](security-review.md)); what remains here is gaps, not open
vulnerabilities. Each entry says where it is tracked: a roadmap **phase** or **backlog**.

Severity: **High** blocks a production go-live, **Medium** should be fixed before or soon after
go-live, **Low** is debt or polish.

## Operations

| # | Issue | Impact | Severity | Plan |
|---|---|---|---|---|
| OPS-1 | Production runs on Railway (web, worker, PostgreSQL, Redis and the media bucket), but Celery Beat and the backup service are not created: the Trial plan refuses more services. Email is not configured, and Railway's GitHub App is not authorized, so deploys are manual ([current deployment](deployment-railway.md#current-production-deployment)) | Scheduled sweeps (no-show release, reminders, approval expiry, nightly analytics) do not run; no automated backups; no email | High | Upgrade the Railway plan, then add Beat and backups; configure an email provider; authorize the Railway GitHub App |
| OPS-3 | Sentry is wired (`SENTRY_DSN`, no personal data) but has no DSN yet; there is no external uptime monitor, and Railway's health check runs only during deploys | Exceptions are only in logs until a DSN is set; an outage between deploys is noticed by users | Medium | Create a Sentry project; add an uptime monitor on `/health/` once deployed |
| OPS-4 | With `REDIS_URL` set, Redis backs the Django cache (sign-in and API rate limits, Insights cache) and the Celery broker. A Redis outage degrades sign-in rate limiting, the API throttle, Insights and email delivery. **Booking correctness never depends on it** | Degraded, not incorrect, behaviour during a Redis outage; the [runbook playbook](runbook.md#redis-is-down) covers it | Medium | Accepted by design ([ADR 0001](adr/0001-track-p-django-postgresql.md)); monitor Redis in Phase 6 |
| OPS-6 | `SweepRun` (about 4,000 rows a day), `BookingAttempt` and `Notification` are never pruned | Slow table growth; no functional impact for years | Low | Backlog: a monthly pruning sweep with a configurable horizon |
| OPS-8 | The 500-user scenario has been run only against a production-like stack on a single 4-core machine ([load-test-report.md](load-test-report.md)); no measurement exists against a deployed environment | CES §1.5 asks for a report at M4 against the concurrency targets; the CES user and latency targets are unverified | Medium | Phase 6, once staging exists |
| OPS-10 | The OWASP ZAP baseline is passive and covers public and student pages only; staff console pages, TLS configuration and active (attack) scanning are out of its scope ([ci.md](ci.md#owasp-zap-baseline)) | Staff pages and TLS are verified by other means (tests, `check --deploy`, the platform) rather than by ZAP | Low | Phase 6: TLS scan of the deployed host; backlog: an authenticated staff pass |
| OPS-11 | The Beat schedule file is ephemeral (no volume, so the container stays non-root). After a restart, interval sweeps start on a fresh schedule | None: every sweep is idempotent, and the nightly analytics job rebuilds every missed day, up to 31 | Low | Accepted ([deployment-railway.md](deployment-railway.md#celery-worker-and-exactly-one-beat)) |

## Configuration

| # | Issue | Impact | Severity | Plan |
|---|---|---|---|---|
| CFG-2 | Production logging is JSON to stdout (`LOG_JSON=1`) with no log-retention or shipping configuration | Depends on the platform's log retention | Low | Phase 6: document the platform's retention |

## Files and storage

| # | Issue | Impact | Severity | Plan |
|---|---|---|---|---|
| FS-3 | Uploads are validated (declared type, magic bytes, size and pixel caps, Pillow verify, re-encoded to WebP) but **not malware-scanned** as CES §1.4 requires | Re-encoding removes active content from images, which limits the risk; CSV imports are parsed and discarded, never stored | Low | Backlog: ClamAV scan before re-encode if a scanning service is available |

## Integrations

| # | Issue | Impact | Severity | Plan |
|---|---|---|---|---|
| INT-1 | No university SSO or ERP integration; identities and roles are local Django users | Administrators add people and set roles in the console (**Setup → Users → Add a person**); there is no self-service sign-up | Medium | Backlog: an OIDC/SAML backend mapping ERP role to `User.role`; `accounts.permissions` already derives everything from the role |
| INT-2 | The API uses session authentication only. An unattended client such as the P13 timetable feed must hold a session of a user with `manage_timetable` | No clean machine-to-machine credential | Medium | Backlog: scoped API tokens for integrations ([ADR 0005](adr/0005-server-rendered-htmx-with-drf-api.md)) |
| INT-3 | Calendar export is one-way: per-booking `.ics` and a private subscription feed; no Google/Outlook API push | Calendars refresh at the subscriber's polling interval | Low | Accepted for v1 |
| INT-4 | No SMS channel; notifications are in-app and email | §11 notifications arrive by email and in-app only | Low | Backlog |
| INT-5 | No door-access or IoT occupancy integration (optional v2 in the P20 brief) | Check-in is by QR only | Low | v2 |

## Tenancy

The schema carries an institution on every record ([ADR 0011](adr/0011-tenancy-via-institution-fk.md)),
but only one tenant (LPU) is served. A second tenant would expose:

| # | Issue | Severity | Plan |
|---|---|---|---|
| TEN-1 | Isolation depends on every query filtering by institution; there is no PostgreSQL row-level security | Medium (only with a second tenant) | Backlog: RLS policies keyed on a session variable |
| TEN-2 | Background sweeps run across all institutions and `SweepRun` is global | Low | Backlog |
| TEN-3 | `User.username` is unique globally, not per institution | Low | Backlog |
| TEN-4 | There is no UI to create institutions; onboarding a tenant is a data task | Low | Backlog |

## Security and privacy

| # | Issue | Impact | Severity | Plan |
|---|---|---|---|---|
| SEC-R1 | No MFA recovery codes. A person who loses their authenticator needs an administrator to clear enrolment in the database (`mfa_enabled = false, mfa_secret = ''`), after which they enrol again at next sign-in | Support burden; documented in [guide-admin.md](guide-admin.md#mfa-and-locked-accounts) | Medium | Backlog: single-use recovery codes and a console reset action |
| SEC-R3 | DPDP Act 2023: data-subject *access* is self-service (`/me/export/`); there is no self-service *deletion* endpoint | Deletion requests are handled by an administrator (deactivate, then a DBA-run erasure that keeps the audit trail's detached actor) | Medium | Backlog: an erasure request flow with audit |
| SEC-R4 | Field-level encryption covers the TOTP secret only; `vid` and `phone` are stored in plain text (CES §1.4 asks for field-level encryption of identity fields) | Relies on database encryption at rest | Medium | Backlog: encrypted fields for `vid`/`phone`, with a lookup hash for `vid` sign-in |
| SEC-R5 | A request whose only eligible approver is its own requester (for example a custodian booking their own room) waits for a facility manager or administrator, who can decide any step; there is no automatic re-routing | Such requests rely on campus-wide approvers watching the queue | Low | Backlog: route self-requests to the next approver role |
| SEC-R6 | `audit.record()` never raises into business flows; a failed audit write is visible only in logs | A silent gap in the audit trail is possible if the database refuses the insert | Low | Backlog: alert on the `audit write failed` log line |
| SEC-R8 | A privileged account that has not enrolled MFA yet enrols whichever authenticator completes its first password sign-in (trust on first use). Enrolment is audited (`auth.mfa_enrolled`) but nobody is notified | Someone who learns an un-enrolled administrator's password before they first sign in could enrol their own authenticator | Low | Enrol privileged staff at onboarding; backlog: email the person on enrolment |
| SEC-R9 | `/health/` and `/ready/` answer before host validation, the HTTPS redirect and HSTS, and `/ready/` names the failing dependency's exception class | Probes must work for the platform without a Host header or TLS; the class name (for example `OperationalError`) reveals no data | Low | Accepted by design ([ADR 0006](adr/0006-celery-beat-sweeps-with-sweeprun.md) and `apps/core/health.py`) |
| SEC-R10 | `X-Forwarded-Proto: https` is trusted whether or not `TRUSTED_PROXY_HOPS` declares a proxy | A client that reaches gunicorn directly can only make its own request look secure; nobody else is affected. Coupling the two would turn a forgotten `TRUSTED_PROXY_HOPS` into an HTTPS redirect loop | Low | Accepted (Phase 3 re-review); production exposes only the proxy |
| SEC-R11 | On Railway, client addresses come from `X-Real-IP` (`TRUSTED_CLIENT_IP_HEADER`), the header Railway documents and sets at its edge. The app cannot verify that the edge overwrote a client-supplied value | If Railway stopped setting it, rate limits and the audit log would fall back to the edge's address (fail closed: stricter, never spoofable) | Low | Accepted; `tests/test_production_readiness.py` pins the behaviour, including malformed values |

## Data

| # | Issue | Severity | Plan |
|---|---|---|---|
| DATA-1 | Per-entity retention (CES §1.3: seven years for academic records, configurable per entity) is not implemented; bookings and history are kept indefinitely ([database.md](database.md#data-lifecycle)) | Low | Backlog: retention settings plus an archival job |
| DATA-2 | The audit log cannot be pruned through the application (by design, [ADR 0012](adr/0012-append-only-audit-trigger.md)); archival is a recorded DBA operation | Low | Accepted |

## Product and UI

| # | Issue | Severity | Plan |
|---|---|---|---|
| UI-1 | Hindi and Punjabi translations are partial. English is fully supported and is the launch language, and the infrastructure for Hindi and Punjabi (language switcher, locale catalogues, `LocaleMiddleware`) is in place. Only the navigation shell, sign-in, home and the Language section of **Me** are translated (4 of 63 templates); every other screen is English only and its text is not yet marked for translation, so choosing हिन्दी or ਪੰਜਾਬੀ gives a mixed-language interface | Medium | Deferred: English at launch, with no dedicated translation phase planned. Full application-wide translation (marking the remaining templates and Python messages, then reviewed Hindi and Punjabi translations) is backlog work |

## Test debt

| # | Issue | Severity | Plan |
|---|---|---|---|
| TD-1 | `seed_demo` (demo data generator) has no automated test | Low | Backlog: a smoke test that seeds a small campus |
| TD-2 | The thin Celery task wrappers in `apps/maintenance/tasks.py` and `apps/approvals/tasks.py` are not exercised directly (the services they call are) | Low | Backlog |

## Resolved

| # | Was | Resolved in |
|---|---|---|
| OPS-2 | Database backups were not scheduled | Production readiness: nightly age-encrypted `pg_dump` to a private bucket (Railway cron service `backup`), Railway volume backups, and a backup-to-restore drill in CI on every push ([backup-restore.md](backup-restore.md)) |
| OPS-5 | Without `REDIS_URL` rate limits were per worker | Production readiness: the Railway configuration always sets it, and `check --deploy` warns without it (`lpu.W003`) |
| CFG-1 | SMTP settings were not read from the environment | Production readiness: `EMAIL_HOST*`, `EMAIL_USE_TLS/SSL`, `EMAIL_TIMEOUT`, plus HTTPS email APIs through django-anymail (Railway blocks SMTP below Pro); `check --deploy` refuses a non-delivering backend; CI delivers a test message over SMTP |
| FS-1 | Uploaded photos were not served | Production readiness: served from a private bucket through 15-minute pre-signed URLs (and by `runserver` in development); CI round-trips a file through a pre-signed URL |
| FS-2 | `USE_S3=1` failed: missing dependencies | Production readiness: `django-storages[s3]` and `boto3` added; `check --deploy` refuses production without object storage (`lpu.E001`) |
| SEC-R2 | Rotating `DJANGO_SECRET_KEY` made stored TOTP secrets undecryptable, and the sign-in page reported that as a wrong code and counted it towards the lockout (seen locally on 2026-10-01: a new `.env` key locked an enrolled superuser out) | Production readiness: secrets stay readable through `DJANGO_SECRET_KEY_FALLBACKS` and move to the new key at sign-in or with `manage.py mfa_keys --rotate`; an unreadable secret is reported as a server problem, is audited (`auth.mfa_secret_unreadable`) and never counts towards the lockout; weak fallbacks are refused in production (`tests/test_mfa.py`) |
| UI-2 | The brandmark and favicon were placeholders | Production readiness: the official LPU seal supplied by the project owner (`static/img/lpu_logo.png`) and renditions derived from it (`scripts/brand_renditions.py`) in the navigation, sign-in, MFA, error pages, door signs, favicon, touch icon and web manifest ([branding.md](branding.md)) |
| OPS-7 | No OWASP ZAP baseline scan in CI | Phase 3: `zap` job, two passes over a production-like stack, gated by risk ([ci.md](ci.md#owasp-zap-baseline)) |
| OPS-9 | CI did not run on pushes to development branches | Phase 3: the active branch was listed under `on.push`. Production readiness: removed again once Phase 3 merged; pull requests into `main` run every job |
| SEC-R7 | Fonts loaded from Google Fonts (third-party request on every page) | Phase 3: fonts self-hosted under `static/fonts` (SIL OFL 1.1); the CSP names no third-party origin |
| UI-3 | Dead `placeholder` view and template | Phase 3: removed |
