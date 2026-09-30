from datetime import time, timedelta

import pytest
from django.db import IntegrityError, transaction

from apps.bookings import availability
from apps.bookings import services as bookings
from apps.bookings.models import Booking, BookingSlot, BookingStatus, SlotKind
from apps.core.errors import BookingRejected, NotPermitted, SlotUnavailable
from apps.core.timeutil import trange
from apps.rules.models import Blackout, Quota, Scope

from .conftest import at

pytestmark = pytest.mark.django_db


def book(user, room, d, h1, h2, now, **kw):
    return bookings.create_booking(
        requester=user, resource=room, start=at(d, *h1), end=at(d, *h2), title="Study", now=now, notify=False, **kw
    )


def test_confirmed_booking_claims_the_ledger(student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    assert b.status == BookingStatus.APPROVED
    assert BookingSlot.objects.get(booking=b).kind == SlotKind.BOOKING
    assert b.reference.startswith("LR-")


def test_overlap_is_rejected_with_a_reason(student, make_user, room, monday, now):
    book(student, room, monday, (10,), (11,), now)
    with pytest.raises(SlotUnavailable) as exc:
        book(make_user(), room, monday, (10, 30), (11, 30), now)
    assert "Already booked 10:00–11:00" in exc.value.message


def test_back_to_back_is_allowed(student, make_user, room, monday, now):
    book(student, room, monday, (10,), (11,), now)
    assert book(make_user(), room, monday, (11,), (12,), now).status == BookingStatus.APPROVED


def test_same_time_different_room_is_allowed(student, make_user, room, room2, monday, now):
    book(student, room, monday, (10,), (11,), now)
    assert book(make_user(), room2, monday, (10,), (11,), now)


def test_database_refuses_overlap_even_without_the_service(student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    clone = Booking(
        institution_id=b.institution_id,
        resource=room,
        requester=student,
        booked_for=student,
        title="raw",
        period=trange(at(monday, 10, 30), at(monday, 12)),
        status=BookingStatus.APPROVED,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        clone.save()


def test_cancelled_booking_frees_the_slot(student, make_user, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    bookings.cancel_booking(b, student, reason="plans changed", now=now)
    b.refresh_from_db()
    assert b.status == BookingStatus.CANCELLED
    assert not BookingSlot.objects.filter(booking=b).exists()
    assert book(make_user(), room, monday, (10,), (11,), now)


def test_other_student_cannot_cancel(student, make_user, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    with pytest.raises(NotPermitted):
        bookings.cancel_booking(b, make_user(), now=now)


def test_timetable_block_is_a_hard_conflict(student, room, monday, now):
    bookings.claim_block(
        room,
        at(monday, 9),
        at(monday, 10),
        kind=SlotKind.CLASS,
        source_type="timetable_entry",
        source_id=1,
        label="CSE326 Lecture · K23KF",
    )
    with pytest.raises(SlotUnavailable) as exc:
        book(student, room, monday, (9, 30), (10, 30), now)
    assert exc.value.code == "timetable"
    assert "CSE326" in exc.value.message


def test_timetable_slots_are_never_offered(student, room, monday, now):
    bookings.claim_block(
        room,
        at(monday, 9),
        at(monday, 10),
        kind=SlotKind.CLASS,
        source_type="timetable_entry",
        source_id=1,
        label="CSE326 Lecture",
    )
    sched = availability.day(room, monday, student, now=now)
    nine = [c for c in sched.cells if c.start in (at(monday, 9), at(monday, 9, 30))]
    assert {c.state for c in nine} == {availability.CLASS}
    assert all(not c.selectable for c in nine)


def test_hours_blackout_duration_capacity_rules(student, room, monday, now, lpu):
    with pytest.raises(BookingRejected, match="open 08:00–20:00"):
        book(student, room, monday, (7,), (8,), now)
    with pytest.raises(BookingRejected, match="limited to 3h"):
        book(student, room, monday, (9,), (13,), now)
    with pytest.raises(BookingRejected, match="holds 60"):
        book(student, room, monday, (9,), (10,), now, attendees=61)
    with pytest.raises(BookingRejected, match="30-minute boundaries"):
        bookings.create_booking(
            requester=student,
            resource=room,
            start=at(monday, 9, 10),
            end=at(monday, 10),
            title="x",
            now=now,
            notify=False,
        )
    Blackout.objects.create(
        institution=lpu,
        title="Diwali break",
        scope=Scope.CAMPUS,
        period=trange(at(monday, 0), at(monday + timedelta(days=1), 0)),
    )
    with pytest.raises(BookingRejected, match="Diwali break") as exc:
        book(student, room, monday, (10,), (11,), now)
    assert exc.value.code == "blackout"


def test_student_cannot_book_on_behalf(student, make_user, room, monday, now):
    with pytest.raises(NotPermitted):
        book(student, room, monday, (10,), (11,), now, booked_for=make_user())
    with pytest.raises(NotPermitted):
        book(student, room, monday, (10,), (11,), now, group_label="K23KF")


def test_faculty_can_book_for_a_class(faculty, room, monday, now):
    b = book(faculty, room, monday, (10,), (11,), now, group_label="K23KF · CSE326 extra lab", attendees=55)
    assert b.group_label.startswith("K23KF")


def test_role_quota_in_hours(student, room, room2, monday, now, lpu):
    Quota.objects.create(institution=lpu, name="Student weekly", role="student", period="week", max_hours=2)
    book(student, room, monday, (10,), (11,), now)
    book(student, room2, monday, (12,), (13,), now)
    with pytest.raises(BookingRejected) as exc:
        book(student, room, monday + timedelta(days=1), (10,), (10, 30), now)
    assert exc.value.code == "quota"


def test_department_quota_is_shared(student, make_user, room, room2, monday, now, lpu, cse):
    Quota.objects.create(institution=lpu, name="CSE rooms", department=cse, period="week", max_bookings=2)
    book(student, room, monday, (10,), (11,), now)
    book(make_user(), room2, monday, (10,), (11,), now)
    with pytest.raises(BookingRejected, match="CSE department"):
        book(make_user(), room, monday, (14,), (15,), now)


def test_cancelled_bookings_do_not_count_against_quota(student, room, monday, now, lpu):
    Quota.objects.create(institution=lpu, name="One a day", role="student", period="day", max_bookings=1)
    b = book(student, room, monday, (10,), (11,), now)
    bookings.cancel_booking(b, student, now=now)
    assert book(student, room, monday, (12,), (13,), now)


def test_recurring_series_skips_a_mid_series_conflict(faculty, student, room, monday, now):
    # Someone already holds the third Monday.
    book(student, room, monday + timedelta(weeks=2), (10,), (11,), now)
    series, created, skipped = bookings.create_series(
        requester=faculty,
        resource=room,
        title="DSA tutorial",
        frequency="weekly",
        interval=1,
        weekdays=[0],
        start_date=monday,
        until_date=monday + timedelta(weeks=4),
        start_time=time(10),
        end_time=time(11),
        attendees=40,
    )
    assert len(created) == 4
    assert len(skipped) == 1
    assert skipped[0]["code"] == "conflict"
    assert series.created_count == 4
    assert all(b.series_id == series.pk for b in created)


def test_students_cannot_create_series(student, room, monday):
    with pytest.raises(NotPermitted):
        bookings.create_series(
            requester=student,
            resource=room,
            title="x",
            frequency="weekly",
            interval=1,
            weekdays=[0],
            start_date=monday,
            until_date=monday + timedelta(weeks=2),
            start_time=time(10),
            end_time=time(11),
        )


def test_preview_series_explains_each_date(faculty, student, room, room2, monday, now):
    book(student, room, monday + timedelta(weeks=1), (10,), (11,), now)
    occ = bookings.expand_occurrences(
        frequency="weekly",
        interval=1,
        weekdays=[0],
        start_date=monday,
        until_date=monday + timedelta(weeks=2),
        start_time=time(10),
        end_time=time(11),
    )
    plans = bookings.preview_series(requester=faculty, resource=room, occurrences=occ)
    assert [p.ok for p in plans] == [True, False, True]
    assert plans[1].alternatives == [room2]


def test_maintenance_claim_displaces_bookings(student, custodian, room, monday, now):
    from apps.maintenance import services as maintenance

    b = book(student, room, monday, (10,), (11,), now)
    w = maintenance.schedule(room, at(monday, 9), at(monday, 12), title="Projector swap", actor=custodian)
    b.refresh_from_db()
    assert b.status == BookingStatus.CANCELLED
    assert w.displaced_bookings == 1
    with pytest.raises(SlotUnavailable) as exc:
        book(student, room, monday, (11,), (12,), now)
    assert exc.value.code == "maintenance"


def test_student_cannot_schedule_maintenance(student, room, monday):
    from apps.maintenance import services as maintenance

    with pytest.raises(NotPermitted):
        maintenance.schedule(room, at(monday, 9), at(monday, 12), title="x", actor=student)
