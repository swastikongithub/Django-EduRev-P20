from django.conf import settings
from django.db import models


class Kind(models.TextChoices):
    BOOKING_CONFIRMED = "booking_confirmed", "Booking confirmed"
    APPROVAL_REQUIRED = "approval_required", "Approval required"
    APPROVAL_PENDING = "approval_pending", "Waiting for approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    REMINDER = "reminder", "Starting soon"
    CHECKIN_OPEN = "checkin_open", "Check-in open"
    AUTO_RELEASED = "auto_released", "Auto-released"
    RESTRICTED = "restricted", "Booking restricted"
    MAINTENANCE = "maintenance", "Maintenance scheduled"
    UNAVAILABLE = "unavailable", "Resource unavailable"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"
    STOCK_LOW = "stock_low", "Stock low"
    BREAKDOWN = "breakdown", "Breakdown reported"
    SERIES = "series", "Recurring booking"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=500, blank=True)
    url = models.CharField(max_length=240, blank=True)
    tone = models.CharField(max_length=12, default="info")  # info | success | warning | danger
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"])]

    def __str__(self):
        return self.title
