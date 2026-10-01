# 0001. Track P: Django 5.2 and PostgreSQL 16

- Status: accepted
- Deciders: project team, week 1
- Related: CES §1.1, §1.9, §1.10; P20 §7, §16

## Context

The EduRev programme offers two stacks. Track J is Next.js, Node.js, MongoDB and Redis;
Track P is Python, Django and PostgreSQL. P20's central requirement is that double-booking be
structurally impossible, including against the published timetable, under 500 concurrent
attempts on one slot (P20 §8, §22). CES §1.9 lists P20 as a project where Track P is the
stronger choice because "a PostgreSQL exclusion constraint makes double-booking structurally
impossible". On Track J the same guarantee needs a unique index on a discretised
resource/time-slot pair plus a Redis lock that must be released on every failure path, and
Redis then sits on the critical path for booking (P20 §16).

The team's courses (INT253, CSE326) cover Django and server-rendered pages; range types,
Celery and QR generation are the stated gaps (P20 §19).

## Decision

Build on Track P: Python 3.12, Django 5.2 (LTS), PostgreSQL 16, Celery with Redis as broker,
Docker and GitHub Actions. Use PostgreSQL features directly where they carry correctness:
`tstzrange` columns (`DateTimeRangeField`), `ExclusionConstraint` with `btree_gist`, partial
unique indexes, check constraints, `SELECT ... FOR UPDATE [SKIP LOCKED]`, full-text search and
`pg_trgm`.

## Consequences

- Double-booking is refused by the database for every writer, not only by application code
  ([ADR 0003](0003-exclusion-constraints-and-unified-ledger.md)).
- Redis is not on the booking path; an outage cannot cause a double booking. It does still
  back the Django cache and the Celery broker, so it affects sign-in, the API and email
  delivery (see [known issues](../known-issues.md)).
- The application is tied to PostgreSQL. SQLite cannot run the test suite; local development
  needs a PostgreSQL 16+ server (`scripts/devdb.sh` or docker compose).
- Search uses PostgreSQL full-text and trigram similarity instead of a separate search engine.
- Django's admin, auth, migrations and forms are available without extra services.

## Alternatives considered

- **Track J (Node.js, MongoDB, Redis lock).** Rejected: the hand-built lock is the hardest part
  to get right, and MongoDB has no range-overlap constraint, so the guarantee would live in
  application code.
- **Django on MySQL.** Rejected: no exclusion constraints or range types; overlap would again
  need locking in application code.
- **Discretised slot table with a unique index** (one row per resource per 30 minutes).
  Rejected: ties the data model to one slot size, multiplies rows, and still needs care for
  bookings that span several slots. Range overlap expresses the rule directly.
