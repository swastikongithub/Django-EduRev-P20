# 0006. Celery Beat sweeps recorded as SweepRun rows

- Status: accepted
- Related: CES §1.1 ("Celery Beat, never a cron calling manage.py inside the web container"); P20 §7, §8, §11

## Context

Several behaviours are time-driven: releasing bookings nobody checked into after the grace
period, completing finished sessions, expiring approval requests at their start time,
reminders and check-in nudges, maintenance window transitions and nightly analytics. They must
run on time, survive restarts, tolerate overlap (a slow run while the next one starts), and be
visible to operators, who otherwise cannot tell "nothing to release" from "the job is dead".

## Decision

- Celery Beat schedules eight sweeps (`CELERY_BEAT_SCHEDULE` in `config/settings.py`);
  workers execute them. Redis is the broker; no result backend.
- Each task body calls `core.sweeps.run_sweep(name, fn)`, which creates a `SweepRun` row,
  runs the service function, and records `finished_at`, `affected` and `ok` (with the error
  `repr` on failure).
- Sweeps that mutate bookings lock with `select_for_update(skip_locked=True)`, so concurrent
  runs split the work instead of blocking or double-processing. Service functions take `now=`
  and are idempotent.
- `/manage/ops/` (facility managers and administrators) shows readiness checks, the Celery
  mode, each sweep's last run, a stalled flag when the last run is older than three times its
  interval, recent runs, and a "Run now" button that executes the sweep synchronously in the
  web process (audited as `ops.run_sweep`).
- Exactly one Beat process per deployment. Workers run with `acks_late` and prefetch 1.
- For setups without a broker, `manage.py run_sweeps [--loop]` runs the same schedule
  in-process. It is a development and demo tool, not a production scheduler.

## Consequences

- Auto-release correctness is testable at the boundary minute
  (`tests/test_checkins.py::test_sweep_releases_exactly_after_the_grace_period`,
  `test_checkin_at_the_deadline_beats_the_sweep`).
- Operators can see and trigger background work without shell access
  (`tests/test_console_setup.py::test_ops_run_now_releases_overdue_booking`).
- `SweepRun` grows by about 4,000 rows a day at the current schedule (two sweeps run every
  minute); it is not pruned yet ([known issues](../known-issues.md)).
- A second Beat instance would double-schedule; the sweeps are safe under that, but
  reminders rely on `reminder_sent_at` stamps rather than a scheduler lock.
- Auto-release depends on the worker and Beat being up. If they are down, bookings are not
  released, but nothing becomes inconsistent; the next run catches up.

## Alternatives considered

- **cron calling `manage.py` in the web container.** Forbidden by CES and invisible to operators.
- **django-q or APScheduler in-process.** Rejected: CES names Celery for Track P; in-process
  schedulers multiply with web replicas.
- **Per-booking delayed tasks (`apply_async(eta=...)`).** Rejected: thousands of pending
  tasks in the broker, lost on broker flush, and hard to reconcile after edits or
  cancellations. A sweep re-reads the truth from the database each minute.
