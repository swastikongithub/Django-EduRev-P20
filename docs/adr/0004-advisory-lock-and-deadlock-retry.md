# 0004. Advisory lock and deadlock retry as a throughput aid

- Status: accepted
- Related: [ADR 0003](0003-exclusion-constraints-and-unified-ledger.md); [booking-concurrency.md](../booking-concurrency.md#a-real-finding-exclusion-constraints-can-deadlock)

## Context

The first run of the 500-attempt stampede kept the guarantee (one booking) but about 160
attempts failed with `40P01 deadlock detected`. Exclusion checks also inspect in-progress
tuples: when two transactions insert overlapping ranges at the same instant, each waits for
the other, and PostgreSQL aborts one after `deadlock_timeout` (1 s). Those users saw an error
instead of "slot taken", and the stampede took far longer.

## Decision

Two measures in `apps/bookings/services.py`, explicitly not part of the correctness argument:

1. `serialise_claims(resource_id)` takes `pg_advisory_xact_lock(20020, resource_id)` just
   before the INSERT. Claims on the same resource queue; claims on different resources never
   wait for each other. The lock is transaction-scoped, so every commit or rollback releases it.
2. `_claim` retries on `40P01` (up to 8 times, with jittered back-off), rolling back only its
   savepoint. A retry either sees the winner's committed row (`23P01`, a clean refusal) or,
   if the winner rolled back, takes the slot.

Per-user quota accounting is serialised separately with `SELECT ... FOR UPDATE` on the
booked-for user row (and the department row when a departmental quota applies).

## Consequences

- The 500-attempt test resolves with 1 booking, 499 `SlotUnavailable`, 0 errors.
- `tests/test_concurrency.py::test_database_constraint_alone_prevents_double_booking`
  monkeypatches both the pre-check and `serialise_claims` away and still gets exactly one
  booking, so removing this ADR's measures costs only time.
- Same-resource bookings are serialised for the duration of the claim transaction. That is
  intended: they compete for the same time anyway.
- Advisory key namespace `20020` must not be reused for other purposes.

## Alternatives considered

- **`SELECT ... FOR UPDATE` on the resource row.** Equivalent effect, but takes a row lock
  that also blocks unrelated updates to the resource (status, edits).
- **Accept deadlocks and surface them as "try again".** Rejected: poor experience at exactly
  the moment that matters (a lab slot release).
- **Redis lock.** Rejected: puts Redis on the booking path and needs release on every failure
  path (P20 §8 Track J note).
