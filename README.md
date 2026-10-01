# LPU Reserve: campus resource, lab and facility booking

**EduRev P20** · Track P (Python · Django 5.2 · PostgreSQL 16 · Celery/Redis · Docker · GitHub Actions)

One place to find and book every bookable thing at Lovely Professional University:
classrooms, computer and electronics labs, seminar halls, meeting rooms, courts and
grounds, cameras, 3D printers, microscopes and vehicles. The timetable is respected
automatically, double-booking is structurally impossible, check-in is a QR scan, unused
bookings release themselves, and facility managers can finally see what is used and what
sits idle.

> Built from the P20 specification in [`docs/EduRev_Project_Description.pdf`](docs/EduRev_Project_Description.pdf)
> and modelled on the real LPU UMS portals (old UMS and studentums), then redesigned.

---

## What it does

| P20 module | What you get | Where |
|---|---|---|
| **M1 Resource catalogue** | 10 resource types, photos, capacity, features, attributes, custodians, location by block; natural-language search ("lab for 40 tomorrow after 3 pm", "projector block 34") on PostgreSQL full-text + trigram | `apps/catalogue` |
| **M2 Availability & rules** | Opening hours, slot size, min/max duration, lead time, booking window, blackouts (campus/block/type/resource, exempt roles), role and departmental quotas, no-show restriction ladder: all data, most-specific-wins | `apps/rules` |
| **M3 Booking engine** | Atomic slot claim protected by PostgreSQL **exclusion constraints**; one ledger shared by bookings, classes and maintenance; recurring series with per-date conflict handling | `apps/bookings` |
| **M4 Timetable integration** | CSV / P13 API import, clash validation, atomic publish/republish; class time written to the ledger as a hard constraint and never offered | `apps/timetable` |
| **M5 Approval workflow** | Multi-step chains chosen by resource / type / requester role / attendees / duration, edited in a builder; changes apply to the next booking, no deploy | `apps/approvals` |
| **M6 Check-in & auto-release** | QR booking pass + door QR, phone camera or in-app scanner, grace period, auto-release sweep, early check-out hands time back, no-show tracking, progressive restriction | `apps/checkins` |
| **M7 Maintenance & downtime** | Scheduled windows on the ledger (displacing bookings, refusing class overlaps), breakdown reports from anyone, critical reports take a resource offline | `apps/maintenance` |
| **M8 Consumables & accessories** | Stock reserved with a booking, issued at check-in, returned at check-out, low-stock alerts | `apps/inventory` |
| **M9 Analytics & reporting** | Nightly utilisation snapshots; utilisation by resource/type/department/block, idle-capacity ranking weighted by asset cost, heat map, no-show rates, demand vs supply, approval turnaround, downtime, quota consumption | `apps/analytics` |

Plus notifications (in-app + email), iCal export and a private calendar feed, an append-only audit
log enforced by a database trigger, TOTP MFA for privileged roles, DPDP data export, and a REST API
(`/api/v1`, OpenAPI 3) for every P20 endpoint.

## The guarantee

```sql
EXCLUDE USING gist (resource_id WITH =, period WITH &&) WHERE (status IN ('pending','approved','checked_in'))
```

PostgreSQL itself refuses a second overlapping booking for the same resource, however many
people click at once. A second constraint on the `BookingSlot` ledger stops a booking from
overlapping a timetabled class or a maintenance window. **500 simultaneous attempts on one slot
produce exactly one booking**, proven in CI (`tests/test_concurrency.py`). The full argument,
including the deadlock behaviour the stress test uncovered and how it is handled, is in
[`docs/booking-concurrency.md`](docs/booking-concurrency.md).

## Quick start

### Docker (one command)

```bash
docker compose up --build                      # web + Celery worker + Celery Beat + PostgreSQL 16 + Redis
docker compose --profile demo run --rm seed    # load the demo campus (in another terminal)
```

Open <http://localhost:8000>. With `DEMO_MODE=1` (the compose default) the sign-in page offers
one-click demo personas.

### Local development (no Docker)

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows; use .venv/bin/activate elsewhere
pip install -r requirements-dev.txt
scripts/devdb.sh init                               # a private PostgreSQL cluster on :5433 (max_connections=700)
cp .env.example .env                                # DEBUG=1, DEMO_MODE=1, eager Celery
python manage.py migrate
python manage.py seed_demo                          # ~25 s; --reset rebuilds it
python manage.py runserver
```

## Demo personas

`seed_demo` creates a fictional campus (12 blocks, 61 resources, 155 people, a published
2026-27 odd-term timetable, six weeks of history). Sign in with one click as:

| Persona | Try this |
|---|---|
| **Student** (Aarav Sharma, K23KF) | Home → "What do you need, and when?" → drag across free time on a lab calendar → QR pass → check in from the door QR on a phone |
| **Faculty** (Dr. Neha Verma) | Bookings → *Weekly booking*: preview every date of a weekly lab, see the one that clashes, book the rest |
| **Custodian** (Rajinder Singh) | Approvals queue, live booking board, upkeep (schedule maintenance and watch it displace a booking), stock |
| **Head of Department** | Department-scoped insights and quotas; second-step approvals |
| **Facility Manager** | Campus insights (idle-capacity "money report", heat map, demand vs supply), policies, timetable publishing, Operations → *Run no-show sweep* to release a booking live |
| **Administrator** | Workflow builder ("who approves this?" tester), users and roles, audit log |

Privileged roles use TOTP MFA when signing in with a password; demo one-click sign-in exists only
when `DEMO_MODE=1` and is off by default.

## Testing

```bash
make test-fast        # everything except the stampede (≈ 3 min)
make test-race        # the 500-attempt concurrency proofs
pytest -m e2e         # Playwright browser journeys (python -m playwright install chromium)
make loadtest         # Locust: 500 users, one slot (see loadtest/README.md)
```

| Layer | What it proves |
|---|---|
| Unit / service | rules, quotas (individual and shared departmental), state machine, approvals, check-in windows, auto-release boundaries, restriction ladder, timetable publish/republish, maintenance displacement, inventory, analytics against a hand-computed fixture |
| Concurrency | 500 simultaneous attempts → exactly one booking; with every application safeguard removed, PostgreSQL alone still allows exactly one |
| API | every `/api/v1` endpoint including authorisation-failure paths |
| Pages | every screen per role, booking through the real form, IDOR, lockout, MFA, demo-login off by default |
| End-to-end | drag-to-book → QR pass; timetable never offered; phone door-QR check-in/out; auto-release; no horizontal overflow at 360 px |
| CI | ruff, Django + migration checks, the full suite on PostgreSQL 16 with 500-way concurrency, pip-audit, gitleaks, Docker build |

## Architecture

A modular monolith with one Django app per P20 module. Views parse, call a service, render.
Business rules live in `services.py` and are unit-tested without HTTP, and apps talk to each
other through those functions.

```
config/            settings (env-driven), URL roots, Celery app
apps/core          tenancy (Institution on every record), shell, health probes, sweeps, design-system tags
apps/accounts      users, roles → Django groups/permissions, object-level checks, MFA, sign-in
apps/catalogue     M1   apps/rules        M2   apps/bookings    M3   apps/timetable   M4
apps/approvals     M5   apps/checkins     M6   apps/maintenance M7   apps/inventory   M8
apps/analytics     M9   apps/notifications      apps/audit
templates/ static/ server-rendered UI (Django templates + htmx), design tokens, no inline JS (strict CSP)
tests/             pytest-django suites, tests/e2e Playwright journeys
loadtest/          Locust peak scenario      docker/ + Dockerfile + docker-compose.yml
```

Redis is only the Celery broker (reminders, check-in nudges, auto-release, approval expiry,
maintenance transitions, nightly analytics). Booking correctness never depends on it.

## Documentation

| Document | Contents |
|---|---|
| [docs/booking-concurrency.md](docs/booking-concurrency.md) | How double-booking is made impossible, and the proof |
| [docs/design-system.md](docs/design-system.md) | The UI contract: what was kept from LPU's portals, what was fixed, tokens, components |
| [docs/openapi.yaml](docs/openapi.yaml) | API specification (live: `/api/v1/docs/`) |
| [loadtest/README.md](loadtest/README.md) | Running and reading the 500-user load test |

Further handover documents (architecture decision records, ERD, environment reference, runbook,
role matrix, user guides, requirements traceability, known issues) live in [`docs/`](docs/).

## Licence and credits

Built for the EduRev programme at Lovely Professional University. All people, bookings and
campus details in the demo data are fictional. Resource photographs: Pexels and Unsplash,
credited in [`static/img/resources/CREDITS.md`](static/img/resources/CREDITS.md). Icons: Lucide (ISC).
