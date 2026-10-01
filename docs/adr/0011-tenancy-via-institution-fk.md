# 0011. Tenancy through an Institution foreign key

- Status: accepted
- Related: CES §1.2 ("multi-tenant-ready from day one: every domain record carries an institution identifier")

## Context

The platform is built for LPU but designed to be offered to other institutions. Retrofitting
tenancy later is expensive. Options range from a column on each table to a schema or a
database per tenant.

## Decision

- `core.Institution` is the tenant root (code, name, timezone). Migration `core.0002`
  creates the default `LPU` institution.
- Abstract `core.TenantModel` adds `institution = ForeignKey(Institution, on_delete=PROTECT)`
  with a default of the `DEFAULT_INSTITUTION_CODE` tenant. Top-level domain models inherit it:
  `User`, `Department`, `Building`, `ResourceType`, `Feature`, `Resource`, `BookingPolicy`,
  `AvailabilityRule`, `Blackout`, `Quota`, `RestrictionTier`, `Booking`, `BookingSeries`,
  `ApprovalWorkflow`, `NoShow`, `Restriction`, `MaintenanceWindow`, `BreakdownReport`,
  `InventoryItem`, `AcademicTerm`, `TimetablePublication`, `AuditLog`.
- Dependent rows (`BookingSlot`, `BookingAttempt`, `ResourceAttribute`, `ResourceImage`,
  `Custodian`, `SavedResource`, `ApprovalStep`, `Approval`, `CheckIn`, `Issuance`,
  `StockMovement`, `TimetableEntry`, `UtilisationSnapshot`, `Notification`) inherit the tenant
  through their parent's foreign key.
- Natural keys are unique per institution (resource code and slug, building code, department
  code, type code, SKU, term code).
- Views and API querysets filter on `request.user.institution_id`; services check that a
  booking's person and resource belong to the same institution.

## Consequences

- Row-level separation in one schema; one database serves all tenants.
- Cross-tenant access is tested at the API (`tests/test_api.py::test_resource_detail_by_id_or_slug_and_tenant_isolation`,
  `test_create_rejects_foreign_resource`).
- Isolation depends on every query filtering by institution. There is no database-level
  row security; a missed filter would leak.
- Background sweeps run across all institutions; `SweepRun` is global.
- `User.username` is unique globally (Django default), not per institution.
- There is no UI to create institutions; tenant onboarding is a data task.
- These gaps are acceptable while one tenant exists and are listed in
  [known issues](../known-issues.md#tenancy).

## Alternatives considered

- **Schema per tenant (django-tenants).** Stronger isolation, but complicates migrations,
  the shared exclusion constraints and cross-tenant operations; heavy for a single tenant.
- **Database per tenant.** Strongest isolation and simplest queries, highest operational cost.
- **PostgreSQL row-level security.** A good later hardening step on top of the FK column.
