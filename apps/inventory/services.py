"""
M8 service interface.

    items_for(resource)                      accessories/consumables that can be requested with a booking
    reserve(booking, {item_id: qty})         reserve at booking time (row-locked stock check)
    issue_for_booking(booking, actor)        at check-in: accessories issued, consumables consumed
    return_for_booking(booking, actor)       at check-out: accessories returned to stock
    cancel_reservations(booking)             booking ended without use
    restock(item, qty, actor) / adjust(...)  custodian stock changes
    low_stock(institution_id)                items at or under their reorder level
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts.permissions import can_manage_resource, has_cap, is_campus_wide
from apps.bookings.models import HOLDING_STATUSES, Booking
from apps.core.errors import BookingRejected, NotPermitted

from .models import InventoryItem, Issuance, IssuanceStatus, ItemKind, StockMovement


def items_for(resource):
    return InventoryItem.objects.filter(institution_id=resource.institution_id).filter(
        Q(resource=resource) | Q(resource__isnull=True, resource_type_id=resource.type_id)
    )


def _committed_elsewhere(item: InventoryItem, booking: Booking) -> int:
    """Units already promised to bookings whose time overlaps this one (accessories)."""
    if item.kind == ItemKind.CONSUMABLE:
        agg = Issuance.objects.filter(item=item, status=IssuanceStatus.RESERVED).exclude(booking=booking)
    else:
        agg = Issuance.objects.filter(
            item=item,
            status__in=[IssuanceStatus.RESERVED, IssuanceStatus.ISSUED],
            booking__status__in=HOLDING_STATUSES,
            booking__period__overlap=booking.period,
        ).exclude(booking=booking)
    return agg.aggregate(n=Sum("quantity"))["n"] or 0


def reserve(booking: Booking, items: dict[int, int]):
    wanted = {int(k): int(v) for k, v in items.items() if int(v) > 0}
    if not wanted:
        return []
    allowed = {i.pk for i in items_for(booking.resource)}
    out = []
    # Lock item rows in id order so concurrent bookings can't deadlock on each other.
    for item in InventoryItem.objects.select_for_update().filter(pk__in=sorted(wanted)).order_by("pk"):
        qty = wanted[item.pk]
        if item.pk not in allowed:
            raise BookingRejected(f"{item.name} isn't available with {booking.resource.name}.", code="policy")
        if qty > item.max_per_booking:
            raise BookingRejected(
                f"At most {item.max_per_booking} {item.unit} of {item.name} per booking.", code="policy"
            )
        pool = item.quantity_total if item.kind == ItemKind.ACCESSORY else item.quantity_available
        free = pool - _committed_elsewhere(item, booking)
        if qty > free:
            raise BookingRejected(
                f"Only {max(free, 0)} {item.unit} of {item.name} free for that time.",
                code="policy",
                detail={"item": item.pk, "free": max(free, 0)},
            )
        out.append(Issuance.objects.create(booking=booking, item=item, quantity=qty))
    return out


def _move(item, delta, reason, *, issuance=None, actor=None, note=""):
    StockMovement.objects.create(item=item, delta=delta, reason=reason, issuance=issuance, actor=actor, note=note)


def _alert_if_low(item):
    if item.is_low:
        from apps.notifications.models import Kind
        from apps.notifications.services import notify_many

        custodians = [c.user for c in item.resource.custodians.select_related("user")] if item.resource_id else []
        notify_many(
            custodians,
            Kind.STOCK_LOW,
            f"Low stock · {item.name}",
            f"{item.quantity_available} {item.unit} left (reorder at {item.reorder_level}).",
            "/manage/inventory/",
            email=False,
        )


def issue_for_booking(booking: Booking, actor):
    now = timezone.now()
    for iss in Issuance.objects.select_related("item").filter(booking=booking, status=IssuanceStatus.RESERVED):
        item = InventoryItem.objects.select_for_update().get(pk=iss.item_id)
        qty = min(iss.quantity, item.quantity_available)
        if qty <= 0:
            continue
        item.quantity_available -= qty
        item.save(update_fields=["quantity_available", "updated_at"])
        iss.quantity = qty
        iss.status = IssuanceStatus.ISSUED if item.kind == ItemKind.ACCESSORY else IssuanceStatus.CONSUMED
        iss.issued_at = now
        iss.handled_by = actor
        iss.save(update_fields=["quantity", "status", "issued_at", "handled_by"])
        _move(item, -qty, "issue" if item.kind == ItemKind.ACCESSORY else "consume", issuance=iss, actor=actor)
        _alert_if_low(item)


def return_for_booking(booking: Booking, actor):
    now = timezone.now()
    for iss in Issuance.objects.filter(booking=booking, status=IssuanceStatus.ISSUED):
        item = InventoryItem.objects.select_for_update().get(pk=iss.item_id)
        item.quantity_available = min(item.quantity_total, item.quantity_available + iss.quantity)
        item.save(update_fields=["quantity_available", "updated_at"])
        iss.status = IssuanceStatus.RETURNED
        iss.returned_at = now
        iss.handled_by = actor
        iss.save(update_fields=["status", "returned_at", "handled_by"])
        _move(item, iss.quantity, "return", issuance=iss, actor=actor)


def cancel_reservations(booking: Booking):
    Issuance.objects.filter(booking=booking, status=IssuanceStatus.RESERVED).update(status=IssuanceStatus.CANCELLED)


def can_manage_item(user, item: InventoryItem) -> bool:
    if not has_cap(user, "manage_inventory"):
        return False
    if is_campus_wide(user):
        return True
    return bool(item.resource_id and can_manage_resource(user, item.resource))


def restock(item: InventoryItem, qty: int, actor, note=""):
    if not can_manage_item(actor, item):
        raise NotPermitted("You don't manage this item.")
    if qty <= 0:
        raise BookingRejected("Restock quantity must be positive.", code="policy")
    with transaction.atomic():
        item = InventoryItem.objects.select_for_update().get(pk=item.pk)
        item.quantity_available += qty
        if item.kind == ItemKind.ACCESSORY:
            item.quantity_total += qty
        else:
            item.quantity_total = max(item.quantity_total, item.quantity_available)
        item.save(update_fields=["quantity_available", "quantity_total", "updated_at"])
        _move(item, qty, "restock", actor=actor, note=note)
    return item


def mark_lost(issuance: Issuance, actor, note=""):
    if not can_manage_item(actor, issuance.item):
        raise NotPermitted("You don't manage this item.")
    with transaction.atomic():
        item = InventoryItem.objects.select_for_update().get(pk=issuance.item_id)
        if issuance.status == IssuanceStatus.ISSUED:
            item.quantity_total = max(0, item.quantity_total - issuance.quantity)
            item.save(update_fields=["quantity_total", "updated_at"])
            issuance.status = IssuanceStatus.LOST
            issuance.save(update_fields=["status"])
            _move(item, -issuance.quantity, "lost", issuance=issuance, actor=actor, note=note)
    return issuance


def low_stock(institution_id):
    from django.db.models import F

    return InventoryItem.objects.filter(institution_id=institution_id, quantity_available__lte=F("reorder_level"))
