"""M8 — Consumables & Accessories."""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.bookings.models import Booking
from apps.catalogue.models import Resource, ResourceType
from apps.core.models import TenantModel, TimeStampedModel


class ItemKind(models.TextChoices):
    ACCESSORY = "accessory", "Accessory (returned)"
    CONSUMABLE = "consumable", "Consumable (used up)"


class InventoryItem(TenantModel, TimeStampedModel):
    name = models.CharField(max_length=120)
    sku = models.CharField(max_length=40)
    kind = models.CharField(max_length=12, choices=ItemKind.choices)
    unit = models.CharField(max_length=20, default="pcs")
    resource = models.ForeignKey(Resource, null=True, blank=True, on_delete=models.CASCADE, related_name="inventory")
    resource_type = models.ForeignKey(
        ResourceType, null=True, blank=True, on_delete=models.CASCADE, related_name="inventory"
    )
    quantity_total = models.PositiveIntegerField(
        default=0, help_text="Owned (accessories) / last restock (consumables)"
    )
    quantity_available = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=0)
    max_per_booking = models.PositiveIntegerField(default=10)
    description = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "sku"], name="uniq_item_sku"),
            models.CheckConstraint(
                name="item_available_le_total_for_accessories",
                condition=Q(kind="consumable") | Q(quantity_available__lte=F("quantity_total")),
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_low(self):
        return self.quantity_available <= self.reorder_level

    @property
    def is_returnable(self):
        return self.kind == ItemKind.ACCESSORY


class IssuanceStatus(models.TextChoices):
    RESERVED = "reserved", "Reserved"
    ISSUED = "issued", "Issued"
    RETURNED = "returned", "Returned"
    CONSUMED = "consumed", "Consumed"
    CANCELLED = "cancelled", "Cancelled"
    LOST = "lost", "Lost / damaged"


class Issuance(models.Model):
    """Items requested with a booking, issued at check-in and returned at check-out."""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="issuances")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="issuances")
    quantity = models.PositiveIntegerField()
    status = models.CharField(
        max_length=10, choices=IssuanceStatus.choices, default=IssuanceStatus.RESERVED, db_index=True
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(name="issuance_quantity_positive", condition=Q(quantity__gte=1)),
            models.UniqueConstraint(fields=["booking", "item"], name="uniq_issuance_item_per_booking"),
        ]

    def __str__(self):
        return f"{self.quantity}× {self.item} for {self.booking.reference}"


class StockMovement(models.Model):
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="movements")
    delta = models.IntegerField()
    reason = models.CharField(max_length=24)  # restock | issue | return | consume | adjust | lost
    issuance = models.ForeignKey(Issuance, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
