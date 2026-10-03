# Roles and permissions

Access control has two halves, and every page and API endpoint enforces both on the server.
Hiding a link in the UI is a convenience, never the control.

1. **Capabilities (RBAC).** Each role is a Django group `role:<role>` holding custom
   permissions declared on `User.Meta` (`apps/accounts/models.py`). The mapping is
   `ROLE_PERMISSIONS` in `apps/accounts/permissions.py`; `sync_role_groups` re-applies it after
   every `migrate`, and a `post_save` signal keeps each user in their role's group.
2. **Object scope (ABAC).** Capabilities say *what* a person may do; scope says *where*.
   `can_manage_resource` and the per-module queryset helpers limit custodians to the
   resources they are custodian of, heads of department to their department's resources, and
   leave facility managers and administrators campus-wide. Everything is also limited to the
   person's institution ([ADR 0011](adr/0011-tenancy-via-institution-fk.md)).

## Roles

| Role (`User.role`) | Who | Scope |
|---|---|---|
| `student` | Students | Their own bookings |
| `faculty` | Teaching staff | Their own bookings and bookings they make for a class |
| `staff` | Non-teaching staff | As faculty |
| `custodian` | Lab in-charges, caretakers, equipment custodians | The resources they are named custodian of (`catalogue.Custodian`) |
| `dept_head` | Heads of department | Resources owned by their department |
| `facility_manager` | Estate and facility office | Campus-wide |
| `admin` | System administrators | Campus-wide, plus users and roles |

Superusers are treated as campus-wide and always need MFA. They are for break-glass use of
`/django-admin/`, not for day-to-day work.

## Capability matrix

| Capability (`accounts.<codename>`) | student | faculty | staff | custodian | dept_head | facility_manager | admin |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `book_resources`: book resources whose type allows the role | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `book_recurring`: weekly series with per-date preview |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `book_on_behalf`: book for a class or group |  | ✓ | ✓ |  | ✓ | ✓ | ✓ |
| `approve_bookings`: decide approval steps |  |  |  | ✓ | ✓ | ✓ | ✓ |
| `manage_resources`: edit resources, door QR codes |  |  |  | ✓ |  | ✓ | ✓ |
| `manage_maintenance`: schedule maintenance, handle breakdowns |  |  |  | ✓ |  | ✓ | ✓ |
| `manage_inventory`: stock, restock, write off |  |  |  | ✓ |  | ✓ | ✓ |
| `forgive_no_shows`: forgive no-shows, lift pauses |  |  |  | ✓ |  | ✓ | ✓ |
| `view_department_analytics`: Insights for a department |  |  |  |  | ✓ | ✓ | ✓ |
| `view_campus_analytics`: Insights for the whole campus |  |  |  |  |  | ✓ | ✓ |
| `configure_policy`: rules, hours, blackouts, quotas, ladder, workflows |  |  |  |  | ✓ | ✓ | ✓ |
| `manage_timetable`: import and publish the timetable |  |  |  |  |  | ✓ | ✓ |
| `view_audit_log`: read and export the audit log |  |  |  |  |  | ✓ | ✓ |
| `manage_users`: add people, change roles, deactivate accounts |  |  |  |  |  |  | ✓ |
| **MFA required at sign-in** (`MFA_REQUIRED_ROLES`) |  |  |  |  |  | ✓ | ✓ |

Notes on the matrix:

- **Which types a role may book** is data, not code: a resource type can list
  `allowed_roles` (for example, vehicles for faculty and staff only). Empty means every role.
- **Heads of department** configure policy only within their department: they edit
  departmental quotas and read the workflow builder; campus-wide rules need a facility
  manager or administrator.
- **MFA** is required for `admin`, `facility_manager` and superusers by default. Anyone else
  who enrols voluntarily is held to it too. MFA is checked for the whole session, not only
  at sign-in: if someone is promoted to an MFA role while signed in, their session ends and
  they sign in again with a code ([security review](security-review.md), SEC-12).

## Rules that apply whatever the role

These are separation-of-duties and safety rules enforced in the service layer.

| Rule | Where |
|---|---|
| Nobody decides an approval step for a request they made or that is for them; such requests never appear in their queue | `approvals.services.can_decide`, `queue_for` |
| Nobody forgives their own no-show or lifts their own booking pause | `checkins.services.forgive`, `lift_restriction` |
| A critical breakdown report takes a resource out of service only when someone who manages that resource files or confirms it | `maintenance.services.report_breakdown`, `confirm_critical` |
| The last active administrator cannot be demoted or deactivated; nobody can deactivate themselves | `accounts.manage_views.change_role`, `set_active` |
| Deactivating an account never deletes it; bookings and history are kept | `accounts.manage_views.set_active` |
| Every privileged action is written to the append-only audit log | `audit.services.record` ([ADR 0012](adr/0012-append-only-audit-trigger.md)) |

## Staff console access

The console (`/manage/`) shows each person only the sections their capabilities allow; each
view re-checks the capability (`apps/core/manage_views.staff_required`).

| Console area | Path | Needs any of | Scope |
|---|---|---|---|
| First-run setup | `/setup/bootstrap/` | nobody signed in, **and the database has no accounts at all**; otherwise a 404 for everyone | Creates one Administrator (never superuser or staff) |
| Console home | `/manage/` | any staff capability | Own work |
| Approvals queue | `/manage/approvals/` | `approve_bookings` | Steps the person may decide |
| Live booking board | `/manage/board/` | `manage_resources`, `approve_bookings` | Managed resources |
| Resources | `/manage/resources/` | `manage_resources`, `approve_bookings` (creating and importing: `manage_resources`, campus-wide) | Managed resources |
| Upkeep (maintenance, breakdowns) | `/manage/maintenance/` | `manage_maintenance` | Managed resources |
| Stock | `/manage/inventory/` | `manage_inventory` | Managed resources |
| No-shows and pauses | `/manage/no-shows/` | `forgive_no_shows` | People seen on managed resources |
| Insights | `/insights/` | `view_department_analytics`, `view_campus_analytics` | Department, or campus |
| Setup hub | `/manage/setup/` | `configure_policy`, `manage_timetable`, `manage_users`, `view_audit_log` | Cards shown per capability |
| Policies | `/manage/policies/` | `configure_policy` | Campus-wide, or own department's quotas |
| Approval workflows | `/manage/workflows/` | `configure_policy` | Institution |
| Timetable | `/manage/timetable/` | `manage_timetable` | Institution |
| Users and roles | `/manage/users/` | any staff capability to view; `manage_users` to change | Institution |
| Add a person | `/manage/users/new/` | `manage_users` | Institution |
| Catalogue (resource types, blocks, departments) | `/manage/catalogue/` | `manage_resources`, campus-wide (facility managers, administrators) | Institution |
| Audit log | `/manage/audit/` | `view_audit_log` | Institution |
| Operations | `/manage/ops/` | campus-wide role (facility manager, administrator) | Institution |
| Django admin | `/django-admin/` | `is_staff` (superusers); same sign-in and MFA as the product | Break-glass only |

## API access

The REST API (`/api/v1`, [openapi.yaml](openapi.yaml)) applies the same capabilities through
`HasCap(...)` permission classes and the same scoped querysets. Every endpoint refuses
anonymous requests; the live schema and Swagger UI need a signed-in user.

| Endpoint | Needs |
|---|---|
| `GET /resources`, `/resources/{id}`, `/resources/{id}/availability` | signed in |
| `POST /resources/{id}/report-breakdown` | signed in |
| `GET/POST /bookings`, `/bookings/{ref}/cancel`, `/check-in`, `/check-out`, `/ics` | `book_resources` to create; own or managed bookings otherwise |
| `POST /bookings/{ref}/approve`, `/reject` | `approve_bookings`, scoped as in the console |
| `GET/POST /series`, `/series/preview` | `book_recurring` |
| `GET /approvals` | `approve_bookings` |
| `GET/POST /maintenance`, `/maintenance/{id}/cancel`, `/complete` | `manage_maintenance` |
| `POST /timetable/publications` | `manage_timetable` |
| `GET /analytics/utilisation` | `view_department_analytics` (campus scope needs `view_campus_analytics`) |
| `GET /me`, `/notifications` | signed in (own data only) |

## Changing someone's role

Administrators change roles in **Setup → Users** ([guide-admin.md](guide-admin.md#users-and-roles)).
The change takes effect on the person's next request; if the new role needs MFA, their
current session ends and they sign in again with a code. Every change is audited as
`user.role_change` with the before and after role.

## Where this is tested

- `tests/test_console_setup.py`, `tests/test_console_ops.py`: every console screen per role, scoping, read-only views.
- `tests/test_api.py`: every endpoint including authorisation failures.
- `tests/test_security.py`: separation of duties, MFA enforcement, IDOR and tenant isolation.
- `tests/test_malformed_input.py`: every page and form as five roles with hostile input.
