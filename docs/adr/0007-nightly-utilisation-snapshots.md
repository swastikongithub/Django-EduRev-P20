# 0007. Nightly UtilisationSnapshot aggregation

- Status: accepted
- Related: P20 §9, §10, §22; CES §1.3 (dashboards under 3 s)

## Context

P20 asks for utilisation by resource, type, department and period, idle-capacity ranking,
no-show rates, demand against supply, approval turnaround, maintenance downtime, departmental
quota consumption and a heat map. Utilisation needs interval arithmetic per resource per day:
opening hours minus blackouts minus maintenance minus classes, unions of bookings, checked-in
time, released time. Computing that live for 61 resources over 90 days on every dashboard view
would be slow and repeated. CES §1.3 wants interactive dashboards under 3 s.

## Decision

- `analytics.UtilisationSnapshot` holds one row per resource per local day: `open_minutes`
  (bookable supply), `class_minutes`, `maintenance_minutes`, `booked_minutes`,
  `used_minutes`, `released_minutes`, counts of bookings, no-shows, cancellations and denied
  attempts, and 24 hourly buckets. Definitions are in the `apps/analytics/services.py`
  docstring.
- `analytics.build_snapshots` runs at 01:15 for yesterday, as an idempotent upsert
  (`uniq_snapshot_resource_date`). The ops page's "Run now" rebuilds yesterday; calling the
  task with `day="YYYY-MM-DD"` rebuilds any day, and `services.backfill()` fills a range.
- Dashboards are `GROUP BY` queries over snapshots. Facts a snapshot cannot carry (who
  no-showed, approval timings, quota windows) read live tables.
- Utilisation = (class + booked) / (open + class), capped at 100 %. Realised utilisation uses
  used minutes. Idle capacity is open minutes not booked, ranked by asset cost.
- The Insights page caches each scope's computed report for five minutes in the Django cache.

## Consequences

- Dashboard query count is bounded and independent of the number of resources
  (`tests/test_analytics.py::test_query_count_does_not_grow_with_resources`,
  `tests/test_insights.py::test_dashboard_query_count_is_bounded`).
- Snapshot arithmetic is verified against a hand-computed day
  (`test_snapshot_matches_the_hand_computed_day`).
- Insights show data up to yesterday. Today's activity appears after the nightly run.
- Changing a definition requires rebuilding past snapshots (`backfill`).
- Snapshots must be rebuilt for a day if history is edited after the fact (for example
  correcting a past booking directly in the database).

## Alternatives considered

- **Live SQL over bookings and slots per request.** Rejected: complex range arithmetic in
  SQL, repeated per view, and unbounded cost as history grows.
- **Materialised views refreshed nightly.** Viable, but the interval logic (opening hours by
  scope, blackout scoping) is clearer and testable in Python; the result is equivalent.
- **External analytics store.** Rejected: unnecessary at this scale and a second system to run.
