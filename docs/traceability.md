# Requirements traceability

Each requirement from the P20 brief and the EduRev Common Engineering Standard (CES) in
[`EduRev_Project_Description.pdf`](EduRev_Project_Description.pdf), mapped to where it is
implemented and the evidence that it works. Test references are `file::test` under `tests/`.

Status: **Met**; **Partial** (works, with a gap recorded in [known-issues.md](known-issues.md));
**Not yet** (planned).

## P20 §22 Acceptance criteria

| # | Criterion | Status | Implementation | Evidence |
|---|---|---|---|---|
| AC-1 | 500 concurrent attempts on one slot yield exactly one booking, proven by test | Met | PostgreSQL exclusion constraints on `Booking` and the `BookingSlot` ledger ([booking-concurrency.md](booking-concurrency.md), [ADR 0003](adr/0003-exclusion-constraints-and-unified-ledger.md)) | `test_concurrency.py::test_many_simultaneous_attempts_yield_exactly_one_booking` and `::test_database_constraint_alone_prevents_double_booking` (500 attempts in CI); `loadtest/locustfile.py` |
| AC-2 | Timetable-occupied slots never offered | Met | Published classes are `class` rows on the ledger; availability marks them unselectable and the constraint refuses them | `test_booking_engine.py::test_timetable_slots_are_never_offered`, `::test_timetable_block_is_a_hard_conflict`; `test_timetable.py::test_timetabled_slots_are_never_offered`; e2e `test_journeys.py::test_timetabled_class_is_shown_with_its_reason_and_never_offered` |
| AC-3 | Approval workflows configurable per resource type without deployment | Met | `ApprovalWorkflow`/`ApprovalStep` rows edited in the console builder ([ADR 0008](adr/0008-data-driven-rules-and-workflows.md)) | `test_approvals.py::test_changing_a_workflow_row_changes_the_next_booking`; `test_console_setup.py::test_workflow_builder_applies_to_the_next_booking`; e2e `test_workflows.py::test_runtime_workflow_then_custodian_approves_in_console` |
| AC-4 | QR check-in works on mobile; un-checked-in bookings auto-release after the grace period | Met | Pass QR and door QR, in-app camera scanner; `checkins.sweep_no_shows` every minute | e2e `test_journeys.py::test_mobile_door_qr_check_in_then_check_out`, `::test_unchecked_booking_is_released_after_grace`; `test_checkins.py::test_sweep_releases_exactly_after_the_grace_period`, `::test_checkin_at_the_deadline_beats_the_sweep` |
| AC-5 | No-show tracking and progressive restriction functioning | Met | `NoShow`, `RestrictionTier` ladder, `Restriction`; forgive and lift in the console | `test_checkins.py::test_progressive_ladder`, `::test_thirty_day_pause_counts_a_sixty_day_window`, `::test_forgiving_lifts_every_stacked_automatic_restriction` |
| AC-6 | Utilisation and idle-capacity reports across at least three resource types | Met | `UtilisationSnapshot` and Insights; demo data has 10 resource types | `test_analytics.py::test_utilisation_by_each_dimension`, `::test_idle_capacity_ranking_surfaces_expensive_idle_kit_first`, `::test_snapshot_matches_the_hand_computed_day` |
| AC-7 | Recurring bookings created with correct per-occurrence conflict handling | Met | `bookings.preview_series` / `create_series` | `test_booking_engine.py::test_recurring_series_skips_a_mid_series_conflict`, `::test_preview_series_explains_each_date`; e2e `test_workflows.py::test_faculty_weekly_series_skips_the_clash` |

## P20 §15 Specific tests

| Test the brief names | Evidence |
|---|---|
| 500 concurrent attempts on the same slot produce exactly one booking | AC-1 |
| Timetable conflicts never offered as available | AC-2 |
| Auto-release fires correctly after the grace period | AC-4 |
| A recurring booking with a mid-series conflict handled correctly | AC-7 |
| Quota enforcement | `test_booking_engine.py::test_role_quota_in_hours`, `::test_department_quota_is_shared`, `::test_cancelled_bookings_do_not_count_against_quota` |

## P20 §5 Functional modules

| Module | Status | Implementation | Evidence |
|---|---|---|---|
| M1 Resource catalogue: types, attributes, images, capacity, features, custodians, location | Met | `apps/catalogue` (natural-language search on full-text and trigram) | `test_pages.py::test_find_understands_natural_language`; `test_api.py::test_resource_list_and_filters`; `test_console_setup.py::test_csv_import_preview_then_confirm_creates_all` |
| M2 Availability and rules: hours, booking windows, duration and lead time, blackouts, quotas | Met | `apps/rules` (most specific scope wins) | `test_rules_availability.py::test_policy_precedence_resource_over_type_over_campus`, `::test_blackout_scopes_and_exemptions`; `test_booking_engine.py::test_hours_blackout_duration_capacity_rules` |
| M3 Booking engine: conflict-free reservation with atomic slot claim | Met | `apps/bookings` | `test_booking_engine.py`, `test_state_machine.py`, `test_concurrency.py` |
| M4 Timetable integration: the published timetable as a hard constraint | Met | `apps/timetable` (CSV and API, atomic publish and republish) | `test_timetable.py::test_republish_supersedes_atomically`, `::test_publish_displaces_a_colliding_booking_and_tells_the_owner` |
| M5 Approval workflow: chains by resource type and requester role | Met | `apps/approvals` | `test_approvals.py` (19 tests) |
| M6 Check-in and auto-release: QR, grace period, release, check-out, no-show tracking | Met | `apps/checkins` | `test_checkins.py` (22 tests) |
| M7 Maintenance and downtime: scheduled maintenance, breakdown reporting, downtime | Met | `apps/maintenance` | `test_maintenance_inventory.py::test_maintenance_never_displaces_a_class`, `::test_critical_breakdown_takes_resource_offline_until_resolved`; `test_booking_engine.py::test_maintenance_claim_displaces_bookings` |
| M8 Consumables and accessories: stock, issue with booking, return | Met | `apps/inventory` | `test_maintenance_inventory.py::test_issue_on_check_in_and_return_on_check_out`, `::test_overlapping_bookings_cannot_overcommit_a_shared_pool` |
| M9 Analytics and reporting: utilisation, idle capacity, no-shows, demand against supply | Met | `apps/analytics` | `test_analytics.py` (19 tests), `test_insights.py` (15 tests) |

## P20 §6 User roles

| Role and rights in the brief | Status | Evidence |
|---|---|---|
| Student: browse and book permitted resources, check in, view own bookings | Met | [roles.md](roles.md); `test_pages.py::test_student_pages_render`; `test_api.py::test_list_is_scoped_to_what_the_user_may_see` |
| Faculty and staff: broader rights, recurring bookings, book on behalf of a class | Met | `test_booking_engine.py::test_faculty_can_book_for_a_class`, `::test_students_cannot_create_series` |
| Resource custodian: own resources' availability, approvals, maintenance, consumables | Met | `test_console_ops.py::test_board_shows_only_custodians_resources`, `::test_custodian_queue_is_scoped`, `::test_custodian_cannot_restock_elsewhere` |
| Department head: departmental quotas and utilisation | Met | `test_console_setup.py::test_dept_head_manages_only_own_department_quota`; `test_insights.py::test_dept_head_is_locked_to_their_department` |
| Facility manager: cross-campus utilisation, policy configuration | Met | `test_insights.py::test_facility_manager_sees_the_campus`; `test_console_setup.py::test_booking_policy_override_is_audited_and_applies` |
| Administrator: resource types, workflows, quota configuration | Met | `test_console_setup.py::test_console_renders_for_admin_and_facility_manager`, `::test_role_change_is_audited` |

## P20 §8 Technical requirements

| Requirement | Status | Implementation | Evidence |
|---|---|---|---|
| Resource search with facets and photographs | Met | Find page facets (type, block, capacity, features, time window); photos per type | `test_pages.py::test_find_with_window_hides_busy_resources` |
| Calendar view with drag-to-select | Met | `static/js/calendar.js` on the resource page | e2e `test_journeys.py::test_student_drags_on_the_calendar_and_gets_a_qr_pass` |
| Mobile check-in by QR scan | Met | `/scan/` camera scanner, door QR | AC-4 |
| Custodian approval queue | Met | `/manage/approvals/` | `test_console_ops.py::test_approve_via_view_confirms_booking` |
| Atomic slot reservation; double-booking structurally impossible | Met | AC-1 | AC-1 |
| Timetable as a hard constraint with automatic refresh on republication | Met | `timetable.publish` supersedes the previous version in one transaction | `test_timetable.py::test_republish_supersedes_atomically` |
| Auto-release job for bookings not checked into within the grace period | Met | Celery Beat `auto-release-no-shows`, every 60 s | AC-4 |
| Recurring bookings expanded with per-occurrence conflict handling | Met | AC-7 | AC-7 |
| Data model: ResourceType, Resource, ResourceAttribute, Custodian, AvailabilityRule, Blackout, Quota, Booking, BookingSlot, RecurrenceRule, ApprovalWorkflow, Approval, CheckIn, NoShow, MaintenanceWindow, Consumable, Issuance, UtilisationSnapshot | Met | Mapped entity by entity in [database.md](database.md#spec-entities-and-where-they-live) (RecurrenceRule is `BookingSeries`, Consumable is `InventoryItem`) | `makemigrations --check` in CI |
| API: `/resources`, `/resources/:id/availability`, `/bookings`, `/bookings/:id/approve`, `/bookings/:id/check-in`, `/maintenance`, `/analytics/utilisation` | Met | `/api/v1/...`, [openapi.yaml](openapi.yaml) | `test_api.py` (every endpoint including authorisation failures) |
| 500 concurrent booking attempts at peak with zero double-booking | Met | AC-1 | AC-1; [loadtest/README.md](../loadtest/README.md) |

## P20 §9 Admin dashboard

| Feature | Status | Where | Evidence |
|---|---|---|---|
| Resource catalogue with bulk import | Met | Resources, CSV import | `test_console_setup.py::test_csv_import_preview_then_confirm_creates_all`, `::test_csv_import_with_bad_rows_imports_nothing` |
| Availability rule and quota configuration | Met | Setup → Policies | `test_console_setup.py::test_hours_add_refuses_overlap`, `::test_blackout_create` |
| Approval workflow builder | Met | Setup → Workflows | `test_console_setup.py::test_workflow_tester_partial_and_dept_head_read_only` |
| Live booking board | Met | Manage → Board | `test_console_ops.py::test_board_htmx_refresh_returns_body_only`; `test_rules_availability.py::test_board_query_count_is_constant` |
| No-show monitor with restriction management | Met | No-shows | `test_console_ops.py::test_forgive_requires_reason_and_works`, `::test_lift_restriction_scoped_to_people_seen_on_your_resources` |
| Maintenance calendar | Met | Manage → Upkeep | `test_console_ops.py::test_schedule_preview_then_confirm_displaces_booking` |
| Utilisation heat map | Met | Insights | `test_analytics.py::test_heatmap` |
| Consumable stock alerts | Met | Manage → Stock, low-stock notifications | `test_console_ops.py::test_low_stock_filter`; `test_maintenance_inventory.py::test_low_stock_listing` |

## P20 §10 Reporting and analytics

| Report | Status | Evidence |
|---|---|---|
| Utilisation by resource, type, department and period | Met | `test_analytics.py::test_utilisation_by_each_dimension`, `::test_scope_filters` |
| Idle-capacity ranking | Met | `test_analytics.py::test_idle_capacity_ranking_surfaces_expensive_idle_kit_first` |
| No-show rate by user and resource | Met | `test_analytics.py::test_no_show_rates` |
| Demand against supply | Met | `test_analytics.py::test_demand_vs_supply_flags_types_that_turn_people_away` |
| Approval turnaround | Met | `test_analytics.py::test_approval_turnaround_and_pending_queue` |
| Maintenance downtime | Met | `test_analytics.py::test_maintenance_downtime` |
| Departmental quota consumption | Met | `test_analytics.py::test_department_quota_consumption` |

## P20 §11 Notifications

| Event | Status | Evidence |
|---|---|---|
| Booking confirmed; approval required; approved or rejected | Met | `test_approvals.py::test_two_step_chain_custodian_then_dept_head`, `::test_reject_needs_a_comment_frees_the_slot_and_skips_the_rest` |
| Reminder before start; check-in required with grace countdown | Met | `test_checkins.py::test_checkin_nudge_and_reminder_are_sent_once` |
| Auto-released | Met | `test_checkins.py::test_sweep_releases_exactly_after_the_grace_period` |
| Maintenance scheduled; resource unavailable | Met | `test_api.py::test_custodian_schedules_maintenance_and_displaces_bookings`; `test_timetable.py::test_publish_displaces_a_colliding_booking_and_tells_the_owner` |
| Channels: in-app and email | Partial | Email needs environment-driven SMTP (CFG-1); SMS not built (INT-4) |

## P20 §12 Integrations

| Integration | Status | Notes |
|---|---|---|
| P13 published timetable (essential) | Met | `POST /api/v1/timetable/publications/` and CSV; `test_api.py::test_publish_timetable` |
| ERP and SSO for identity and role | Not yet | INT-1 |
| Calendar export: iCal, Google, Outlook | Met | Per-booking `.ics` and a private subscription feed that Google and Outlook subscribe to; `test_pages.py::test_ics_export`, `::test_personal_feed_needs_the_token` |
| Door access and IoT occupancy (optional) | Not yet | INT-5, a v2 item |
| Email and SMS | Partial | INT-4, CFG-1 |

## P20 §13 and §17 Deliverables

| Deliverable | Status | Where |
|---|---|---|
| Seeded catalogue covering at least three resource types with real data | Met | `python manage.py seed_demo`: 10 types, 61 resources, 12 blocks |
| Written explanation of the conflict-prevention mechanism | Met | [booking-concurrency.md](booking-concurrency.md) |

## CES §1.3 Non-functional requirements

| Requirement | Status | Evidence or gap |
|---|---|---|
| 2,000 sustained and 5,000 peak concurrent users | Partial | Load-test scenario exists; no report against a deployed environment yet (OPS-8) |
| API p95 under 400 ms reads and 800 ms writes; dashboards under 3 s | Partial | Constant-query board and dashboards (`test_rules_availability.py::test_board_query_count_is_constant`, `test_insights.py::test_dashboard_query_count_is_bounded`); latency not yet measured on staging (OPS-8) |
| Availability 99.5%; daily backups with a tested restore | Partial | Probes `/health/` and `/ready/` (`test_health.py`); restore tested ([runbook](runbook.md#tested-restore-procedure)); scheduling not automated (OPS-2) |
| Seven-year retention, configurable per entity | Not yet | DATA-1 |
| WCAG 2.2 AA for all student-facing screens | Met | axe in Chromium, light and dark: `e2e/test_accessibility.py` |
| Last two versions of major browsers; responsive to 360 px | Met | e2e `test_journeys.py::test_no_horizontal_overflow_on_a_phone` |
| Internationalisation-ready, Hindi and Punjabi externalised | Partial | Shell, sign-in and home translated (`test_pages.py::test_hindi_and_punjabi_shell`); other screens in Phase 4 (UI-1) |

## CES §1.4 Security baseline

| Requirement | Status | Evidence or gap |
|---|---|---|
| OWASP Top 10 addressed and evidenced | Met | [security-review.md](security-review.md); `test_security.py` (136 tests, no open findings) |
| Input validation on every endpoint (Django forms, DRF serializers) | Met | `test_api.py` validation cases; `test_malformed_input.py` |
| Rate limiting per IP and per user; brute-force lockout | Met | `test_security.py` lockout and SEC-03/SEC-07 tests; DRF throttles |
| TLS 1.2+ in transit; encryption at rest | Partial | HSTS and secure cookies with `DEBUG=0`; at rest depends on the database host (Phase 6) |
| Field-level encryption for identity, health and financial fields | Partial | TOTP secret encrypted; `vid` and `phone` not (SEC-R4) |
| Immutable audit log of privileged actions (actor, action, target, before and after, time, IP) | Met | [ADR 0012](adr/0012-append-only-audit-trigger.md); `test_audit.py` |
| DPDP: purpose limitation, data-subject access and deletion | Partial | Access: `/me/export/` (`test_pages.py::test_data_export_contains_only_my_bookings`); deletion is administrator-handled (SEC-R3) |
| No personal data in logs or error messages | Met | Branded error pages; `test_health.py::test_check_database_reports_failure_without_leaking_details` |
| Dependency scanning (pip-audit), no High or Critical at handover | Met | CI `security` job |
| Upload validation, size caps, malware scanning, stored outside the web root, pre-signed URLs | Partial | Validation, caps and re-encoding (`test_console_setup.py::test_photo_upload_*`); no malware scanning (FS-3); serving and pre-signed URLs pending (FS-1, FS-2) |

## CES §1.5 Testing

| Type | Requirement | Status | Evidence |
|---|---|---|---|
| Unit | 70% or more statement coverage on domain and service layers | Met | 80% overall in CI; service modules 85% to 100% |
| Component | Every form and shared component | Met | `test_pages.py`, `test_console_setup.py`, `test_console_ops.py` |
| Integration | Every endpoint, including authorisation-failure paths | Met | `test_api.py`, including `::test_anonymous_requests_are_refused_on_every_endpoint` |
| End-to-end | Every critical journey in the acceptance criteria | Met | `tests/e2e/` (30 browser tests) |
| Load | Against the concurrency targets, report at M4 | Partial | `loadtest/`; report pending (OPS-8) |
| Security | OWASP ZAP baseline and pip-audit, clean at handover | Partial | pip-audit and gitleaks in CI; ZAP in Phase 3 (OPS-7) |
| Accessibility | axe-core in CI, zero critical violations on student pages | Met | `e2e/test_accessibility.py` |
| Concurrency | Explicit multi-process test wherever the spec names a guarantee | Met | `test_concurrency.py` |

## CES §1.6 Documentation

| Document | Where |
|---|---|
| README with one-command local setup | [README.md](../README.md) |
| Architecture decision records for every significant choice | [adr/](adr/README.md) |
| API specification | [openapi.yaml](openapi.yaml) |
| Database schema documentation with an ERD | [database.md](database.md) |
| Environment variable reference | [environment.md](environment.md) |
| Deployment and rollback runbook | [runbook.md](runbook.md) |
| Backup and restore procedure | [runbook.md](runbook.md#backup) |
| Role and permission matrix | [roles.md](roles.md) |
| Admin user guide | [guide-admin.md](guide-admin.md) |
| End-user quick-start guide | [guide-user.md](guide-user.md) |
| Known issues and technical debt register | [known-issues.md](known-issues.md) |
| Recorded handover walkthrough (60 to 90 minutes) | Not yet: recorded at handover |

## CES §1.7 Definition of done

| Item | Status |
|---|---|
| Merged to main via reviewed pull request; CI green | Met for Phase 1 (PR #2) |
| Tests written and passing; API specification updated; migrations committed and reversible | Met |
| Deployed to staging and demoed live | Not yet (OPS-1) |
| No High or Critical vulnerabilities; accessibility check on new screens | Met |
