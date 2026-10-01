# 0005. Server-rendered templates with htmx (Path P1), DRF API alongside

- Status: accepted
- Related: CES §1.1, §1.8 (Path P1); P20 §8 (frontend and API deltas)

## Context

CES §1.8 makes Path P1 (Django templates, CSE326 for CSS and JavaScript, optionally htmx) the
default on Track P; DRF with drf-spectacular is optional on P1. P20 §8 nevertheless lists API
endpoints (`/resources`, `/resources/:id/availability`, `/bookings`, `/bookings/:id/approve`,
`/bookings/:id/check-in`, `/maintenance`, `/analytics/utilisation`), and P13 needs to push a
published timetable programmatically. The UI needs interactive pieces: drag-to-select on a
calendar, a live booking board, a QR scanner, inline form feedback.

## Decision

- Pages are Django templates (`templates/`) with a design system (`static/css/tokens.css`,
  `app.css`; [design-system.md](../design-system.md)). Interactivity uses htmx partials
  (booking panel, board refresh every 60 s, workflow tester) and small first-party scripts in
  `static/js/` wired through `data-*` attributes.
- A REST API at `/api/v1/` (DRF, session authentication, drf-spectacular OpenAPI 3) covers
  every P20 endpoint plus series, approvals queue, notifications, timetable publication and
  breakdown reports. The schema is committed as `docs/openapi.yaml` (`make openapi`) and
  served at `/api/v1/docs/`.
- Both layers call the same services ([ADR 0002](0002-modular-monolith-with-service-layer.md)).
  Neither contains business rules.

## Consequences

- One codebase, no SPA build pipeline, no client-side state store; pages work with
  server-side authorisation and CSRF out of the box.
- The API uses session authentication only (no JWT/SimpleJWT, which CES requires only on
  P2/P3). A machine client such as P13 must hold a session for a user with
  `manage_timetable`; a token scheme would be needed for unattended integration
  (see [known issues](../known-issues.md#integrations)).
- Every endpoint has an integration test including authorisation failures
  (`tests/test_api.py`).
- htmx runs with `allowEval: false` so it works under the strict CSP
  ([ADR 0010](0010-strict-csp-no-inline-js.md)).

## Alternatives considered

- **Path P2 (DRF + React SPA).** Rejected: duplicates validation and permissions in two
  places, needs a second build and deployment, and is outside the default path.
- **Templates only, no API.** Rejected: P20 names API endpoints, P13 integration needs one,
  and the load test drives the real API.
