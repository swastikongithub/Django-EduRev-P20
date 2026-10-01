# 0003. Exclusion constraints and a unified BookingSlot ledger

- Status: accepted
- Related: P20 §3, §4, §8, §15, §17, §22; [booking-concurrency.md](../booking-concurrency.md)

## Context

P20 requires conflict prevention to be absolute, "including against the published timetable",
and maintenance windows also take a resource out of use. Check-then-insert in application
code races under READ COMMITTED; there is no row to lock for a slot that does not exist yet.
PostgreSQL exclusion constraints reject overlapping ranges at write time, but a constraint only
covers rows in one table. Bookings, timetabled class occurrences and maintenance windows are
different kinds of record.

## Decision

1. `Booking.period` is a `tstzrange` (half-open), and `Booking` carries
   `EXCLUDE USING gist (resource_id WITH =, period WITH &&) WHERE status IN ('pending','approved','checked_in')`
   (`booking_no_overlap`). Released, cancelled, rejected, expired and completed bookings stop
   blocking without any cleanup job.
2. Every claim on a resource's time also writes one row to `BookingSlot`, which has an
   unconditional exclusion constraint (`slot_no_overlap`). Kinds: `booking` (1:1 with a
   booking, enforced by `slot_booking_kind_has_booking`), `class` (from `timetable.publish`),
   `maintenance` (from `maintenance.schedule`).
3. A booking inserts its `Booking` and `BookingSlot` rows in one savepoint
   (`bookings.services._claim`). SQLSTATE `23P01` becomes `SlotUnavailable` with a sentence
   naming what holds the time.
4. Hard claims (classes, maintenance) displace overlapping ordinary bookings first
   (`displace_bookings`: cancel, notify with alternatives), then insert. Classes are never
   displaced automatically: maintenance over a class is refused, and a timetable that
   overlaps maintenance fails to publish as a whole.
5. A ledger row is deleted when its claim ends early (`set_status` leaving a holding status,
   maintenance cancelled, timetable superseded) and shortened on early check-out or early
   maintenance completion.

## Consequences

- No writer, including a future one, can create an overlap; the database is the authority.
  `tests/test_concurrency.py` proves 500 simultaneous attempts produce exactly one booking, and
  that the constraint alone holds with every application safeguard removed.
- "Timetable-occupied slots are never offered" holds at write time as well as in the
  calendar (`tests/test_timetable.py::test_timetabled_slots_are_never_offered`).
- Availability for many resources is one range query on one table (`availability._load`).
- Two rows per booking must stay consistent; status changes go through `set_status`, which
  releases the slot when a booking leaves a holding status. `tests/test_state_machine.py`
  covers every transition.
- Republishing a term's timetable deletes and rewrites its class slots in one transaction,
  so the change of timetable and the change of availability are one event.
- Requires the `btree_gist` extension (migration `core.0002`).

## Alternatives considered

- **Constraint on `Booking` only, checking classes and maintenance in code.** Rejected: the
  timetable guarantee would rest on application code and race with publication.
- **Store classes and maintenance as pseudo-bookings.** Rejected: pollutes booking semantics
  (status machine, quotas, check-in, analytics).
- **Discretised slot rows with a unique index.** Rejected in [ADR 0001](0001-track-p-django-postgresql.md).
- **Serializable isolation with retry.** Rejected: correct but turns every concurrent booking
  into retries, and still depends on every writer using it.
