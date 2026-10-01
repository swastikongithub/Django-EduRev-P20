"""
The audit log is append-only at the database level (audit migrations 0002/0003): the trigger
rejects UPDATE and DELETE from any client, including raw SQL, while still letting ON DELETE
SET NULL detach a deleted user.
"""

import pytest
from django.db import DatabaseError, connection, transaction

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.bookings import services as bookings

from .conftest import at

pytestmark = pytest.mark.django_db


@pytest.fixture
def row(student, room):
    r = record(student, "test.action", room, before={"a": 1}, after={"a": 2})
    assert r is not None and r.pk
    return r


def _raw(sql, params):
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute(sql, params)


def test_raw_update_is_rejected(row):
    with pytest.raises(DatabaseError, match="append-only"):
        _raw("UPDATE audit_auditlog SET action = %s WHERE id = %s", ["tampered", row.pk])
    row.refresh_from_db()
    assert row.action == "test.action"


def test_raw_delete_is_rejected(row):
    with pytest.raises(DatabaseError, match="append-only"):
        _raw("DELETE FROM audit_auditlog WHERE id = %s", [row.pk])
    assert AuditLog.objects.filter(pk=row.pk).exists()


def test_orm_update_and_delete_are_rejected(row):
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditLog.objects.filter(pk=row.pk).update(after={"a": 999})
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditLog.objects.filter(pk=row.pk).delete()
    with pytest.raises(DatabaseError), transaction.atomic():
        row.delete()
    row.refresh_from_db()
    assert row.after == {"a": 2}


def test_detaching_the_actor_cannot_smuggle_other_changes(row):
    """The one permitted UPDATE (actor_id -> NULL) must not carry any other column change with it."""
    with pytest.raises(DatabaseError, match="append-only"):
        _raw("UPDATE audit_auditlog SET actor_id = NULL, action = %s WHERE id = %s", ["tampered", row.pk])
    row.refresh_from_db()
    assert row.actor_id is not None
    assert row.action == "test.action"


def test_reassigning_the_actor_is_rejected(row, make_user):
    other = make_user()
    with pytest.raises(DatabaseError, match="append-only"):
        _raw("UPDATE audit_auditlog SET actor_id = %s WHERE id = %s", [other.pk, row.pk])


def test_deleting_a_user_with_audit_rows_keeps_the_rows(make_user, room):
    user = make_user(first_name="Asha", last_name="Verma")
    r = record(user, "test.erasure", room)
    label = r.actor_label
    assert label == "Asha Verma"
    user.delete()  # ON DELETE SET NULL is the one UPDATE the trigger allows
    r.refresh_from_db()
    assert r.actor_id is None
    assert r.actor_label == "Asha Verma"
    assert r.action == "test.erasure"


def test_business_actions_are_audited(student, room, monday, now):
    b = bookings.create_booking(
        requester=student, resource=room, start=at(monday, 10), end=at(monday, 11), title="x", now=now, notify=False
    )
    bookings.cancel_booking(b, student, reason="changed plans", now=now)
    actions = list(
        AuditLog.objects.filter(target_type="bookings.booking", target_id=str(b.pk)).values_list("action", flat=True)
    )
    assert sorted(actions) == ["booking.cancel", "booking.create"]
    cancel = AuditLog.objects.get(target_id=str(b.pk), action="booking.cancel")
    assert cancel.actor_id == student.pk
    assert cancel.before == {"status": "approved"}
    assert cancel.after["status"] == "cancelled"
