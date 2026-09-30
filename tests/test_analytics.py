"""
M9 — analytics. One hand-computed Monday on Room 34-301 (open 08:00–20:00):

    09–10  timetabled class                                  class 60
    10–11  A: checked in 10:05, out 10:40 → shrunk to 10:00–10:40, 20 min handed back, used 35
    11–12  B: never checked in → no-show at 11:20, 40 min released (still 60 booked)
    12–13  C: checked in 12:00, auto-completed at 13:30        used 60
    14–15  maintenance window                                maintenance 60
    15–16  D: cancelled                                      not booked; 1 cancellation
    18–20  campus blackout                                   supply lost 120
    + 3 refused attempts (timetable, conflict, maintenance) and 1 "closed" (not unmet demand)

    open    = 720 − 60 class − 60 maintenance − 120 blackout = 480
    booked  = 40 + 60 + 60 = 160      used = 35 + 60 = 95      released = 20 + 40 = 60
    utilisation = (60 + 160) / (480 + 60) = 40.7 %

Room 34-302 and an ECE spectrometer (₹40 lakh) sit idle that Monday (open 600 each, blackout
applies campus-wide). On Tuesday Room 34-302 has one approved 10–12 booking.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from apps.accounts.models import Department, Role
from apps.analytics import services as analytics
from apps.analytics import tasks
from apps.analytics.models import UtilisationSnapshot
from apps.approvals import services as approvals
from apps.approvals.models import Approval, ApprovalStep, ApprovalWorkflow, Decision
from apps.bookings import services as bookings
from apps.bookings.models import Booking, BookingStatus, SlotKind
from apps.catalogue.models import Resource
from apps.checkins import services as checkins
from apps.core.errors import BookingRejected
from apps.core.models import SweepRun
from apps.core.timeutil import trange
from apps.maintenance import services as maintenance
from apps.rules.models import Blackout, Quota, QuotaPeriod, Scope

from .conftest import at

pytestmark = pytest.mark.django_db


def book(user, resource, d, h1, h2, now, **kw):
    return bookings.create_booking(
        requester=user,
        resource=resource,
        start=at(d, *h1),
        end=at(d, *h2),
        title="Study",
        now=now,
        notify=False,
        **kw,
    )


@pytest.fixture
def ece(lpu):
    return Department.objects.create(institution=lpu, code="ECE", name="Electronics & Communication")


@pytest.fixture
def spectrometer(lpu, lab_type, block34, ece):
    return Resource.objects.create(
        institution=lpu,
        type=lab_type,
        code="SPEC-1",
        name="Raman Spectrometer",
        capacity=4,
        building=block34,
        department=ece,
        acquisition_cost=Decimal("4000000.00"),
    )


@pytest.fixture
def scenario(lpu, room, room2, spectrometer, custodian, make_user, monday, now):
    u1, u2, u3 = make_user(), make_user(), make_user()
    bookings.claim_block(
        room,
        at(monday, 9),
        at(monday, 10),
        kind=SlotKind.CLASS,
        source_type="timetable_entry",
        source_id=1,
        label="CSE326 Lecture · K23KF",
    )
    maintenance.schedule(
        room, at(monday, 14), at(monday, 15), title="Projector swap", actor=custodian, enforce_permissions=False
    )
    a = book(u1, room, monday, (10,), (11,), now)
    b = book(u2, room, monday, (11,), (12,), now)
    c = book(u1, room, monday, (12,), (13,), now)
    d = book(u1, room, monday, (15,), (16,), now)
    bookings.cancel_booking(d, u1, now=now)
    for h1, h2 in [((9, 30), (10, 30)), ((10, 30), (11,)), ((14,), (14, 30)), ((7,), (8,))]:
        with pytest.raises(BookingRejected):
            book(u3, room, monday, h1, h2, now)
    Blackout.objects.create(
        institution=lpu, title="Convocation", scope=Scope.CAMPUS, period=trange(at(monday, 18), at(monday, 20))
    )

    checkins.check_in(a, u1, now=at(monday, 10, 5))
    checkins.check_out(a, u1, now=at(monday, 10, 40))
    assert [x.pk for x in checkins.sweep_no_shows(now=at(monday, 11, 20))] == [b.pk]
    checkins.check_in(c, u1, now=at(monday, 12))
    checkins.sweep_completed(now=at(monday, 13, 30))

    tuesday = monday + timedelta(days=1)
    book(u2, room2, tuesday, (10,), (12,), now)
    return {"users": (u1, u2, u3), "bookings": (a, b, c, d), "tuesday": tuesday}


def snap(resource, day):
    return UtilisationSnapshot.objects.get(resource=resource, date=day)


# ── Snapshots ───────────────────────────────────────────────────────────────


def test_snapshot_matches_the_hand_computed_day(scenario, room, monday):
    s = analytics.build_snapshot(room, monday)
    assert (s.open_minutes, s.class_minutes, s.maintenance_minutes) == (480, 60, 60)
    assert (s.booked_minutes, s.used_minutes, s.released_minutes) == (160, 95, 60)
    assert (s.bookings, s.no_shows, s.cancellations, s.denied_attempts) == (3, 1, 1, 3)
    assert s.hourly_booked == [0] * 9 + [60, 40, 60, 60] + [0] * 11
    assert round(s.utilisation * 100, 1) == 40.7
    assert s.idle_minutes == 320


def test_idle_resources_and_campus_blackout(scenario, room2, spectrometer, monday):
    analytics.build_snapshots(monday)
    for r in (room2, spectrometer):
        s = snap(r, monday)
        assert (s.open_minutes, s.booked_minutes, s.bookings) == (600, 0, 0)
        assert s.hourly_booked == [0] * 24


def test_build_snapshots_is_idempotent_and_bulk(scenario, room, room2, monday, lpu):
    assert analytics.build_snapshots(monday, institution_id=lpu.pk) == 3
    first = {
        s.resource_id: (s.open_minutes, s.booked_minutes, s.hourly_booked) for s in UtilisationSnapshot.objects.all()
    }
    assert analytics.build_snapshots(monday, institution_id=lpu.pk) == 3
    assert UtilisationSnapshot.objects.count() == 3
    again = {
        s.resource_id: (s.open_minutes, s.booked_minutes, s.hourly_booked) for s in UtilisationSnapshot.objects.all()
    }
    assert again == first
    # the single-resource builder upserts the same row
    analytics.build_snapshot(room, monday)
    assert UtilisationSnapshot.objects.filter(resource=room, date=monday).count() == 1

    # a later change is picked up by a rebuild (update in place, not a duplicate)
    Booking.objects.filter(resource=room2).update(status=BookingStatus.CANCELLED)
    book(scenario["users"][2], room2, monday, (16,), (17,), at(monday, 9))
    analytics.build_snapshots(monday, institution_id=lpu.pk)
    assert snap(room2, monday).booked_minutes == 60
    assert UtilisationSnapshot.objects.count() == 3


def test_query_count_does_not_grow_with_resources(scenario, lpu, room_type, monday, django_assert_max_num_queries):
    with django_assert_max_num_queries(8):
        analytics.build_snapshots(monday)
    for i in range(15):
        Resource.objects.create(institution=lpu, type=room_type, code=f"X-{i}", name=f"Room X{i}", capacity=10)
    with django_assert_max_num_queries(8):
        assert analytics.build_snapshots(monday) == 18


def test_retired_and_unbookable_resources_are_not_reported(scenario, room2, spectrometer, monday):
    room2.status = "retired"
    room2.save()
    spectrometer.is_bookable = False
    spectrometer.save()
    assert analytics.build_snapshots(monday) == 1


def test_backfill_covers_every_day(scenario, room2, monday):
    assert analytics.backfill(monday, scenario["tuesday"]) == 6
    s = snap(room2, scenario["tuesday"])
    assert (s.open_minutes, s.booked_minutes, s.used_minutes, s.bookings) == (720, 120, 0, 1)
    assert s.hourly_booked[10:12] == [60, 60]


def test_celery_task_builds_yesterday_and_records_the_sweep(scenario, monday, lpu):
    assert tasks.build_snapshots(monday.isoformat()) == 3
    run = SweepRun.objects.get(task="analytics.build_snapshots")
    assert run.ok and run.affected == 3
    tasks.build_snapshots()  # default: yesterday — must not fail on an empty day
    assert SweepRun.objects.filter(task="analytics.build_snapshots").count() == 2


# ── Dashboards ──────────────────────────────────────────────────────────────


@pytest.fixture
def built(scenario, monday):
    analytics.backfill(monday, scenario["tuesday"])
    return scenario


def test_overview_kpis(built, lpu, room, monday):
    o = analytics.overview(lpu.pk, monday, monday)
    # open 480 + 600 + 600; class 60; booked 160; used 95; idle 320 + 600 + 600
    assert o["open_hours"] == 28.0
    assert o["booked_hours"] == 2.7
    assert o["used_hours"] == 1.6
    assert o["idle_hours"] == 25.3
    assert o["utilisation_pct"] == 12.6  # 220 / 1740
    assert o["realised_pct"] == 8.9  # 155 / 1740
    assert (o["bookings"], o["no_shows"], o["no_show_rate_pct"]) == (3, 1, 33.3)
    assert (o["cancellations"], o["denied_attempts"], o["resources"], o["days"]) == (1, 3, 3, 1)
    assert o["pending_approvals"] == 0
    assert o["avg_turnaround_hours"] is None
    assert o["top_resource"]["key"] == room.pk
    assert o["top_resource"]["utilisation_pct"] == 40.7


def test_scope_filters(built, lpu, ece, cse, lab_type, spectrometer, monday):
    o = analytics.overview(lpu.pk, monday, monday, department_id=ece.pk)
    assert (o["resources"], o["open_hours"], o["booked_hours"]) == (1, 10.0, 0.0)
    assert o["top_resource"]["key"] == spectrometer.pk
    o = analytics.overview(lpu.pk, monday, monday, department_id=cse.pk)
    assert (o["resources"], o["booked_hours"]) == (2, 2.7)
    assert analytics.overview(lpu.pk, monday, monday, resource_type_id=lab_type.pk)["resources"] == 1


def test_utilisation_by_each_dimension(built, lpu, room, room_type, cse, block34, monday):
    rows = analytics.utilisation_by("resource", lpu.pk, monday, monday)
    assert [r["key"] for r in rows][0] == room.pk
    assert rows[0]["utilisation_pct"] == 40.7 and rows[0]["idle_hours"] == 5.3
    types = {r["label"]: r for r in analytics.utilisation_by("type", lpu.pk, monday, monday)}
    assert types["Classroom"]["key"] == room_type.pk
    assert types["Classroom"]["resources"] == 2
    assert types["Classroom"]["utilisation_pct"] == 19.3  # 220 / (1080 + 60)
    assert types["Computer Lab"]["utilisation_pct"] == 0.0
    depts = {r["key"]: r for r in analytics.utilisation_by("department", lpu.pk, monday, monday)}
    assert depts[cse.pk]["booked_hours"] == 2.7
    buildings = analytics.utilisation_by("building", lpu.pk, monday, monday)
    assert [(b["key"], b["resources"]) for b in buildings] == [(block34.pk, 3)]
    with pytest.raises(ValueError):
        analytics.utilisation_by("colour", lpu.pk, monday, monday)


def test_idle_capacity_ranking_surfaces_expensive_idle_kit_first(built, lpu, room, room2, spectrometer, monday):
    rows = analytics.idle_capacity_ranking(lpu.pk, monday, monday)
    assert [r["resource_id"] for r in rows] == [spectrometer.pk, room2.pk, room.pk]
    top = rows[0]
    assert top["acquisition_cost"] == 4000000.0
    assert (top["idle_hours"], top["idle_pct"], top["idle_cost_score"]) == (10.0, 100.0, 40000000.0)
    assert rows[2]["idle_hours"] == 5.3 and rows[2]["acquisition_cost"] is None
    assert len(analytics.idle_capacity_ranking(lpu.pk, monday, monday, limit=1)) == 1


def test_heatmap(built, lpu, monday):
    h = analytics.heatmap(lpu.pk, monday, built["tuesday"])
    assert [r["label"] for r in h["rows"]] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    mon, tue = h["rows"][monday.weekday()], h["rows"][built["tuesday"].weekday()]
    assert mon["minutes"][9:13] == [60, 40, 60, 60] and mon["total"] == 220
    assert tue["minutes"][10:12] == [60, 60] and tue["total"] == 120
    assert (h["max"], h["total"]) == (60, 340)
    assert all(len(r["minutes"]) == 24 for r in h["rows"])


def test_no_show_rates(built, lpu, room, monday):
    _, u2, _ = built["users"]
    r = analytics.no_show_rates(lpu.pk, monday, built["tuesday"])
    assert r["overall"] == {"bookings": 4, "no_shows": 1, "rate_pct": 25.0}
    assert [(u["user_id"], u["bookings"], u["no_shows"], u["rate_pct"]) for u in r["by_user"]] == [(u2.pk, 2, 1, 50.0)]
    assert r["by_user"][0]["name"] == u2.get_full_name()
    assert [(x["resource_id"], x["bookings"], x["no_shows"], x["rate_pct"]) for x in r["by_resource"]] == [
        (room.pk, 3, 1, 33.3)
    ]


def test_demand_vs_supply_flags_types_that_turn_people_away(built, lpu, room_type, monday):
    rows = analytics.demand_vs_supply(lpu.pk, monday, monday)
    assert rows[0]["type_id"] == room_type.pk
    assert (rows[0]["bookings"], rows[0]["denied_attempts"], rows[0]["demand"]) == (3, 3, 6)
    assert rows[0]["denial_rate_pct"] == 50.0
    assert rows[0]["needs_capacity"] is True
    assert rows[1]["type"] == "Computer Lab" and rows[1]["needs_capacity"] is False


def test_maintenance_downtime(built, lpu, room, room_type, monday):
    m = analytics.maintenance_downtime(lpu.pk, monday, built["tuesday"])
    assert (m["total_hours"], m["lost_open_hours"], m["windows"]) == (1.0, 1.0, 1)
    assert m["by_resource"] == [
        {
            "resource_id": room.pk,
            "name": room.name,
            "type": "Classroom",
            "hours": 1.0,
            "windows": 1,
            "lost_open_hours": 1.0,
        }
    ]
    assert m["by_type"][0]["type_id"] == room_type.pk and m["by_type"][0]["resources"] == 1
    # windows are clipped to the date range: a range without Monday sees no downtime
    assert analytics.maintenance_downtime(lpu.pk, built["tuesday"], built["tuesday"])["total_hours"] == 0.0


def test_daily_series_fills_gaps(built, lpu, monday):
    wed = built["tuesday"] + timedelta(days=1)
    series = analytics.daily_series(lpu.pk, monday, wed)
    assert [d["date"] for d in series] == [monday, built["tuesday"], wed]
    assert (series[0]["booked_hours"], series[0]["used_hours"], series[0]["no_shows"]) == (2.7, 1.6, 1)
    assert (series[1]["booked_hours"], series[1]["bookings"], series[1]["utilisation_pct"]) == (2.0, 1, 5.6)
    assert series[2] == {
        "date": wed,
        "open_hours": 0.0,
        "class_hours": 0.0,
        "booked_hours": 0.0,
        "used_hours": 0.0,
        "bookings": 0,
        "no_shows": 0,
        "cancellations": 0,
        "denied_attempts": 0,
        "utilisation_pct": 0.0,
    }


def test_department_quota_consumption(built, lpu, cse, ece, room_type, monday):
    Quota.objects.create(
        institution=lpu,
        name="CSE rooms",
        department=cse,
        resource_type=room_type,
        period=QuotaPeriod.WEEK,
        max_hours=10,
    )
    Quota.objects.create(institution=lpu, name="ECE labs", department=ece, period=QuotaPeriod.WEEK, max_bookings=5)
    Quota.objects.create(institution=lpu, name="Student cap", role=Role.STUDENT, max_hours=4)  # not departmental
    rows = analytics.department_quota_consumption(lpu.pk, monday, monday, at=at(monday, 12))
    assert [r["name"] for r in rows] == ["CSE rooms", "ECE labs"]
    cse_row = rows[0]
    # completed A (40) + completed C (60) + approved Tuesday 10–12 (120); no-show and cancelled don't count
    assert (cse_row["hours_used"], cse_row["max_hours"], cse_row["hours_pct"]) == (3.7, 10.0, 37)
    assert (cse_row["bookings_used"], cse_row["bookings_pct"], cse_row["pct"]) == (3, None, 37)
    assert cse_row["department_code"] == "CSE" and cse_row["resource_type"] == "Classroom"
    assert cse_row["window_start"] == at(monday, 0)
    assert rows[1]["bookings_used"] == 0 and rows[1]["pct"] == 0
    only_ece = analytics.department_quota_consumption(lpu.pk, monday, monday, department_id=ece.pk, at=at(monday, 12))
    assert [r["name"] for r in only_ece] == ["ECE labs"]


def test_approval_turnaround_and_pending_queue(
    lpu, lab_type, spectrometer, student, facility_manager, monday, now, room_type
):
    wf = ApprovalWorkflow.objects.create(institution=lpu, name="Lab sign-off", resource_type=lab_type)
    ApprovalStep.objects.create(workflow=wf, order=1, approver_role="facility_manager")
    first = book(student, spectrometer, monday, (10,), (11,), now)
    second = book(student, spectrometer, monday, (14,), (15,), now)
    assert first.status == second.status == BookingStatus.PENDING
    Booking.objects.filter(pk__in=[first.pk, second.pk]).update(created_at=now)
    step = Approval.objects.get(booking=first, decision=Decision.PENDING)
    approvals.decide(step, facility_manager, approve=True, now=now + timedelta(hours=3))

    week = (now.date() - timedelta(days=1), monday)
    t = analytics.approval_turnaround(lpu.pk, *week)
    assert (t["avg_hours"], t["decided"], t["approved"], t["rejected"]) == (3.0, 1, 1, 0)
    assert t["pending_now"] == 1
    assert t["by_type"] == [{"type_id": lab_type.pk, "type": "Computer Lab", "avg_hours": 3.0, "decided": 1}]
    assert analytics.approval_turnaround(lpu.pk, *week, resource_type_id=room_type.pk)["decided"] == 0

    o = analytics.overview(lpu.pk, *week)
    assert (o["pending_approvals"], o["avg_turnaround_hours"]) == (1, 3.0)


def test_dashboards_are_empty_safe(lpu, monday):
    assert analytics.overview(lpu.pk, monday, monday)["utilisation_pct"] == 0.0
    assert analytics.overview(lpu.pk, monday, monday)["top_resource"] is None
    assert analytics.utilisation_by("type", lpu.pk, monday, monday) == []
    assert analytics.idle_capacity_ranking(lpu.pk, monday, monday) == []
    assert analytics.heatmap(lpu.pk, monday, monday)["max"] == 0
    assert analytics.no_show_rates(lpu.pk, monday, monday)["overall"]["rate_pct"] == 0.0
    assert analytics.demand_vs_supply(lpu.pk, monday, monday) == []
    assert analytics.maintenance_downtime(lpu.pk, monday, monday)["by_type"] == []
    assert analytics.department_quota_consumption(lpu.pk, monday, monday) == []
    assert len(analytics.daily_series(lpu.pk, monday, monday + timedelta(days=6))) == 7
