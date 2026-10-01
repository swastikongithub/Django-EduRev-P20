"""M2 rules precedence and the calendar's explained states (every cell says why)."""

from datetime import time, timedelta

import pytest

from apps.bookings import availability
from apps.bookings import services as bookings
from apps.bookings.models import SlotKind
from apps.catalogue.models import Resource
from apps.checkins.models import Restriction
from apps.rules import services as rules
from apps.rules.models import AvailabilityRule, Blackout, BookingPolicy, Scope

from .conftest import at

pytestmark = pytest.mark.django_db


def cell(sched, d, hh, mm=0):
    return next(c for c in sched.cells if c.start == at(d, hh, mm))


def test_policy_precedence_resource_over_type_over_campus(lpu, room, room2, lab_type, block34):
    BookingPolicy.objects.create(institution=lpu, scope=Scope.CAMPUS, max_duration_minutes=60)
    BookingPolicy.objects.create(institution=lpu, scope=Scope.RESOURCE, resource=room, max_duration_minutes=240)
    lab = Resource.objects.create(institution=lpu, type=lab_type, code="L1", name="Lab", building=block34)
    assert rules.policy_for(room).max_duration_minutes == 240  # resource override
    assert rules.policy_for(room2).max_duration_minutes == 180  # type policy (conftest)
    assert rules.policy_for(lab).max_duration_minutes == 60  # campus default
    bulk = rules.policies_for([room, room2, lab])
    assert [bulk[r.pk].max_duration_minutes for r in (room, room2, lab)] == [240, 180, 60]


def test_built_in_default_when_nothing_configured(lpu, lab_type, block34):
    lab = Resource.objects.create(institution=lpu, type=lab_type, code="L2", name="Lab 2", building=block34)
    assert rules.policy_for(lab) == rules.EffectivePolicy()


def test_opening_hours_most_specific_scope_wins(lpu, room, room2):
    AvailabilityRule.objects.create(
        institution=lpu, scope=Scope.RESOURCE, resource=room, weekday=0, opens=time(10), closes=time(12)
    )
    hours = rules.weekly_hours_for([room, room2])
    assert hours[room.pk] == {0: [(time(10), time(12))]}  # resource rules replace the type's whole week
    assert hours[room2.pk][0] == [(time(8), time(20))]


def test_blackout_scopes_and_exemptions(lpu, room, room2, block34, student, faculty, monday, now):
    from apps.core.timeutil import trange

    day = trange(at(monday, 0), at(monday + timedelta(days=1), 0))
    Blackout.objects.create(
        institution=lpu,
        title="Block 34 audit",
        scope=Scope.CAMPUS,
        building=block34,
        period=day,
        exempt_roles=["faculty"],
    )
    assert rules.blackouts_for(room, at(monday, 10), at(monday, 11))
    assert availability.day(room, monday, student, now=now).cells[6].state == availability.BLACKOUT
    # Faculty are exempt from this one: the same slot is free for them.
    assert cell(availability.day(room2, monday, faculty, now=now), monday, 10).state == availability.FREE
    assert bookings.create_booking(
        requester=faculty, resource=room, start=at(monday, 10), end=at(monday, 11), title="ok", now=now, notify=False
    )


def test_every_cell_state_has_a_reason(lpu, room, student, make_user, custodian, monday, now):
    other = make_user()
    bookings.create_booking(
        requester=other,
        resource=room,
        start=at(monday, 9),
        end=at(monday, 10),
        title="Secret plan",
        now=now,
        notify=False,
    )
    bookings.create_booking(
        requester=student, resource=room, start=at(monday, 10), end=at(monday, 11), title="Mine", now=now, notify=False
    )
    bookings.claim_block(
        room,
        at(monday, 11),
        at(monday, 12),
        kind=SlotKind.CLASS,
        source_type="timetable_entry",
        source_id=7,
        label="CSE326 Lecture",
    )
    bookings.claim_block(
        room,
        at(monday, 12),
        at(monday, 13),
        kind=SlotKind.MAINTENANCE,
        source_type="maintenance_window",
        source_id=7,
        label="Projector swap",
    )
    s = availability.day(room, monday, student, now=now)
    assert (cell(s, monday, 9).state, cell(s, monday, 9).reason) == (availability.BOOKED, "Booked")  # no title leak
    assert cell(s, monday, 10).state == availability.MINE
    assert (cell(s, monday, 11).state, cell(s, monday, 11).reason) == (availability.CLASS, "CSE326 Lecture")
    assert (cell(s, monday, 12).state, cell(s, monday, 12).reason) == (availability.MAINTENANCE, "Projector swap")
    assert cell(s, monday, 14).state == availability.FREE
    # The custodian sees what the booking is for.
    assert cell(availability.day(room, monday, custodian, now=now), monday, 9).reason == "Secret plan"


def test_past_lead_beyond_restricted_and_closed_states(lpu, room, student, monday, now):
    BookingPolicy.objects.filter(resource_type=room.type).update(lead_time_minutes=120, max_advance_days=3)
    friday = (now - timedelta(hours=9)).date()  # `now` is Friday 09:00
    s = availability.day(room, friday, student, now=now)
    assert cell(s, friday, 8).state == availability.PAST
    assert cell(s, friday, 10).state == availability.LEAD and "notice" in cell(s, friday, 10).reason
    assert cell(s, friday, 12).state == availability.FREE
    later = monday + timedelta(days=2)  # beyond the 3-day window
    assert cell(availability.day(room, later, student, now=now), later, 10).state == availability.BEYOND
    sunday = monday - timedelta(days=1)
    assert availability.day(room, sunday, student, now=now).is_open is False
    Restriction.objects.create(
        institution=lpu,
        user=student,
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(days=7),
        reason="3 no-shows",
    )
    assert cell(availability.day(room, monday, student, now=now), monday, 10).state == availability.RESTRICTED


def test_forbidden_type_is_explained(lpu, room, student, now, monday):
    room.type.allowed_roles = ["faculty"]
    room.type.save()
    c = cell(availability.day(room, monday, student, now=now), monday, 10)
    assert c.state == availability.FORBIDDEN and "faculty" in c.reason


def test_out_of_service_is_explained(room, student, monday, now):
    Resource.objects.filter(pk=room.pk).update(status="out_of_service", status_note="Flooded")
    room.refresh_from_db()
    c = cell(availability.day(room, monday, student, now=now), monday, 10)
    assert (c.state, c.reason) == (availability.OUT_OF_SERVICE, "Flooded")


def test_board_matches_single_resource_schedules(room, room2, student, custodian, monday, now):
    bookings.create_booking(
        requester=student, resource=room, start=at(monday, 9), end=at(monday, 10), title="x", now=now, notify=False
    )
    for viewer in (student, custodian):
        rows = dict(availability.board([room, room2], monday, viewer, now=now))
        for r in (room, room2):
            single = availability.day(r, monday, viewer, now=now, window=(time(7), time(22)))
            assert [(c.state, c.reason) for c in rows[r].cells] == [(c.state, c.reason) for c in single.cells]


def test_board_query_count_is_constant(
    room, room2, student, monday, now, django_assert_max_num_queries, lpu, room_type
):
    many = [Resource.objects.create(institution=lpu, type=room_type, code=f"X{i}", name=f"X{i}") for i in range(15)]
    resources = list(
        Resource.objects.select_related("type", "building").filter(pk__in=[r.pk for r in [room, room2, *many]])
    )
    with django_assert_max_num_queries(10):
        availability.board(resources, monday, student, now=now)
