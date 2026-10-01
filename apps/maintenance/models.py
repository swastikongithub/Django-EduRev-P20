"""M7 — Maintenance & Downtime."""

from django.conf import settings
from django.contrib.postgres.fields import DateTimeRangeField
from django.db import models

from apps.catalogue.models import Resource
from apps.core.models import TenantModel, TimeStampedModel


class MaintenanceKind(models.TextChoices):
    PREVENTIVE = "preventive", "Preventive maintenance"
    REPAIR = "repair", "Repair"
    CALIBRATION = "calibration", "Calibration"
    UPGRADE = "upgrade", "Upgrade"
    CLEANING = "cleaning", "Deep cleaning"


class WindowStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class MaintenanceWindow(TenantModel, TimeStampedModel):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="maintenance_windows")
    title = models.CharField(max_length=140)
    kind = models.CharField(max_length=16, choices=MaintenanceKind.choices, default=MaintenanceKind.PREVENTIVE)
    period = DateTimeRangeField()
    status = models.CharField(
        max_length=12, choices=WindowStatus.choices, default=WindowStatus.SCHEDULED, db_index=True
    )
    notes = models.TextField(blank=True)
    vendor = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    displaced_bookings = models.PositiveSmallIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period"]

    def __str__(self):
        return f"{self.title} · {self.resource}"

    @property
    def start(self):
        return self.period.lower

    @property
    def end(self):
        return self.period.upper


class Severity(models.TextChoices):
    LOW = "low", "Minor — still usable"
    HIGH = "high", "Major — partly unusable"
    CRITICAL = "critical", "Critical — unusable"


class ReportStatus(models.TextChoices):
    OPEN = "open", "Open"
    ACKNOWLEDGED = "acknowledged", "Acknowledged"
    RESOLVED = "resolved", "Resolved"


class BreakdownReport(TenantModel, TimeStampedModel):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="breakdowns")
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    summary = models.CharField(max_length=160)
    details = models.TextField(blank=True)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.HIGH)
    status = models.CharField(max_length=14, choices=ReportStatus.choices, default=ReportStatus.OPEN, db_index=True)
    window = models.ForeignKey(
        MaintenanceWindow, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.CharField(max_length=240, blank=True)
    # A critical report takes the resource out of service only once someone who manages it has
    # confirmed it: immediately when they file it themselves, otherwise from the console (SEC-02).
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.summary

    @property
    def awaiting_confirmation(self) -> bool:
        return self.severity == Severity.CRITICAL and self.confirmed_at is None and self.status != ReportStatus.RESOLVED
