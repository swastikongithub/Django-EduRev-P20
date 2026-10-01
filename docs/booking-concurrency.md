# How LPU Reserve makes double-booking impossible

> P20 §17: *"a written explanation of the conflict-prevention mechanism — the artefact that shows
> the team understood why it works."* Acceptance criterion: *"500 concurrent attempts on one slot
> yield exactly one booking — proven by test."*

## The problem

Two students open the same lab at the same minute and both click **Book 10:00–11:00**. The naive
implementation is:

```python
if not Booking.objects.filter(resource=lab, period__overlap=wanted).exists():   # (1) check
    Booking.objects.create(resource=lab, period=wanted)                           # (2) act
```

Both requests can run step (1) before either runs step (2). Both see "free", both insert, and the
lab is double-booked. Wrapping it in `transaction.atomic()` does not help: under PostgreSQL's
default READ COMMITTED isolation, neither transaction can see the other's uncommitted row.
Locking "the slot" does not help either, because there is no row for a slot that doesn't exist
yet.

## The guarantee: an exclusion constraint

A booking stores its time as a single PostgreSQL range, `period tstzrange` (half-open `[start, end)`,
so 10:00–11:00 and 11:00–12:00 do **not** overlap). The table carries:

```sql
ALTER TABLE bookings_booking ADD CONSTRAINT booking_no_overlap
  EXCLUDE USING gist (resource_id WITH =, period WITH &&)
  WHERE (status IN ('pending', 'approved', 'checked_in'));
```

Read it as: *no two rows may have an equal `resource_id` **and** overlapping `period`, among
bookings that are holding time.* PostgreSQL enforces this inside the index, at INSERT/UPDATE time,
for every transaction, including ones not yet committed. When two transactions insert
overlapping rows, the second one to reach the index waits for the first. When the first commits,
the second fails with SQLSTATE `23P01` (exclusion_violation). Nothing in application code can
race past it, and no lock has to be managed.

- `btree_gist` lets one GiST index combine `=` (on an integer) with `&&` (on a range).
- The `WHERE` clause means cancelled, rejected, expired, completed and released bookings stop
  blocking the slot. A cancellation frees the time with no cleanup job.

In Django (`apps/bookings/models.py`):

```python
ExclusionConstraint(
    name="booking_no_overlap",
    expressions=[("resource", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)],
    condition=Q(status__in=HOLDING_STATUSES),
)
```

## One ledger for classes, maintenance and bookings

Bookings are not the only thing that occupies a room. A timetabled class (P20 M4) and a
maintenance window (M7) must also be hard constraints. Separate tables cannot share an exclusion
constraint, so every claim on a resource's time is written into one ledger, `BookingSlot`, which
has its own unconditional constraint:

```python
ExclusionConstraint(name="slot_no_overlap",
                    expressions=[("resource", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)])
```

| Claim | `kind` | Written by | Released when |
|---|---|---|---|
| Booking | `booking` (1:1 with Booking) | `create_booking` | the booking leaves a holding status |
| Class occurrence | `class` | `timetable.publish` (every remaining occurrence this term) | the next timetable version supersedes it, in the same transaction |
| Maintenance | `maintenance` | `maintenance.schedule` | the window is cancelled or completed early (shrunk) |

A booking inserts its `Booking` row and its `BookingSlot` row in **one savepoint**. If either
constraint fires, both roll back. So a booking can never overlap a class or a maintenance
window either, and "timetable-occupied slots are never offered" holds at the database level,
not just in the calendar.

When a class or a maintenance window is written over existing *bookings*, those bookings are
displaced first: cancelled with a reason, the owner notified with free alternatives. Classes are
never displaced automatically. Maintenance over a timetabled class is refused with a sentence
naming the class.

## The write path (`apps/bookings/services.py: create_booking`)

1. **Rules** (`rules.validate_request`): role may book the type, account not restricted, slot
   boundaries, min/max duration, lead time, advance window, opening hours, blackouts, capacity.
   Each refusal is a sentence a student can act on.
2. **Friendly pre-check**: read the ledger. If something overlaps, say what ("A timetabled class
   (CSE326 Lecture, K23KF) runs 09:00–10:00."). This is for the message only. Correctness never
   depends on it.
3. **Transaction:**
   - `SELECT … FOR UPDATE` on the *requester's* user row (and their department row only if a
     departmental quota applies). This makes quota arithmetic exact for that person's own
     concurrent clicks. Different people never wait on each other here.
   - Quota check, approval-workflow resolution.
   - **Claim**: INSERT Booking + BookingSlot in a savepoint. `23P01` becomes `SlotUnavailable`
     with the same explanatory sentence.
   - Approval chain rows, accessory reservations, audit record, notification (after commit).

## A real finding: exclusion constraints can deadlock

The first run of the 500-attempt test failed. The constraint held, but about 160 attempts died
with `40P01 deadlock detected`. The reason: an exclusion check also examines *in-progress*
tuples. When transactions A and B insert overlapping rows at the same instant, A has inserted
and now waits for B's in-progress row, and B waits for A's. Unique indexes avoid this with
speculative insertion; exclusion constraints don't get that treatment. PostgreSQL resolves the
cycle by aborting one side after `deadlock_timeout` (1 s).

Two measures, neither of which carries the correctness argument:

1. **Retry the claim on `40P01`.** The victim rolls back to its savepoint (not the whole
   transaction) and tries again after a few jittered milliseconds. The retry either sees the
   winner's committed row (`23P01`, a clean "slot taken") or, if the winner rolled back, takes the
   slot itself.
2. **Queue same-resource claims with a transaction-scoped advisory lock:**
   `pg_advisory_xact_lock(20020, resource_id)` just before the INSERT. Claims on the *same*
   resource reach the index one after another, so there are no deadlocks to resolve. Claims on
   different resources never wait for each other. The lock is released automatically at
   commit/rollback, so no failure path can leak it.

Remove both measures and double-booking is **still impossible**; you only pay for it in
deadlock-timeout seconds under a stampede. The test below proves exactly that.

## Proof (`tests/test_concurrency.py`)

Both tests use `transaction=True` (real commits, like production). Each attempt runs in its own
thread with its own PostgreSQL connection, connects first, then waits on a `threading.Barrier`,
so all INSERTs genuinely race inside the database.

| Test | What is removed | Attempts | Result | Time (local) |
|---|---|---|---|---|
| `test_many_simultaneous_attempts_yield_exactly_one_booking` | nothing (full service) | 500 | 1 booked, 499 `SlotUnavailable`, 0 errors | ~9 s |
| `test_database_constraint_alone_prevents_double_booking` | pre-check **and** advisory lock | 100 in CI, 500 verified (`RAW_CONCURRENCY_ATTEMPTS=500`) | 1 booked, all others refused by PostgreSQL | ~2 s / ~40 s |

Both also assert exactly one row in `bookings_booking` and one in `bookings_bookingslot` for the
resource. PostgreSQL needs `max_connections` above 500. The dev cluster (`scripts/devdb.sh`),
docker compose and CI all start PostgreSQL with `max_connections=700`.

The HTTP-level counterpart is `loadtest/locustfile.py`: 500 logged-in users POST the same slot
through the real API, and the expected result is exactly one `201` and 499 `409`s.

## What else is protected by the database

- `booking_period_bounded`, `slot_period_bounded`: no empty or unbounded ranges.
- `slot_booking_kind_has_booking`: a ledger row of kind `booking` always points at its booking,
  and other kinds never do.
- Scope consistency on policies, hours, blackouts and quotas (`*_scope_consistent`), a quota
  targets a role xor a department, a workflow targets a type xor a resource, and a term has at
  most one published timetable (partial unique index).
- Accessory stock can never exceed what is owned (`item_available_le_total_for_accessories`).
- The audit log is append-only by trigger: `UPDATE`/`DELETE` are rejected except detaching a
  deleted user's id.

## Why Redis is not involved

Redis is the Celery broker only (reminders, auto-release sweeps, nightly analytics). Booking
correctness never touches it, so a Redis outage delays notifications but cannot cause a double
booking (P20 §16, Track P).
