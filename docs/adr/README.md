# Architecture decision records

Each record follows the MADR shape: context, decision, consequences, alternatives considered.
Records are immutable once accepted; a later decision supersedes an earlier one by a new record.

| # | Decision | Status |
|---|---|---|
| [0001](0001-track-p-django-postgresql.md) | Track P: Django 5.2 and PostgreSQL 16 | Accepted |
| [0002](0002-modular-monolith-with-service-layer.md) | Modular monolith, one app per P20 module, logic in `services.py` | Accepted |
| [0003](0003-exclusion-constraints-and-unified-ledger.md) | Exclusion constraints and one `BookingSlot` ledger for bookings, classes and maintenance | Accepted |
| [0004](0004-advisory-lock-and-deadlock-retry.md) | Advisory lock and deadlock retry as a throughput aid, not the correctness mechanism | Accepted |
| [0005](0005-server-rendered-htmx-with-drf-api.md) | Server-rendered templates with htmx (Path P1), DRF API alongside | Accepted |
| [0006](0006-celery-beat-sweeps-with-sweeprun.md) | Celery Beat sweeps recorded as `SweepRun` rows | Accepted |
| [0007](0007-nightly-utilisation-snapshots.md) | Nightly `UtilisationSnapshot` aggregation for analytics | Accepted |
| [0008](0008-data-driven-rules-and-workflows.md) | Rules, quotas and approval workflows as data, changed without a deploy | Accepted |
| [0009](0009-totp-mfa-and-demo-personas.md) | TOTP MFA for privileged roles; demo personas behind `DEMO_MODE` | Accepted |
| [0010](0010-strict-csp-no-inline-js.md) | Strict Content-Security-Policy, no inline JavaScript | Accepted |
| [0011](0011-tenancy-via-institution-fk.md) | Tenancy through an `Institution` foreign key | Accepted |
| [0012](0012-append-only-audit-trigger.md) | Append-only audit log enforced by a database trigger | Accepted |
