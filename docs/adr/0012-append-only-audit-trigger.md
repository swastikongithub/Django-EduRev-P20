# 0012. Append-only audit log enforced by a database trigger

- Status: accepted
- Related: CES §1.4 ("immutable audit log for every privileged action: actor, action, target, before and after, timestamp, IP"); DPDP Act 2023

## Context

An audit log that application code can edit is not evidence. The application role owns the
table, so Django permissions alone cannot stop an `UPDATE` or `DELETE`. At the same time, DPDP
erasure of a person must not be blocked by audit rows that reference them.

## Decision

- `audit.AuditLog` stores actor (nullable FK) and `actor_label`, `action`, `target_type`,
  `target_id`, `target_label`, `before`, `after` (JSON), `ip` and `created_at`.
  `audit.services.record()` is the only writer and is called by every privileged service
  (bookings, approvals, check-ins, maintenance, rules, workflows, timetable, users, ops,
  sign-in, data export).
- Migration `audit.0002` installs `audit_log_is_append_only()` and a `BEFORE UPDATE OR
  DELETE` row trigger that raises `insufficient_privilege`.
- Migration `audit.0003` permits exactly one update: setting `actor_id` to NULL when nothing
  else in the row changes (the `ON DELETE SET NULL` cascade when a user is deleted). The name
  survives in `actor_label`. It also drops the `TRUNCATE` trigger so the test runner can reset
  tables; in production the application role must not own the table, so it cannot truncate.
- `record()` writes in its own savepoint and logs (does not raise) on failure, so an audit
  write problem never aborts the business action it describes.

## Consequences

- Raw SQL and ORM updates and deletes are refused (`tests/test_audit.py`).
- Deleting a user keeps their audit rows with the actor detached
  (`test_deleting_a_user_with_audit_rows_keeps_the_rows`); smuggling other changes alongside
  the detach is refused (`test_detaching_the_actor_cannot_smuggle_other_changes`).
- Retention cannot be enforced by deleting rows through the application; archival would be a
  DBA operation (disable trigger, export, delete, re-enable) and should itself be recorded.
- Because `record()` swallows its own failures, a broken audit write is visible only in logs.
- `pg_restore` works normally (the trigger does not fire on `INSERT` or `COPY`).
- `ip` is taken from the first `X-Forwarded-For` entry when present; behind a proxy that does
  not overwrite the header, it can be spoofed (see [known issues](../known-issues.md)).

## Alternatives considered

- **Revoke UPDATE/DELETE from the application role.** Equally effective in production, but
  depends on deployment discipline and is not exercised by tests; the trigger travels with the
  migrations.
- **Hash-chained rows.** Detects tampering after the fact rather than preventing it; could be
  added later for tamper evidence against a DBA.
- **External log service.** Stronger separation of duties, but another system to run.
