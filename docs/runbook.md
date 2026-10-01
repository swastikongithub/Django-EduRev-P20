# Operations runbook

Deployment, rollback, backup and restore, secret rotation, monitoring and incident playbooks
for LPU Reserve. Environment variables are described in [environment.md](environment.md).

> Status: there is no deployed staging or production environment yet. The CI `deploy` job is a
> placeholder. The procedures below are written for the shipped `Dockerfile` and
> `docker-compose.yml` and for a generic container platform (Render, Railway or similar).
> The backup and restore procedure was exercised against the development database on
> 2026-10-01 (see [Tested restore](#tested-restore-procedure)).

## Topology

| Process | Command | Instances | Notes |
|---|---|---|---|
| web | `gunicorn config.wsgi:application` (image default `CMD`) | 1..n | Liveness `/health/`, readiness `/ready/`; static files served by WhiteNoise |
| worker | `celery -A config worker -l info --concurrency N` | 1..n | Runs sweeps and notification email |
| beat | `celery -A config beat -l info --schedule /var/lib/celery/celerybeat-schedule` | **exactly 1** | Never scale; a second Beat doubles every scheduled sweep |
| PostgreSQL 16 | managed service | 1 primary | `max_connections` must cover web workers + Celery + headroom |
| Redis 7 | managed service | 1 | Django cache (db 0) and Celery broker (db 1); no persistence required |

All three application processes use the same image. Only one process per release runs
migrations (`RUN_MIGRATIONS=1`).

Connection budget: each gunicorn worker and each Celery worker process holds up to one
persistent connection (`DB_CONN_MAX_AGE=60`). With 2 web containers x 3 workers + 2 Celery
processes + Beat, plan for about 15 connections plus admin sessions.

## Deployment

### Local or single-host (docker compose)

```bash
docker compose up --build -d                      # db, redis, web (migrates), worker, beat
docker compose --profile demo run --rm seed       # optional demo data; never in production
docker compose ps                                 # web should be "healthy"
curl -fsS http://localhost:8000/ready/            # {"status": "ok", "checks": {...}}
docker compose logs -f web worker beat
```

Compose defaults (`DEMO_MODE=1`, a public placeholder secret key and database password) are for
development only. Override them through the shell environment or an untracked `.env` for any
shared host.

### Container platform release checklist

1. **CI is green on `main`**: lint; Django, deployment and migration checks; OpenAPI drift;
   tests on PostgreSQL 16 (including the 500-way concurrency proof); Playwright journeys and
   axe; pip-audit; gitleaks; the Docker build with its production smoke test; the OWASP ZAP
   baseline ([ci.md](ci.md)). To repeat the smoke test against a candidate image by hand:
   `IMAGE=lpu-reserve:<sha> scripts/ci/stack.sh up && scripts/ci/smoke.sh && scripts/ci/stack.sh down`.
2. **Build and tag** the image with the commit SHA (`lpu-reserve:<sha>`). Static files are
   collected at build time.
3. **Back up** the database ([Backup](#backup)) and note the current image tag and the latest
   applied migration per app:
   ```bash
   python manage.py showmigrations --list | grep -B1 "\[ \]" || true   # anything unapplied?
   python manage.py showmigrations > pre-release-migrations.txt
   ```
4. **Review the migration plan** with the new image:
   ```bash
   docker run --rm --env-file prod.env lpu-reserve:<sha> python manage.py migrate --plan
   ```
5. **Check deployment settings** with the production environment:
   ```bash
   docker run --rm --env-file prod.env lpu-reserve:<sha> python manage.py check --deploy
   ```
   Expect "no issues (1 silenced)": `security.W021` (HSTS preload) is silenced while
   `SECURE_HSTS_PRELOAD` is off. A weak or default secret key does not get this far: start-up
   refuses it with `ImproperlyConfigured`.
6. **Migrate once**: either a one-off job
   (`docker run --rm --env-file prod.env lpu-reserve:<sha> python manage.py migrate --noinput`)
   or exactly one web instance with `RUN_MIGRATIONS=1`. Do not set it on every replica;
   concurrent `migrate` runs can collide.
7. **Roll out web**, then **worker**, then restart the single **beat**. The entrypoint waits up
   to `DB_WAIT_TIMEOUT` seconds for PostgreSQL.
8. **Probes**: liveness `GET /health/` (never touches the database), readiness `GET /ready/`
   (database `SELECT 1` and Redis `PING`; 503 if either fails). Configure the platform health
   check on `/health/` and traffic gating on `/ready/`.
9. **Smoke test**:
   - `/ready/` returns 200.
   - Sign in as an administrator (MFA prompt appears).
   - `/manage/ops/`: database and Redis "ok", Celery mode shows a broker, every sweep has a
     recent run and none is flagged stalled (allow five minutes after Beat starts).
   - Book and cancel a test slot on a test resource; confirm the notification arrives.

### Things not to do

- Do not run `celery beat` in more than one container, or inside the web container.
- Do not set `DEMO_MODE=1`, `MFA_ENFORCED=0` or `CELERY_TASK_ALWAYS_EAGER=1` in production.
- Do not use `manage.py run_sweeps --loop` as the production scheduler; it is for setups
  without a broker.
- Do not give the application database role ownership of `audit_auditlog` in production if it
  can be avoided; the owner can drop the append-only trigger.

## Rollback

### Image rollback (no schema change in the release)

Redeploy the previous image tag for web, worker and beat. No database action needed.

### Release that included migrations

All migrations in the repository are reversible: data migrations have reverse functions,
`RunSQL` steps have reverse SQL, and a full `migrate <app> zero` then forward run was verified
on 2026-10-01. To roll back:

1. Stop beat and workers (they may run code that expects the new schema).
2. **Using the new image** (the old image does not contain the newer migration files), migrate
   each changed app back to the migration recorded in `pre-release-migrations.txt`:
   ```bash
   docker run --rm --env-file prod.env lpu-reserve:<new-sha> python manage.py migrate <app> <previous_migration_name>
   ```
3. Redeploy the previous image tag for web, worker and beat.
4. Verify with `/ready/`, the ops page and the smoke test.

If a reverse migration would drop columns or tables holding data written since the release,
prefer restoring the pre-release backup into a new database and switching `DATABASE_URL`
([Restore](#restore)), accepting the loss of writes since the backup, or rolling forward with a
fix. Decide with the product owner; bookings made after the release are real commitments.

Migration-writing rule for future releases (expand, then contract): add new columns as nullable
or with defaults first, deploy code that writes both, and only drop old columns in a later
release. Then image rollback alone is always safe.

## Backup

### What to back up

| Data | Where | How |
|---|---|---|
| PostgreSQL database (all application data, including the audit log) | managed PostgreSQL or the compose `pgdata` volume | `pg_dump -Fc` daily, plus platform point-in-time recovery if offered |
| Uploaded resource photos | `MEDIA_ROOT` (compose volume `media`) | Archive the directory daily |
| Redis | compose `redis` service | Not backed up. It holds cache entries and queued tasks only; persistence is off by design |
| Beat schedule file | compose volume `beat-schedule` | Not needed; Beat recreates it |

### Schedule and retention

- Daily at 02:00 IST, after the 01:15 utilisation snapshot.
- Keep 7 daily, 4 weekly and 12 monthly copies, encrypted, in a different account or region
  from the database.
- Run the [tested restore](#tested-restore-procedure) monthly and after every PostgreSQL
  major-version change. CES §1.3 requires a documented, tested restore.

Automating the schedule depends on the hosting platform and is not yet configured
([known issues](known-issues.md#operations)).

### Commands

Docker compose host:

```bash
STAMP=$(date +%Y%m%d-%H%M)
docker compose exec -T db pg_dump -U edurev -d edurev -Fc > "backups/edurev-$STAMP.dump"
docker compose run --rm --no-deps -v "$PWD/backups:/backup" --entrypoint sh web \
  -c "tar czf /backup/media-$STAMP.tgz -C /app .media"
```

Managed PostgreSQL (from any host with PostgreSQL 16+ client tools):

```bash
pg_dump "$DATABASE_URL" -Fc -f "edurev-$(date +%Y%m%d-%H%M).dump"
pg_restore -l edurev-*.dump | head        # sanity check: the archive lists its contents
```

## Restore

Always restore into a **new, empty** database, verify it, then point the application at it.
Never restore over the live database.

```bash
# 1. Create the target (managed: through the provider's console; compose shown here)
docker compose exec -T db createdb -U edurev edurev_restore

# 2. Restore. --no-owner lets a different role own the objects; extensions are recreated from the dump.
docker compose exec -T db pg_restore -U edurev -d edurev_restore --no-owner --exit-on-error < backups/edurev-<stamp>.dump

# 3. Verify (next section), then stop web, worker and beat
# 4. Point DATABASE_URL at edurev_restore (or rename databases) and start web, worker, beat
# 5. Restore media if needed
docker compose run --rm --no-deps -v "$PWD/backups:/backup" --entrypoint sh web \
  -c "tar xzf /backup/media-<stamp>.tgz -C /app"
```

The restoring role must be allowed to `CREATE EXTENSION btree_gist` and `pg_trgm` (both are
trusted extensions in PostgreSQL 13+, so a database owner can create them). The audit trigger
does not interfere with restore: it fires on `UPDATE` and `DELETE`, not `INSERT` or `COPY`.

After switching, run `analytics.build_snapshots` for any day whose snapshot is missing, and
expect sweeps to catch up on overdue releases and expiries within a few minutes.

## Tested restore procedure

Run against a scratch database. Every step below was executed on 2026-10-01 against the
seeded development database (PostgreSQL 18 client and server; the procedure is identical on
16): the dump took under a second (about 1 MB, 48 data sections), the restore about one second,
and every check passed.

1. Take a dump of the source: `pg_dump "$SOURCE_URL" -Fc -f check.dump`.
2. Create and restore a scratch database: `createdb edurev_restore_check`, then
   `pg_restore -d edurev_restore_check --no-owner --exit-on-error check.dump`.
3. Compare row counts between source and restore (they must match exactly):
   ```sql
   SELECT 'bookings', count(*) FROM bookings_booking UNION ALL
   SELECT 'slots', count(*) FROM bookings_bookingslot UNION ALL
   SELECT 'users', count(*) FROM accounts_user UNION ALL
   SELECT 'resources', count(*) FROM catalogue_resource UNION ALL
   SELECT 'audit', count(*) FROM audit_auditlog UNION ALL
   SELECT 'migrations', count(*) FROM django_migrations;
   ```
4. Confirm the guarantees came back with the data:
   ```sql
   SELECT string_agg(extname, ',' ORDER BY extname) FROM pg_extension;
   -- expect: btree_gist,pg_trgm,plpgsql
   SELECT string_agg(conname, ',' ORDER BY conname) FROM pg_constraint WHERE contype = 'x';
   -- expect: booking_no_overlap,slot_no_overlap
   SELECT tgname FROM pg_trigger WHERE tgrelid = 'audit_auditlog'::regclass AND NOT tgisinternal;
   -- expect: audit_auditlog_no_update
   SELECT count(*) FROM bookings_booking a JOIN bookings_booking b
     ON a.resource_id = b.resource_id AND a.id < b.id AND a.period && b.period
    WHERE a.status IN ('pending','approved','checked_in') AND b.status IN ('pending','approved','checked_in');
   -- expect: 0
   BEGIN; UPDATE audit_auditlog SET action = 'tamper' WHERE id = (SELECT min(id) FROM audit_auditlog); ROLLBACK;
   -- expect: ERROR: audit_auditlog is append-only (UPDATE rejected)
   ```
5. Confirm Django agrees the schema is current:
   ```bash
   DATABASE_URL=postgres://.../edurev_restore_check python manage.py migrate --check   # exit code 0
   DATABASE_URL=postgres://.../edurev_restore_check python manage.py check             # no issues
   ```
6. Record the date, the dump file, the counts and the results in the operations log, then
   `dropdb edurev_restore_check`.

## Secret rotation

| Secret | Procedure | Side effects |
|---|---|---|
| `DJANGO_SECRET_KEY` | Generate 50+ random characters; update the secret for web, worker and beat; redeploy all three | Every session ends (everyone signs in again); password-reset links in flight stop working. **Stored TOTP secrets become undecryptable**: users with MFA cannot complete sign-in until re-enrolled. Before or immediately after the switch, clear enrolment so they enrol again at next sign-in: `UPDATE accounts_user SET mfa_enabled = false, mfa_secret = '' WHERE mfa_enabled;` and tell the affected staff. Booking QR tokens, calendar feed tokens and door QR codes are database values and are not affected |
| Database password | Create the new password on the server, update `DATABASE_URL` everywhere, redeploy, then revoke the old one | Brief reconnects |
| Redis password / URL | Update `REDIS_URL` and `CELERY_BROKER_URL`, redeploy web, worker and beat together | Cached rate-limit counters and Insights cache reset; queued emails in the old broker are lost |
| A person's calendar feed link (leaked) | `UPDATE accounts_user SET calendar_token = gen_random_uuid() WHERE username = '<username>';` | Their old subscription URL stops working; they copy the new link from their profile |
| An administrator's MFA device (lost) | Verify identity out of band, then `UPDATE accounts_user SET mfa_enabled = false, mfa_secret = '' WHERE username = '<username>';` | They enrol a new device at next sign-in. There are no recovery codes yet |

Every manual SQL change to `accounts_user` should be noted in the operations log; it does not
appear in the application audit log.

## Monitoring

| Signal | Where | Alert when |
|---|---|---|
| Readiness | `GET /ready/` | non-200 for 2 minutes |
| Liveness | `GET /health/` (also the Docker `HEALTHCHECK`) | non-200 |
| Background sweeps | `/manage/ops/` (facility manager or administrator): last run, rows affected, failures today, stalled flag when the last run is older than 3x its interval | any sweep stalled, or a failed run |
| Sweeps from SQL | `SELECT task, max(started_at), bool_and(ok) FROM core_sweeprun WHERE started_at > now() - interval '15 minutes' GROUP BY task;` | `checkins.sweep_no_shows` or `notifications.send_checkin_nudges` missing for over 3 minutes |
| Logs | stdout JSON (`LOG_JSON=1`); logger `sweeps` logs every sweep failure with a traceback | `ERROR` lines, gunicorn 5xx in access logs |
| Unsent email | `SELECT count(*) FROM notifications_notification n JOIN accounts_user u ON u.id = n.user_id WHERE n.emailed_at IS NULL AND u.email <> '' AND n.created_at < now() - interval '15 minutes' AND n.kind <> 'checkin_open';` | growing steadily |
| Database | provider metrics | connections near `max_connections`, replication lag, disk |

Error tracking (Sentry) and an external uptime monitor are not configured yet
([known issues](known-issues.md#operations)).

## Incident playbooks

### Redis is down

What happens (verified against the code and by reproducing a dead broker and cache):

| Area | Effect |
|---|---|
| Booking correctness | **Unaffected.** Overlaps are refused by PostgreSQL; no booking path reads Redis for correctness |
| Signed-in users browsing, checking in, checking out | Work |
| Creating, approving or cancelling a booking in the web UI | The change **commits**, then the request fails with a server error after a few seconds, because queuing the notification email to the broker raises after commit. The booking (or decision) is saved; the user sees an error page. Affects users with an email address |
| Password sign-in, MFA and demo sign-in (POST) | Server error: the rate limiter uses the Redis cache |
| REST API (`/api/v1/...`) | Server error on every request: DRF throttling uses the Redis cache |
| Insights dashboard | Server error: report caching uses the Redis cache |
| `/ready/` | 503 (`redis: error`) so load balancers may stop routing to web |
| Background sweeps | Stop: no auto-release, no expiry, no reminders, no nightly snapshot |

Response:

1. Restore Redis (restart the service; it needs no data).
2. If Redis will be down for long, run degraded mode: restart web with `REDIS_URL=` (empty,
   per-process cache) and `CELERY_TASK_ALWAYS_EAGER=1` (email sent inline; use a reliable SMTP
   relay, since a mail failure would then surface as an error after commit), and run one
   temporary `python manage.py run_sweeps --loop` process so auto-release continues. Stop the
   Celery worker and beat meanwhile. Note that readiness will report Redis as off.
3. When Redis is back, restore the original variables, restart web, start worker and beat, and
   check `/manage/ops/` shows sweeps catching up.
4. Tell users who saw an error while booking to check "Bookings": their booking was most
   likely made.

### Auto-release has stalled

Symptoms: `/manage/ops/` flags "Release no-shows" as stalled; confirmed bookings past their
check-in deadline still show as confirmed on the board.

1. Check Beat is running and there is exactly one: `docker compose ps beat` or the platform's
   process list.
2. Check a worker is running and connected: `docker compose logs --tail 100 worker`.
3. Look at the latest `SweepRun` rows: a failed run stores the exception in `detail`:
   `SELECT started_at, ok, affected, detail FROM core_sweeprun WHERE task = 'checkins.sweep_no_shows' ORDER BY started_at DESC LIMIT 5;`
4. Release overdue bookings now: press **Run now** next to "Release no-shows" on `/manage/ops/`
   (runs in the web process, audited), or
   `python manage.py shell -c "from apps.checkins.tasks import sweep_no_shows; print(sweep_no_shows.apply().result)"`.
5. Fix the cause (restart Beat or the worker, restore Redis, fix the failing code) and confirm a
   new successful run appears every minute.

Catching up is safe: the sweep releases every booking whose deadline has passed, records the
no-show at the time of the sweep, and applies the restriction ladder once per no-show. If a
stall made the release unfair (for example the student checked in through a custodian who
could not record it), forgive the no-show from `/manage/no-shows/`.

### Timetable publish failed

Symptoms: the console shows "Some class times clash with maintenance or a booking made seconds
ago. Nothing was published", or the P13 push returns 422 with code `invalid_rows` or `conflict`.

1. Nothing changed: publishing is all-or-nothing, the previous published version stays live and
   the draft remains a draft. Confirm:
   `SELECT version, status, published_at FROM timetable_timetablepublication WHERE term_id = <id> ORDER BY version;`
   (at most one row is `published`, enforced by `one_published_timetable_per_term`).
2. `invalid_rows` (unknown room code, unreadable time, two classes in one room at once): fix
   the CSV or the P13 payload; the console lists each bad row with its line number.
3. `conflict` with maintenance: a class occurrence overlaps a scheduled maintenance window
   (classes are never displaced automatically). Find it:
   ```sql
   SELECT w.id, r.code, w.title, w.period FROM maintenance_maintenancewindow w
   JOIN catalogue_resource r ON r.id = w.resource_id
   WHERE w.status IN ('scheduled','in_progress') AND upper(w.period) > now()
   ORDER BY lower(w.period);
   ```
   Move, shorten or cancel the window on `/manage/maintenance/`, or change the class, then
   publish the draft again.
4. `conflict` from a booking made seconds ago: publish again; the retry displaces it.
5. If publishing keeps failing for a reason not listed, keep the old version live and capture
   the error from the logs; the `detail.db` field in the API response carries the database
   message.

### Database unavailable

`/ready/` returns 503 and the load balancer stops routing; `/health/` stays 200 so containers
are not restarted in a loop. Restore the database (provider status, failover, or
[Restore](#restore)). Sweeps resume and catch up on their own.

### Suspected double booking

Run the overlap query from the [tested restore](#tested-restore-procedure) step 4 against
production. It must return 0; the exclusion constraints make any other result impossible
unless they were dropped. Check they exist with the `pg_constraint` query. If a user reports a
clash in the room, it is usually a booking versus an untimetabled class or an event booked
outside the system: check the resource's calendar and the audit log for that booking.

### Account locked out

After 5 failed attempts (wrong passwords and wrong or replayed TOTP codes count together) an
account is locked for 15 minutes and unlocks by itself. The sign-in page deliberately answers
"don't match" rather than saying the account is locked, so a person who is sure of their
password is probably locked. For a lost authenticator, see
[guide-admin.md](guide-admin.md#mfa-and-locked-accounts). To unlock sooner: `UPDATE accounts_user SET failed_logins = 0, locked_until = NULL WHERE username = '<username>';`
