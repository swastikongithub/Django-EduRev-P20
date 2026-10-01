"""M4: the published timetable as a hard constraint (P20 §8, §15, acceptance criterion 2)."""

from datetime import time, timedelta

import pytest

from apps.bookings import availability
from apps.bookings import services as bookings
from apps.bookings.models import BookingSlot, BookingStatus, SlotKind
from apps.core.errors import BookingRejected, NotPermitted, SlotUnavailable
from apps.notifications.models import Kind, Notification
from apps.timetable import services as tt
from apps.timetable.models import AcademicTerm, PublicationStatus

from .conftest import at

pytestmark = pytest.mark.django_db

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@pytest.fixture
def term(lpu, monday):
    return AcademicTerm.objects.create(
        institution=lpu,
        code="26271",
        name="2026-27 Odd",
        starts=monday - timedelta(days=30),
        ends=monday + timedelta(days=27),
    )


def csv_for(room, monday, rows):
    lines = ["room_code,day,start,end,course_code,course_title,section,faculty,kind"]
    for wd, start, end, code in rows:
        lines.append(f"{room.code},{DAYS[wd]},{start},{end},{code},Course,K23KF,Dr X,Lecture")
    return "\n".join(lines)


def publish(term, text, actor, now):
    entries, errors = tt.parse_rows(text, term.institution_id)
    assert errors == []
    pub = tt.stage(term, entries, actor=actor)
    return tt.publish(pub, actor, now=now)


def test_parse_reports_unknown_room_bad_time_and_internal_clash(room, lpu):
    text = "\n".join(
        [
            "room_code,day,start,end,course_code",
            "NOPE,Mon,09:00,10:00,CSE326",
            f"{room.code},Tue,25:00,26:00,CSE326",
            f"{room.code},Wed,09:00,11:00,CSE310",
            f"{room.code},Wed,10:00,12:00,INT253",
        ]
    )
    entries, errors = tt.parse_rows(text, lpu.pk)
    assert any("unknown room 'NOPE'" in e for e in errors)
    assert any("unreadable time" in e for e in errors)
    assert any("CSE310" in e and "INT253" in e and "overlaps" in e for e in errors)


def test_missing_columns_are_reported(lpu):
    _, errors = tt.parse_rows("room,day\nx,Mon", lpu.pk)
    assert errors and "Missing column" in errors[0]


def test_publish_writes_only_future_occurrences_in_term(term, room, facility_manager, monday, now):
    result = publish(term, csv_for(room, monday, [(0, "09:00", "10:00", "CSE326")]), facility_manager, now)
    slots = BookingSlot.objects.filter(resource=room, kind=SlotKind.CLASS).order_by("period")
    assert result["occurrences"] == slots.count() == 4  # the four Mondays from `monday` to term end
    assert slots.first().period.lower == at(monday, 9)
    assert all(s.period.lower > now for s in slots)


def test_timetabled_slots_are_never_offered(term, room, student, facility_manager, monday, now):
    publish(term, csv_for(room, monday, [(0, "09:00", "11:00", "CSE326")]), facility_manager, now)
    sched = availability.day(room, monday, student, now=now)
    taken = [c for c in sched.cells if at(monday, 9) <= c.start < at(monday, 11)]
    assert taken and all(c.state == availability.CLASS and not c.selectable for c in taken)
    with pytest.raises(SlotUnavailable) as exc:
        bookings.create_booking(
            requester=student,
            resource=room,
            start=at(monday, 10),
            end=at(monday, 10, 30),
            title="x",
            now=now,
            notify=False,
        )
    assert exc.value.code == "timetable"


def test_publish_displaces_a_colliding_booking_and_tells_the_owner(term, room, student, facility_manager, monday, now):
    b = bookings.create_booking(
        requester=student, resource=room, start=at(monday, 9), end=at(monday, 10), title="Study", now=now, notify=False
    )
    result = publish(term, csv_for(room, monday, [(0, "09:00", "10:00", "CSE326")]), facility_manager, now)
    b.refresh_from_db()
    assert result["displaced"] == 1 and b.status == BookingStatus.CANCELLED
    assert "timetable" in b.status_reason
    assert Notification.objects.filter(user=student, kind=Kind.UNAVAILABLE).exists()


def test_republish_supersedes_atomically(term, room, facility_manager, monday, now):
    publish(term, csv_for(room, monday, [(0, "09:00", "10:00", "CSE326")]), facility_manager, now)
    publish(term, csv_for(room, monday, [(1, "14:00", "15:00", "CSE310")]), facility_manager, now)
    pubs = list(term.publications.order_by("version").values_list("status", flat=True))
    assert pubs == [PublicationStatus.SUPERSEDED, PublicationStatus.PUBLISHED]
    labels = set(BookingSlot.objects.filter(resource=room, kind=SlotKind.CLASS).values_list("label", flat=True))
    assert labels == {"CSE310 · Lecture · K23KF"}


def test_only_drafts_can_be_published(term, room, facility_manager, monday, now):
    entries, _ = tt.parse_rows(csv_for(room, monday, [(0, "09:00", "10:00", "CSE326")]), term.institution_id)
    pub = tt.stage(term, entries, actor=facility_manager)
    tt.publish(pub, facility_manager, now=now)
    pub.refresh_from_db()
    with pytest.raises(BookingRejected):
        tt.publish(pub, facility_manager, now=now)


def test_students_cannot_publish(term, room, student, monday, now):
    entries, _ = tt.parse_rows(csv_for(room, monday, [(0, "09:00", "10:00", "CSE326")]), term.institution_id)
    pub = tt.stage(term, entries, actor=student)
    with pytest.raises(NotPermitted):
        tt.publish(pub, student, now=now)


def test_class_overlapping_maintenance_fails_the_whole_publication(
    term, room, custodian, facility_manager, monday, now
):
    from apps.maintenance import services as maintenance

    maintenance.schedule(room, at(monday, 9), at(monday, 12), title="Rewiring", actor=custodian)
    with pytest.raises(BookingRejected):
        publish(term, csv_for(room, monday, [(0, "10:00", "11:00", "CSE326")]), facility_manager, now)
    assert not term.publications.filter(status=PublicationStatus.PUBLISHED).exists()
    assert not BookingSlot.objects.filter(kind=SlotKind.CLASS).exists()


def test_export_round_trips(term, room, facility_manager, monday, now):
    publish(term, csv_for(room, monday, [(2, "08:00", "09:00", "MTH401")]), facility_manager, now)
    text = tt.export_csv(tt.current_publication(term))
    entries, errors = tt.parse_rows(text, term.institution_id)
    assert errors == [] and entries[0].course_code == "MTH401" and entries[0].start_time == time(8)
