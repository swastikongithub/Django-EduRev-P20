"""
P20 acceptance criterion: "500 concurrent attempts on one slot yield exactly one
booking — proven by test."

Each attempt runs in its own thread with its own PostgreSQL connection (Django
opens one connection per thread). A barrier releases all of them at once, so
the INSERTs genuinely race inside PostgreSQL. The test uses the transactional_db
fixture (TransactionTestCase semantics): every attempt commits for real.

Two variants:
  * through the full service (friendly pre-check + constraint)
  * with the pre-check disabled, so every attempt reaches INSERT and the
    ExclusionConstraint alone decides — this is the proof that correctness does
    not depend on application code.
"""

import os
import threading
from collections import Counter

import pytest
from django.contrib.auth.models import Group
from django.db import connection, connections

from apps.accounts.models import Role, User
from apps.accounts.permissions import group_name, sync_role_groups
from apps.bookings import services as booking_services
from apps.bookings.models import Booking, BookingSlot
from apps.core.errors import SlotUnavailable

from .conftest import at

ATTEMPTS = int(os.environ.get("CONCURRENCY_ATTEMPTS", "500"))
# With both the pre-check and the advisory lock removed, every loser resolves through
# PostgreSQL's deadlock detector (deadlock_timeout = 1 s), so this variant runs smaller.
RAW_ATTEMPTS = int(os.environ.get("RAW_CONCURRENCY_ATTEMPTS", "100"))

pytestmark = [pytest.mark.concurrency, pytest.mark.django_db(transaction=True)]


def _students(lpu, cse, n):
    sync_role_groups()
    users = User.objects.bulk_create(
        [
            User(username=f"racer{i:03d}", institution=lpu, role=Role.STUDENT, department=cse, password="!")
            for i in range(n)
        ]
    )
    group = Group.objects.get(name=group_name(Role.STUDENT))
    User.groups.through.objects.bulk_create([User.groups.through(user_id=u.pk, group_id=group.pk) for u in users])
    return list(User.objects.filter(username__startswith="racer").order_by("pk"))


def _stampede(room, users, start, end, now):
    barrier = threading.Barrier(len(users))
    outcomes = Counter()
    errors = []
    lock = threading.Lock()

    def attempt(user):
        try:
            connection.ensure_connection()  # connect first, so the race is on INSERT, not on connect
            barrier.wait()
            booking_services.create_booking(
                requester=user, resource=room, start=start, end=end, title="Race", now=now, notify=False
            )
            key = "booked"
        except SlotUnavailable:
            key = "conflict"
        except Exception as exc:  # anything else is a bug
            key = "error"
            with lock:
                errors.append(repr(exc))
        finally:
            connections.close_all()
        with lock:
            outcomes[key] += 1

    threads = [threading.Thread(target=attempt, args=(u,)) for u in users]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    return outcomes, errors


def test_many_simultaneous_attempts_yield_exactly_one_booking(lpu, cse, room, monday, now):
    users = _students(lpu, cse, ATTEMPTS)
    start, end = at(monday, 10), at(monday, 11)

    outcomes, errors = _stampede(room, users, start, end, now)

    assert errors == []
    assert outcomes["booked"] == 1
    assert outcomes["conflict"] == ATTEMPTS - 1
    assert Booking.objects.filter(resource=room).count() == 1
    assert BookingSlot.objects.filter(resource=room).count() == 1


def test_database_constraint_alone_prevents_double_booking(lpu, cse, room, monday, now, monkeypatch):
    """
    Remove every application-level safeguard — the friendly pre-check and the advisory
    lock that queues claims — so all threads hit INSERT at once. PostgreSQL alone decides.
    """
    monkeypatch.setattr(booking_services, "conflicts_for", lambda *a, **k: [])
    monkeypatch.setattr(booking_services, "serialise_claims", lambda *a, **k: None)
    users = _students(lpu, cse, RAW_ATTEMPTS)
    # Overlapping but not identical ranges, to exercise && rather than equality.
    start, end = at(monday, 14), at(monday, 15, 30)

    outcomes, errors = _stampede(room, users, start, end, now)

    assert errors == []
    assert outcomes["booked"] == 1
    assert outcomes["conflict"] == RAW_ATTEMPTS - 1
    assert Booking.objects.filter(resource=room).count() == 1
    assert BookingSlot.objects.filter(resource=room).count() == 1
