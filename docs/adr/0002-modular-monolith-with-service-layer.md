# 0002. Modular monolith with a service layer

- Status: accepted
- Related: CES §1.2; P20 §5

## Context

CES §1.2 requires a modular monolith for projects that are not marked Enterprise, one Django
app per functional module, business logic in `services.py` ("a view reads the request, calls a
service and renders"), no cross-module direct database access, and business logic that is
unit-testable without HTTP. P20 has nine modules (M1–M9) with explicit dependencies
(M3 depends on M2, M5 and M6 on M3, M9 on M3 and M6). M1 is meant to be shared with P13 later.

## Decision

- One Django app per P20 module: `catalogue` (M1), `rules` (M2), `bookings` (M3),
  `timetable` (M4), `approvals` (M5), `checkins` (M6), `maintenance` (M7), `inventory` (M8),
  `analytics` (M9), plus platform apps `core`, `accounts`, `notifications` and `audit`.
- Each app exposes its operations as functions in `services.py`, documented in the module
  docstring (for example `bookings.services.create_booking`, `rules.services.validate_request`,
  `approvals.services.decide`).
- Views (`views.py`, `manage_views.py`) and API endpoints (`api.py`) parse input, call a
  service, and render or serialise. They do not contain business rules.
- Apps call each other's services, typically with a function-local import to avoid import
  cycles. Writes to another module's tables go through that module's service.
- Services accept `now=` so time-dependent rules are testable without freezing the clock.
- Domain failures are raised as `DomainError` subclasses carrying a code and a sentence
  (`apps/core/errors.py`), so the HTML and API layers present the same message.

## Consequences

- The HTML console and the REST API share one implementation of every rule; there is nothing
  to keep in sync.
- Most tests call services directly (`tests/test_booking_engine.py`, `test_approvals.py`,
  `test_checkins.py`, `test_timetable.py`, `test_rules_availability.py`,
  `test_maintenance_inventory.py`, `test_analytics.py`).
- A module could be extracted later behind its service interface; the catalogue is the
  likely first candidate if P13 consumes it.
- Some read-only queries join across apps (analytics reading bookings and check-ins,
  availability reading rules). These are reads only and are acceptable inside one database;
  extraction would need them replaced by service calls or events.
- One deployable, one database, one transaction boundary: a booking, its approval rows, its
  stock reservation, its audit row and its notification commit or roll back together.

## Alternatives considered

- **Microservices per module.** Rejected: CES forbids it for this band; it would also break
  the single-transaction booking path and the shared exclusion constraint.
- **Fat models / logic in views.** Rejected: harder to test without HTTP and to share between
  the template UI and the API.
- **A single `bookings` app for everything.** Rejected: violates the one-app-per-module rule
  and blurs ownership of tables.
