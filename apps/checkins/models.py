"""M6 — Check-in, auto-release, no-show tracking and progressive restriction."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.bookings.models import Booking
from apps.catalogue.models import Resource
from apps.core.models import TenantModel


class CheckInMethod(models.TextChoices):
    RESOURCE_QR = "resource_qr", "Scanned the room/equipment QR"
    PASS_QR = "pass_qr", "Booking pass scanned by custodian"
    APP = "app", "Tapped check-in in app"
    CUSTODIAN = "custodian", "Checked in by custodian"


class CheckIn(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="checkin")
    checked_in_at = models.DateTimeField()
    method = models.CharField(max_length=16, choices=CheckInMethod.choices)
    checked_in_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    checked_out_at = models.DateTimeField(null=True, blank=True)
    checked_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    auto_checked_out = models.BooleanField(default=False)
    minutes_released = models.PositiveIntegerField(default=0, help_text="Time handed back by an early check-out")

    def __str__(self):
        return f"Check-in {self.booking.reference}"


class NoShow(TenantModel):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="no_show")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="no_shows")
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="no_shows")
    detected_at = models.DateTimeField()
    released_minutes = models.PositiveIntegerField(default=0)
    forgiven = models.BooleanField(default=False)
    forgiven_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    forgiven_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-detected_at"]
        indexes = [models.Index(fields=["user", "detected_at"])]

    def __str__(self):
        return f"No-show {self.booking.reference}"


class Restriction(TenantModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="restrictions")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=240)
    tier_label = models.CharField(max_length=80, blank=True)
    automatic = models.BooleanField(default=True)
    lifted_at = models.DateTimeField(null=True, blank=True)
    lifted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_at"]
        constraints = [
            models.CheckConstraint(name="restriction_ordered", condition=Q(starts_at__lt=models.F("ends_at")))
        ]

    def __str__(self):
        return f"{self.user} restricted until {self.ends_at:%d %b}"
