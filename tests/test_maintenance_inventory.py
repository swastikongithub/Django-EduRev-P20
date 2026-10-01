"""M7 maintenance & downtime, M8 consumables & accessories."""

import pytest

from apps.bookings import services as bookings
from apps.bookings.models import BookingSlot, SlotKind
from apps.checkins import services as checkins
from apps.core.errors import BookingRejected, NotPermitted, SlotUnavailable
from apps.inventory import services as inventory
from apps.inventory.models import InventoryItem, IssuanceStatus
from apps.maintenance import services as maintenance
from apps.maintenance.models import ReportStatus, WindowStatus
from apps.notifications.models import Kind, Notification

from .conftest import at

pytestmark = pytest.mark.django_db


def book(user, room, d, h1, h2, now, **kw):
    return bookings.create_booking(
        requester=user, resource=room, start=at(d, h1), end=at(d, h2), title="x", now=now, notify=False, **kw
    )


# ── Maintenance ─────────────────────────────────────────────────────────────


def test_cancelling_maintenance_frees_the_time(room, custodian, student, monday, now):
    w = maintenance.schedule(room, at(monday, 9), at(monday, 12), title="Painting", actor=custodian)
    with pytest.raises(SlotUnavailable):
        book(student, room, monday, 10, 11, now)
    maintenance.cancel(w, custodian)
    assert book(student, room, monday, 10, 11, now)


def test_completing_early_hands_back_the_rest(room, custodian, student, monday, now):
    w = maintenance.schedule(room, at(monday, 9), at(monday, 13), title="Repair", actor=custodian)
    maintenance.complete(w, custodian, now=at(monday, 10, 30))
    w.refresh_from_db()
    assert w.status == WindowStatus.COMPLETED and w.end == at(monday, 10, 30)
    assert BookingSlot.objects.get(source_type="maintenance_window", source_id=w.pk).period.upper == at(monday, 10, 30)
    assert book(student, room, monday, 11, 12, now)


def test_maintenance_never_displaces_a_class(room, custodian, monday):
    bookings.claim_block(
        room,
        at(monday, 10),
        at(monday, 11),
        kind=SlotKind.CLASS,
        source_type="timetable_entry",
        source_id=1,
        label="CSE326 Lecture",
    )
    with pytest.raises(SlotUnavailable) as exc:
        maintenance.schedule(room, at(monday, 9), at(monday, 12), title="Painting", actor=custodian)
    assert "CSE326" in exc.value.message
    assert not room.maintenance_windows.exists()


def test_critical_breakdown_takes_resource_offline_until_resolved(room, custodian, student, monday, now):
    # A student's critical report alerts the custodian; it takes the room offline once confirmed (SEC-02).
    report = maintenance.report_breakdown(room, student, summary="Projector sparking", severity="critical")
    room.refresh_from_db()
    assert room.status == "active"
    assert Notification.objects.filter(user=custodian, kind=Kind.BREAKDOWN).exists()
    maintenance.confirm_critical(report, custodian)
    room.refresh_from_db()
    assert room.status == "out_of_service"
    with pytest.raises(BookingRejected, match="out of service"):
        book(student, room, monday, 10, 11, now)
    maintenance.resolve(report, custodian, "Replaced the lamp")
    room.refresh_from_db()
    report.refresh_from_db()
    assert room.status == "active" and report.status == ReportStatus.RESOLVED
    assert book(student, room, monday, 10, 11, now)


def test_minor_breakdown_keeps_resource_bookable(room, student):
    maintenance.report_breakdown(room, student, summary="One chair wobbly", severity="low")
    room.refresh_from_db()
    assert room.status == "active"


def test_sweep_moves_windows_through_their_lifecycle(room, custodian, monday):
    w = maintenance.schedule(room, at(monday, 9), at(monday, 10), title="Clean", actor=custodian)
    maintenance.sweep_windows(now=at(monday, 9, 30))
    w.refresh_from_db()
    assert w.status == WindowStatus.IN_PROGRESS
    maintenance.sweep_windows(now=at(monday, 10, 1))
    w.refresh_from_db()
    assert w.status == WindowStatus.COMPLETED


# ── Inventory ───────────────────────────────────────────────────────────────


@pytest.fixture
def adapters(lpu, room):
    return InventoryItem.objects.create(
        institution=lpu,
        name="HDMI adapter",
        sku="HDMI",
        kind="accessory",
        resource=room,
        quantity_total=3,
        quantity_available=3,
        reorder_level=1,
        max_per_booking=3,
    )


@pytest.fixture
def markers(lpu, room):
    return InventoryItem.objects.create(
        institution=lpu,
        name="Markers",
        sku="MRK",
        kind="consumable",
        resource=room,
        quantity_total=10,
        quantity_available=4,
        reorder_level=3,
        max_per_booking=5,
    )


def test_overlapping_bookings_cannot_overcommit_a_shared_pool(
    lpu, room, room2, room_type, student, make_user, monday, now
):
    """Projectors shared by every classroom: two rooms booked at once can't both take the last ones."""
    pool = InventoryItem.objects.create(
        institution=lpu,
        name="Portable projector",
        sku="PRJ",
        kind="accessory",
        resource_type=room_type,
        quantity_total=3,
        quantity_available=3,
        max_per_booking=3,
    )
    book(student, room, monday, 9, 11, now, items={pool.pk: 2})
    with pytest.raises(BookingRejected, match="Only 1"):
        book(make_user(), room2, monday, 10, 12, now, items={pool.pk: 2})
    # A later, non-overlapping booking can have all three.
    assert book(make_user(), room2, monday, 11, 12, now, items={pool.pk: 3})


def test_issue_on_check_in_and_return_on_check_out(room, adapters, markers, custodian, student, monday):
    b = book(student, room, monday, 10, 11, at(monday, 8), items={adapters.pk: 2, markers.pk: 2})
    checkins.check_in(b, student, now=at(monday, 10, 2))
    adapters.refresh_from_db()
    markers.refresh_from_db()
    assert (adapters.quantity_available, markers.quantity_available) == (1, 2)
    statuses = dict(b.issuances.values_list("item__sku", "status"))
    assert statuses == {"HDMI": IssuanceStatus.ISSUED, "MRK": IssuanceStatus.CONSUMED}
    assert Notification.objects.filter(user=custodian, kind=Kind.STOCK_LOW).exists()  # markers fell to 2 (≤ 3)
    checkins.check_out(b, student, now=at(monday, 10, 40))
    adapters.refresh_from_db()
    assert adapters.quantity_available == 3
    assert b.issuances.get(item=adapters).status == IssuanceStatus.RETURNED


def test_cancelling_releases_reservations(room, adapters, student, monday, now):
    b = book(student, room, monday, 10, 11, now, items={adapters.pk: 1})
    bookings.cancel_booking(b, student, now=now)
    assert b.issuances.get().status == IssuanceStatus.CANCELLED


def test_items_must_belong_to_the_resource(lpu, room, room2, student, monday, now):
    other = InventoryItem.objects.create(
        institution=lpu,
        name="Tripod",
        sku="TRI",
        kind="accessory",
        resource=room2,
        quantity_total=2,
        quantity_available=2,
    )
    with pytest.raises(BookingRejected, match="isn't available"):
        book(student, room, monday, 10, 11, now, items={other.pk: 1})


def test_restock_is_for_managers_only(markers, student, custodian):
    with pytest.raises(NotPermitted):
        inventory.restock(markers, 5, student)
    inventory.restock(markers, 6, custodian, note="new box")
    markers.refresh_from_db()
    assert markers.quantity_available == 10
    assert markers.movements.filter(reason="restock", delta=6).exists()


def test_low_stock_listing(markers, adapters, lpu):
    assert list(inventory.low_stock(lpu.pk)) == []  # markers 4 > 3
    InventoryItem.objects.filter(pk=markers.pk).update(quantity_available=2)
    assert list(inventory.low_stock(lpu.pk)) == [InventoryItem.objects.get(pk=markers.pk)]
