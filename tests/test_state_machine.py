"""
Booking state machine: every transition not listed in bookings.models.TRANSITIONS is refused,
and leaving a holding status always frees the time on the BookingSlot ledger.
"""

import pytest

from apps.bookings import services as bookings
from apps.bookings.models import HOLDING_STATUSES, TRANSITIONS, Booking, BookingSlot, BookingStatus
from apps.core.errors import InvalidTransition, NotPermitted

from .conftest import at

pytestmark = pytest.mark.django_db

ALL = list(BookingStatus.values)


def book(user, room, d, h1, h2, now, **kw):
    return bookings.create_booking(
        requester=user, resource=room, start=at(d, *h1), end=at(d, *h2), title="Study", now=now, notify=False, **kw
    )


def _forced(status, user, room, monday, now, hour=10):
    """An approved booking (with its ledger slot) whose status is then forced to `status`."""
    b = book(user, room, monday, (hour,), (hour + 1,), now)
    Booking.objects.filter(pk=b.pk).update(status=status)
    b.refresh_from_db()
    return b


@pytest.mark.parametrize("start_status", ALL)
def test_every_illegal_transition_is_refused(start_status, student, room, monday, now):
    b = _forced(start_status, student, room, monday, now)
    had_slot = BookingSlot.objects.filter(booking=b).exists()
    legal = TRANSITIONS.get(start_status, set())
    illegal = [s for s in ALL if s != start_status and s not in legal]
    assert illegal, "every status has at least one forbidden target"
    for target in illegal:
        with pytest.raises(InvalidTransition):
            bookings.set_status(b, target, now=now)
        b.refresh_from_db()
        assert b.status == start_status, f"{start_status} -> {target} must not change the row"
        assert BookingSlot.objects.filter(booking=b).exists() == had_slot


@pytest.mark.parametrize(
    "terminal",
    [
        BookingStatus.COMPLETED,
        BookingStatus.CANCELLED,
        BookingStatus.REJECTED,
        BookingStatus.EXPIRED,
        BookingStatus.NO_SHOW,
    ],
)
def test_terminal_statuses_have_no_way_out(terminal):
    assert not TRANSITIONS.get(terminal)


def test_same_status_is_a_no_op(student, room, monday, now):
    b = book(student, room, monday, (10,), (11,), now)
    assert bookings.set_status(b, BookingStatus.APPROVED, now=now) is b
    assert BookingSlot.objects.filter(booking=b).exists()


LEAVING_HOLD = [
    (BookingStatus.PENDING, BookingStatus.REJECTED),
    (BookingStatus.PENDING, BookingStatus.CANCELLED),
    (BookingStatus.PENDING, BookingStatus.EXPIRED),
    (BookingStatus.APPROVED, BookingStatus.CANCELLED),
    (BookingStatus.APPROVED, BookingStatus.NO_SHOW),
    (BookingStatus.APPROVED, BookingStatus.COMPLETED),
    (BookingStatus.CHECKED_IN, BookingStatus.COMPLETED),
]


@pytest.mark.parametrize(("start_status", "target"), LEAVING_HOLD)
def test_leaving_a_holding_status_frees_the_ledger(start_status, target, student, make_user, room, monday, now):
    b = _forced(start_status, student, room, monday, now)
    assert BookingSlot.objects.filter(booking=b).exists()
    bookings.set_status(b, target, reason="test", now=now)
    b.refresh_from_db()
    assert b.status == target
    assert target not in HOLDING_STATUSES
    assert not BookingSlot.objects.filter(booking=b).exists()
    # ...and the time is genuinely bookable again.
    assert book(make_user(), room, monday, (10,), (11,), now).status == BookingStatus.APPROVED


@pytest.mark.parametrize(
    ("start_status", "target"),
    [(BookingStatus.PENDING, BookingStatus.APPROVED), (BookingStatus.APPROVED, BookingStatus.CHECKED_IN)],
)
def test_moving_between_holding_statuses_keeps_the_slot(start_status, target, student, room, monday, now):
    b = _forced(start_status, student, room, monday, now)
    bookings.set_status(b, target, now=now)
    assert BookingSlot.objects.filter(booking=b).exists()


def test_set_status_stamps_decision_and_cancellation_times(student, room, monday, now):
    b = _forced(BookingStatus.PENDING, student, room, monday, now)
    bookings.set_status(b, BookingStatus.APPROVED, now=now)
    b.refresh_from_db()
    assert b.decided_at == now
    bookings.set_status(b, BookingStatus.CANCELLED, reason="x", now=now)
    b.refresh_from_db()
    assert b.cancelled_at == now
    assert b.status_reason == "x"


def test_cancelling_a_completed_booking_is_refused(student, room, monday, now):
    b = _forced(BookingStatus.COMPLETED, student, room, monday, now)
    with pytest.raises(NotPermitted):
        bookings.cancel_booking(b, student, now=now)
    with pytest.raises(InvalidTransition):
        bookings.set_status(b, BookingStatus.CANCELLED, now=now)
    b.refresh_from_db()
    assert b.status == BookingStatus.COMPLETED


@pytest.mark.parametrize("status", [BookingStatus.CHECKED_IN, BookingStatus.NO_SHOW, BookingStatus.REJECTED])
def test_cancel_booking_refuses_non_cancellable_statuses(status, student, room, monday, now):
    b = _forced(status, student, room, monday, now)
    with pytest.raises(NotPermitted):
        bookings.cancel_booking(b, student, now=now)


def test_cannot_cancel_a_booking_that_has_already_ended(student, room, monday, now):
    """cancel_booking(now=...) must judge 'already ended' against the `now` it is given, not the wall clock."""
    b = book(student, room, monday, (10,), (11,), now)
    with pytest.raises(NotPermitted):
        bookings.cancel_booking(b, student, now=at(monday, 11))
    b.refresh_from_db()
    assert b.status == BookingStatus.APPROVED
    # One minute before the end it is still cancellable.
    bookings.cancel_booking(b, student, now=at(monday, 10, 59))
    b.refresh_from_db()
    assert b.status == BookingStatus.CANCELLED
