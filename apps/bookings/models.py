"""
M3 — Booking Engine data model.

Two PostgreSQL exclusion constraints make double-booking structurally impossible:

1. ``booking_no_overlap`` on Booking(resource =, period &&) for every booking that
   is *holding* time (pending, approved, checked-in). Two such rows for the same
   resource with overlapping periods cannot both exist — the database refuses the
   second INSERT/UPDATE with SQLSTATE 23P01, no matter how many requests race.

2. ``slot_no_overlap`` on BookingSlot(resource =, period &&). BookingSlot is the
   single ledger of *all* claimed time on a resource — bookings, published
   timetable classes and maintenance windows. Because they share one table, a
   booking can never overlap a class or a maintenance window either.

See docs/booking-concurrency.md for the full argument.
"""

import secrets
import string

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import (
    ArrayField,
    DateTimeRangeField,
    RangeOperators,
)
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.catalogue.models import Resource
from apps.core.models import TenantModel, TimeStampedModel


class BookingStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending approval"
    APPROVED = "approved", "Confirmed"
    CHECKED_IN = "checked_in", "In use"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    NO_SHOW = "no_show", "Released · no-show"


HOLDING_STATUSES = (BookingStatus.PENDING, BookingStatus.APPROVED, BookingStatus.CHECKED_IN)
TERMINAL_STATUSES = (
    BookingStatus.COMPLETED,
    BookingStatus.CANCELLED,
    BookingStatus.REJECTED,
    BookingStatus.EXPIRED,
    BookingStatus.NO_SHOW,
)

# Legal state transitions. Anything else is a programming error.
TRANSITIONS: dict[str, set[str]] = {
    BookingStatus.DRAFT: {BookingStatus.PENDING, BookingStatus.APPROVED, BookingStatus.CANCELLED},
    BookingStatus.PENDING: {
        BookingStatus.APPROVED,
        BookingStatus.REJECTED,
        BookingStatus.CANCELLED,
        BookingStatus.EXPIRED,
    },
    BookingStatus.APPROVED: {
        BookingStatus.CHECKED_IN,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
        BookingStatus.COMPLETED,
    },
    BookingStatus.CHECKED_IN: {BookingStatus.COMPLETED},
}


def _reference():
    alphabet = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"
    return "LR-" + "".join(secrets.choice(alphabet) for _ in range(6))


def _qr_token():
    return secrets.token_urlsafe(18)


class Frequency(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"


class BookingSeries(TenantModel, TimeStampedModel):
    """RecurrenceRule — a recurring booking, expanded into individual Bookings."""

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="series")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="booking_series")
    title = models.CharField(max_length=140)
    frequency = models.CharField(max_length=8, choices=Frequency.choices, default=Frequency.WEEKLY)
    interval = models.PositiveSmallIntegerField(default=1)
    weekdays = ArrayField(models.PositiveSmallIntegerField(), default=list, blank=True)
    start_date = models.DateField()
    until_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    group_label = models.CharField(max_length=120, blank=True)
    created_count = models.PositiveSmallIntegerField(default=0)
    skipped = models.JSONField(default=list, blank=True, help_text="Occurrences not booked and why")

    class Meta:
        verbose_name_plural = "booking series"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(name="series_dates_ordered", condition=Q(start_date__lte=models.F("until_date"))),
            models.CheckConstraint(name="series_times_ordered", condition=Q(start_time__lt=models.F("end_time"))),
            models.CheckConstraint(name="series_interval_positive", condition=Q(interval__gte=1)),
        ]

    def __str__(self):
        return self.title


class Booking(TenantModel, TimeStampedModel):
    reference = models.CharField(max_length=12, unique=True, default=_reference, editable=False)
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name="bookings")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings_made")
    booked_for = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings")
    group_label = models.CharField(max_length=120, blank=True, help_text="Class / section / club this is for")
    title = models.CharField(max_length=140)
    attendees = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)
    period = DateTimeRangeField()
    status = models.CharField(
        max_length=16, choices=BookingStatus.choices, default=BookingStatus.PENDING, db_index=True
    )
    series = models.ForeignKey(BookingSeries, null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings")
    qr_token = models.CharField(max_length=32, unique=True, default=_qr_token, editable=False)
    requires_checkin = models.BooleanField(default=True)
    checkin_grace_minutes = models.PositiveSmallIntegerField(default=15)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    status_reason = models.CharField(max_length=240, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    checkin_nudge_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["period"]
        constraints = [
            ExclusionConstraint(
                name="booking_no_overlap",
                expressions=[("resource", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)],
                condition=Q(status__in=HOLDING_STATUSES),
            ),
            models.CheckConstraint(
                name="booking_period_bounded",
                condition=Q(period__isempty=False, period__lower_inf=False, period__upper_inf=False),
            ),
            models.CheckConstraint(name="booking_attendees_positive", condition=Q(attendees__gte=1)),
        ]
        indexes = [
            models.Index(fields=["booked_for", "status"]),
            models.Index(fields=["resource", "status"]),
        ]

    def __str__(self):
        return f"{self.reference} · {self.resource}"

    def get_absolute_url(self):
        return reverse("bookings:detail", args=[self.reference])

    @property
    def start(self):
        return self.period.lower

    @property
    def end(self):
        return self.period.upper

    @property
    def duration_minutes(self):
        return int((self.end - self.start).total_seconds() // 60)

    @property
    def is_holding(self):
        return self.status in HOLDING_STATUSES

    @property
    def is_upcoming(self):
        return self.is_holding and self.start > timezone.now()

    @property
    def checkin_deadline(self):
        return self.start + timezone.timedelta(minutes=self.checkin_grace_minutes)

    def can_transition(self, new_status) -> bool:
        return new_status in TRANSITIONS.get(self.status, set())


class SlotKind(models.TextChoices):
    BOOKING = "booking", "Booking"
    CLASS = "class", "Timetabled class"
    MAINTENANCE = "maintenance", "Maintenance"


class BookingSlot(models.Model):
    """
    The unified ledger of claimed time. One row per claim; rows are deleted when
    the claim ends early (cancellation, no-show release, maintenance cancelled).
    """

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="slots")
    period = DateTimeRangeField()
    kind = models.CharField(max_length=16, choices=SlotKind.choices)
    booking = models.OneToOneField(Booking, null=True, blank=True, on_delete=models.CASCADE, related_name="slot")
    source_type = models.CharField(max_length=32, blank=True, help_text="For non-booking claims, e.g. timetable_entry")
    source_id = models.BigIntegerField(null=True, blank=True)
    label = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["period"]
        constraints = [
            ExclusionConstraint(
                name="slot_no_overlap",
                expressions=[("resource", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)],
            ),
            models.CheckConstraint(
                name="slot_booking_kind_has_booking",
                condition=Q(kind="booking", booking__isnull=False) | (~Q(kind="booking") & Q(booking__isnull=True)),
            ),
            models.CheckConstraint(
                name="slot_period_bounded",
                condition=Q(period__isempty=False, period__lower_inf=False, period__upper_inf=False),
            ),
        ]
        indexes = [models.Index(fields=["source_type", "source_id"])]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.resource} · {self.period}"


class AttemptOutcome(models.TextChoices):
    BOOKED = "booked", "Booked"
    CONFLICT = "conflict", "Slot taken"
    TIMETABLE = "timetable", "Timetabled class"
    MAINTENANCE = "maintenance", "Maintenance"
    BLACKOUT = "blackout", "Blackout"
    CLOSED = "closed", "Outside hours"
    QUOTA = "quota", "Quota exceeded"
    RESTRICTED = "restricted", "User restricted"
    POLICY = "policy", "Policy violation"
    FORBIDDEN = "forbidden", "Not permitted"


class BookingAttempt(models.Model):
    """Every booking attempt, successful or not — the 'demand' side of demand vs supply."""

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="attempts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    period = DateTimeRangeField()
    outcome = models.CharField(max_length=16, choices=AttemptOutcome.choices, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["resource", "created_at"])]
