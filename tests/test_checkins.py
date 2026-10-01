"""
M6: QR check-in, auto-release after the grace period, no-show tracking and the progressive
restriction ladder. Acceptance criteria: "auto-release fires correctly after the grace
period", "no-show tracking and progressive restriction functioning", "un-checked-in bookings
auto-release after the grace period".

The classroom policy (conftest.room_type) has a 15-minute grace; check-in opens 15 minutes early.
"""

from datetime import timedelta

import pytest

from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.bookings import services as bookings
from apps.bookings.models import Booking, BookingSlot, BookingStatus
from apps.checkins import services as checkins
from apps.checkins.models import CheckIn, CheckInMethod, NoShow, Restriction
from apps.core.errors import BookingRejected, InvalidTransition, NotPermitted
from apps.notifications import tasks as notification_tasks
from apps.notifications.models import Kind, Notification

from .conftest import at

pytestmark = pytest.mark.django_db


def book(user, resource, d, h1, h2, now, **kw):
    return bookings.create_booking(
        requester=user, resource=resource, start=at(d, *h1), end=at(d, *h2), title="Study", now=now, notify=False, **kw
    )


# ── Check-in window ─────────────────────────────────────────────────────────


def test_checkin_too_early_names_the_opening_time(student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    with pytest.raises(InvalidTransition, match="opens at 09:45"):
        checkins.check_in(b, student, now=at(monday, 9, 44))
    b.refresh_from_db()
    assert b.status == BookingStatus.APPROVED
    assert checkins.checkin_state(b, now=at(monday, 9, 44))["state"] == "not_yet"


@pytest.mark.parametrize("hm", [(9, 45), (10, 0), (10, 15)])
def test_checkin_within_window_succeeds(hm, student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    when = at(monday, *hm)
    assert checkins.checkin_state(b, now=when)["state"] == "open"
    checkins.check_in(b, student, now=when)
    b.refresh_from_db()
    assert b.status == BookingStatus.CHECKED_IN
    assert b.checked_in_at == when
    ci = CheckIn.objects.get(booking=b)
    assert (ci.method, ci.checked_in_by) == (CheckInMethod.APP, student)
    assert AuditLog.objects.filter(action="booking.check_in", target_id=str(b.pk)).count() == 1


def test_checkin_after_grace_is_refused(student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    with pytest.raises(InvalidTransition, match="closed"):
        checkins.check_in(b, student, now=at(monday, 10, 16))
    assert checkins.checkin_state(b, now=at(monday, 10, 16))["state"] == "missed"


def test_double_checkin_is_idempotent(student, custodian, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    checkins.check_in(b, student, now=at(monday, 10, 1))
    again = checkins.check_in(b, student, now=at(monday, 10, 5))
    assert again.status == BookingStatus.CHECKED_IN
    assert again.checked_in_at == at(monday, 10, 1)
    checkins.check_in(b, custodian, method=CheckInMethod.PASS_QR, now=at(monday, 10, 6))
    assert CheckIn.objects.filter(booking=b).count() == 1
    assert AuditLog.objects.filter(action="booking.check_in", target_id=str(b.pk)).count() == 1


def test_other_student_cannot_check_in(student, make_user, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    with pytest.raises(NotPermitted):
        checkins.check_in(b, make_user(), now=at(monday, 10))
    b.refresh_from_db()
    assert b.status == BookingStatus.APPROVED


def test_custodian_checks_in_a_pass_on_behalf(student, custodian, make_user, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    # The student can't claim the custodian-only method, nor can another resource's custodian.
    with pytest.raises(NotPermitted):
        checkins.check_in(b, student, method=CheckInMethod.PASS_QR, now=at(monday, 10))
    with pytest.raises(NotPermitted):
        checkins.check_in(b, make_user(Role.CUSTODIAN), method=CheckInMethod.PASS_QR, now=at(monday, 10))
    checkins.check_in(b, custodian, method=CheckInMethod.PASS_QR, now=at(monday, 10, 2))
    ci = CheckIn.objects.get(booking=b)
    assert (ci.method, ci.checked_in_by) == (CheckInMethod.PASS_QR, custodian)


def test_faculty_booking_for_a_student_either_may_check_in(faculty, student, room, monday, now):
    b = book(faculty, room, monday, (10,), (11,), now, booked_for=student)
    checkins.check_in(b, faculty, now=at(monday, 10))
    b.refresh_from_db()
    assert b.status == BookingStatus.CHECKED_IN


def test_pending_booking_cannot_be_checked_into(student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    Booking.objects.filter(pk=b.pk).update(status=BookingStatus.PENDING)
    with pytest.raises(InvalidTransition):
        checkins.check_in(b, student, now=at(monday, 10))


def test_door_qr_checks_in_the_right_booking(student, make_user, room, room2, monday, now):
    other = make_user()
    mine = book(student, room, monday, (10,), (11,), now)
    book(other, room, monday, (11,), (12,), now)
    book(student, room2, monday, (10,), (11,), now)

    assert checkins.check_in_at_resource(room, student, now=at(monday, 9, 30)) is None  # window not open yet
    b = checkins.check_in_at_resource(room, student, now=at(monday, 9, 50))
    assert b.pk == mine.pk
    assert b.status == BookingStatus.CHECKED_IN
    assert CheckIn.objects.get(booking=b).method == CheckInMethod.RESOURCE_QR
    # Scanning again is harmless and returns the same booking.
    assert checkins.check_in_at_resource(room, student, now=at(monday, 10, 5)).pk == mine.pk
    # Somebody without a booking here gets nothing, and can't hijack the next person's slot early.
    assert checkins.check_in_at_resource(room, make_user(), now=at(monday, 10, 5)) is None
    assert checkins.check_in_at_resource(room, other, now=at(monday, 10, 5)) is None


# ── Check-out ───────────────────────────────────────────────────────────────


def test_early_checkout_hands_back_the_tail(student, make_user, room, monday, now):
    b = book(student, room, monday, (10,), (12,), now)
    checkins.check_in(b, student, now=at(monday, 10))
    out_at = at(monday, 10, 21) + timedelta(seconds=30)
    checkins.check_out(b, student, now=out_at)
    b.refresh_from_db()
    assert b.status == BookingStatus.COMPLETED
    assert b.start == at(monday, 10)
    assert b.end == at(monday, 10, 25), "the kept period rounds up to the next 5 minutes"
    assert b.checked_out_at == out_at
    assert not BookingSlot.objects.filter(booking=b).exists()
    assert CheckIn.objects.get(booking=b).minutes_released == 95
    assert AuditLog.objects.filter(action="booking.check_out", target_id=str(b.pk)).exists()

    # The freed tail is genuinely bookable by someone else.
    later = book(make_user(), room, monday, (10, 30), (12,), out_at)
    assert later.status == BookingStatus.APPROVED


def test_only_checked_in_bookings_can_be_checked_out(student, make_user, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    with pytest.raises(InvalidTransition):
        checkins.check_out(b, student, now=at(monday, 10, 10))
    checkins.check_in(b, student, now=at(monday, 10))
    with pytest.raises(NotPermitted):
        checkins.check_out(b, make_user(), now=at(monday, 10, 10))


def test_sweep_completed_auto_checks_out_ended_bookings(student, make_user, room, room2, monday, now):
    ended = book(student, room, monday, (10,), (11,), now)
    running = book(make_user(), room2, monday, (10,), (12,), now)
    no_checkin = book(make_user(), room, monday, (8,), (9,), now)
    Booking.objects.filter(pk=no_checkin.pk).update(requires_checkin=False)
    checkins.check_in(ended, student, now=at(monday, 10))
    checkins.check_in(running, running.booked_for, now=at(monday, 10))

    assert checkins.sweep_completed(now=at(monday, 11)) == 2
    ended.refresh_from_db()
    running.refresh_from_db()
    no_checkin.refresh_from_db()
    assert ended.status == BookingStatus.COMPLETED
    assert ended.end == at(monday, 11)
    assert ended.checked_out_at == at(monday, 11)
    ci = CheckIn.objects.get(booking=ended)
    assert ci.auto_checked_out and ci.checked_out_by is None and ci.minutes_released == 0
    assert running.status == BookingStatus.CHECKED_IN
    assert no_checkin.status == BookingStatus.COMPLETED
    assert not BookingSlot.objects.filter(booking__in=[ended, no_checkin]).exists()
    assert checkins.sweep_completed(now=at(monday, 11)) == 0


# ── Auto-release ────────────────────────────────────────────────────────────


def test_sweep_releases_exactly_after_the_grace_period(student, make_user, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    assert checkins.sweep_no_shows(now=at(monday, 10)) == []
    # At the deadline the student may still check in, so the sweep must not release yet.
    assert checkins.sweep_no_shows(now=at(monday, 10, 15)) == []
    b.refresh_from_db()
    assert b.status == BookingStatus.APPROVED

    released = checkins.sweep_no_shows(now=at(monday, 10, 16))
    assert [x.pk for x in released] == [b.pk]
    b.refresh_from_db()
    assert b.status == BookingStatus.NO_SHOW
    assert not BookingSlot.objects.filter(booking=b).exists()
    ns = NoShow.objects.get(booking=b)
    assert (ns.user, ns.resource, ns.released_minutes) == (student, room, 44)
    assert ns.detected_at == at(monday, 10, 16)
    assert Notification.objects.filter(user=student, kind=Kind.AUTO_RELEASED).count() == 1

    # Too late to check in now, and a second sweep is a no-op.
    with pytest.raises(InvalidTransition):
        checkins.check_in(b, student, now=at(monday, 10, 17))
    assert checkins.sweep_no_shows(now=at(monday, 10, 17)) == []

    # Someone else can take the remaining time.
    walk_in = book(make_user(), room, monday, (10, 30), (11,), at(monday, 10, 16))
    assert walk_in.status == BookingStatus.APPROVED


def test_checkin_at_the_deadline_beats_the_sweep(student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    checkins.check_in(b, student, now=at(monday, 10, 15))
    assert checkins.sweep_no_shows(now=at(monday, 10, 15)) == []
    assert checkins.sweep_no_shows(now=at(monday, 10, 30)) == []
    b.refresh_from_db()
    assert b.status == BookingStatus.CHECKED_IN
    assert not NoShow.objects.exists()


def test_sweep_ignores_checked_in_and_no_checkin_bookings(student, make_user, room, room2, monday, now):
    checked_in = book(student, room, monday, (10,), (11,), now)
    checkins.check_in(checked_in, student, now=at(monday, 10))
    exempt = book(make_user(), room2, monday, (10,), (11,), now)
    Booking.objects.filter(pk=exempt.pk).update(requires_checkin=False)

    assert checkins.sweep_no_shows(now=at(monday, 10, 45)) == []
    checked_in.refresh_from_db()
    exempt.refresh_from_db()
    assert checked_in.status == BookingStatus.CHECKED_IN
    assert exempt.status == BookingStatus.APPROVED
    assert not NoShow.objects.exists()


def test_checkin_nudge_and_reminder_are_sent_once(student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    assert notification_tasks._reminders(now=at(monday, 9, 29)) == 0  # more than 30 minutes out
    assert notification_tasks._reminders(now=at(monday, 9, 30)) == 1
    assert notification_tasks._reminders(now=at(monday, 9, 40)) == 0
    assert notification_tasks._checkin_nudges(now=at(monday, 9, 59)) == 0  # not started
    assert notification_tasks._checkin_nudges(now=at(monday, 10, 5)) == 1
    assert notification_tasks._checkin_nudges(now=at(monday, 10, 6)) == 0
    nudge = Notification.objects.get(user=student, kind=Kind.CHECKIN_OPEN)
    assert nudge.title == "Check in now · 10 min left"
    b.refresh_from_db()
    assert b.reminder_sent_at == at(monday, 9, 30)


# ── Progressive restriction ─────────────────────────────────────────────────


def _no_show(user, resource, d, now):
    """Book d 10:00-11:00 (made at `now`), then let the sweep release it at 10:16."""
    b = book(user, resource, d, (10,), (11,), now)
    return b


def _sweep_on(d):
    return checkins.sweep_no_shows(now=at(d, 10, 16))


def test_progressive_ladder(ladder, student, room, monday, now):
    days = [monday + timedelta(days=i) for i in range(5)]  # Mon..Fri of one week
    for d in days:
        _no_show(student, room, d, now)

    _sweep_on(days[0])
    assert not Notification.objects.filter(user=student, kind=Kind.RESTRICTED).exists()

    _sweep_on(days[1])
    [warning] = Notification.objects.filter(user=student, kind=Kind.RESTRICTED)
    assert "Heads up" in warning.title
    assert not Restriction.objects.exists(), "the first tier is a warning only"

    _sweep_on(days[2])
    r = Restriction.objects.get(user=student)
    assert r.tier_label == "7-day pause"
    assert r.starts_at == at(days[2], 10, 16)
    assert r.ends_at == at(days[2], 10, 16) + timedelta(days=7)
    assert r.automatic
    with pytest.raises(BookingRejected) as exc:
        book(student, room, days[2] + timedelta(days=14), (14,), (15,), at(days[2], 11))
    assert exc.value.code == "restricted"
    assert checkins.active_restriction(student, at(days[2], 11)) == r
    assert checkins.active_restriction(student, r.ends_at) is None, "restrictions end by time"

    _sweep_on(days[3])
    _sweep_on(days[4])
    top = checkins.active_restriction(student, at(days[4], 10, 30))
    assert top.tier_label == "30-day pause"
    assert top.ends_at == at(days[4], 10, 16) + timedelta(days=30)
    assert NoShow.objects.filter(user=student).count() == 5


def test_thirty_day_pause_counts_a_sixty_day_window(ladder, student, room, monday, now):
    # No-shows on days 0, 10, 40, 45, 50: never 3 inside a 30-day window until day 50, but 5 within 60 days.
    offsets = [0, 10, 40, 45, 50]
    days = [monday + timedelta(days=o) for o in offsets]
    assert all(d.weekday() != 6 for d in days)
    for d in days:
        _no_show(student, room, d, now)
    for d in days[:4]:
        _sweep_on(d)
        assert checkins.active_restriction(student, at(d, 10, 30)) is None
    _sweep_on(days[4])
    r = checkins.active_restriction(student, at(days[4], 10, 30))
    assert r.tier_label == "30-day pause"


def test_forgiving_below_the_threshold_lifts_the_restriction(ladder, student, custodian, room, monday, now):
    days = [monday + timedelta(days=i) for i in range(3)]
    for d in days:
        _no_show(student, room, d, now)
    for d in days:
        _sweep_on(d)
    later = at(days[2], 11)
    assert checkins.active_restriction(student, later)

    ns = NoShow.objects.filter(user=student).order_by("detected_at").first()
    checkins.forgive(ns, custodian, "Lift was broken that morning", now=later)
    ns.refresh_from_db()
    assert ns.forgiven and ns.forgiven_by == custodian
    assert checkins.active_restriction(student, later) is None
    assert book(student, room, days[2] + timedelta(days=7), (14,), (15,), later).status == BookingStatus.APPROVED
    assert AuditLog.objects.filter(action="no_show.forgive", actor=custodian).exists()


def test_forgiving_lifts_every_stacked_automatic_restriction(ladder, student, custodian, room, monday, now):
    days = [monday + timedelta(days=i) for i in range(5)]
    for d in days:
        _no_show(student, room, d, now)
    for d in days:
        _sweep_on(d)
    later = at(days[4], 11)
    assert Restriction.objects.filter(user=student).count() >= 2

    for ns in NoShow.objects.filter(user=student).order_by("detected_at")[:3]:
        checkins.forgive(ns, custodian, "Timetable clash, not the student's fault", now=later)
    assert checkins.recent_no_shows(student, 30, later) == 2
    assert checkins.active_restriction(student, later) is None, "no automatic restriction may outlive the tiers"


def test_forgiving_above_the_threshold_keeps_the_restriction(ladder, student, custodian, room, monday, now):
    days = [monday + timedelta(days=i) for i in range(4)]
    for d in days:
        _no_show(student, room, d, now)
    for d in days:
        _sweep_on(d)
    later = at(days[3], 11)
    checkins.forgive(NoShow.objects.filter(user=student).first(), custodian, "one-off", now=later)
    assert checkins.active_restriction(student, later) is not None


def test_only_managers_can_forgive(ladder, student, make_user, room, monday, now):
    _no_show(student, room, monday, now)
    _sweep_on(monday)
    ns = NoShow.objects.get(user=student)
    for outsider in (student, make_user(), make_user(Role.CUSTODIAN), make_user(Role.FACULTY)):
        with pytest.raises(NotPermitted):
            checkins.forgive(ns, outsider, "please", now=at(monday, 11))
    ns.refresh_from_db()
    assert not ns.forgiven
