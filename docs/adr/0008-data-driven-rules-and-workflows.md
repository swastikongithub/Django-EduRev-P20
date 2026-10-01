# 0008. Rules, quotas and approval workflows as data

- Status: accepted
- Related: P20 §3, §5 (M2, M5), §9, §22 ("approval workflows configurable per resource type without deployment")

## Context

Booking rules differ by resource type and individual resource (slot size, minimum and maximum
duration, lead time, how far ahead bookings open, check-in grace), by day (opening hours), by
period (holidays, exams, events), by role and department (quotas), and by behaviour (no-show
ladder). Approval chains differ by resource, type, requester role, number of attendees and
duration. These change during a term, and the acceptance criteria require changing workflows
without a deployment.

## Decision

- Rules are rows in `apps/rules`: `BookingPolicy`, `AvailabilityRule`, `Blackout`, `Quota`,
  `RestrictionTier`. Policies, hours and blackouts are scoped campus, type or resource
  (`Scope`), with check constraints keeping scope fields consistent. Resolution is
  most-specific-wins: resource, then type, then campus, then a built-in default
  (`rules.services.policies_for`, `weekly_hours_for`). Blackouts can also target a block and
  exempt roles.
- Quotas target a role (each holder individually) or a department (shared pool), optionally
  one resource type, per day, week or month, by hours and/or count. They are checked inside
  the booking transaction under a row lock.
- Approval workflows are rows (`ApprovalWorkflow` with ordered `ApprovalStep`s). Matching is
  most-specific-first (resource, then type, then any), then priority; conditions are
  requester roles, minimum attendees and minimum duration. A workflow can auto-approve.
  Steps name an approver role (custodian, head of the owning department, facility manager,
  administrator) or a named person, with an SLA in hours.
- The staff console edits all of these (`/manage/policies/`, `/manage/workflows/`), every
  change is audited, and the workflow builder includes a "who approves this?" tester
  (`workflow_forms.explain`). Changes apply to the next booking; existing bookings keep the
  chain they started with.

## Consequences

- No code change or deployment to retune rules or approvals
  (`tests/test_approvals.py::test_changing_a_workflow_row_changes_the_next_booking`,
  `tests/test_console_setup.py::test_workflow_builder_applies_to_the_next_booking`).
- Rule refusals are sentences derived from the data ("Equipment needs at least 1 hour notice"),
  which keeps messages accurate when rules change.
- Misconfiguration is possible (for example a quota that blocks everyone); the console
  previews and describes each rule in words, and the tester explains workflow matches.
- A workflow with no steps and no auto-approve is ignored rather than blocking everyone.
- Rule precedence must be understood by administrators; [guide-admin.md](../guide-admin.md)
  explains it.

## Alternatives considered

- **Rules in settings or code.** Rejected: needs a deploy per change; fails the acceptance
  criterion.
- **A general rule engine or expression language.** Rejected: harder to validate and explain
  to non-technical staff; the fixed set of scoped fields covers P20's requirements.
- **Per-resource configuration only.** Rejected: 61 resources (and many more in production)
  would need duplicated settings; scope inheritance keeps it manageable.
