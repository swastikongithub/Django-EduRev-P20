"""
M2 — Availability & Rules.

Everything here is data, edited from the admin console; nothing is hard-coded in
views. Scope resolution is always most-specific-wins: resource > type > campus.
"""

from django.contrib.postgres.fields import ArrayField, DateTimeRangeField
from django.db import models
from django.db.models import Q

from apps.accounts.models import Department, Role
from apps.catalogue.models import Building, Resource, ResourceType
from apps.core.models import TenantModel, TimeStampedModel


class Scope(models.TextChoices):
    CAMPUS = "campus", "Whole campus"
    TYPE = "type", "Resource type"
    RESOURCE = "resource", "Single resource"


def _scope_constraint(prefix):
    return models.CheckConstraint(
        name=f"{prefix}_scope_consistent",
        condition=(
            Q(scope="campus", resource_type__isnull=True, resource__isnull=True)
            | Q(scope="type", resource_type__isnull=False, resource__isnull=True)
            | Q(scope="resource", resource__isnull=False)
        ),
    )


class BookingPolicy(TenantModel, TimeStampedModel):
    """Duration, lead-time, window and check-in rules."""

    scope = models.CharField(max_length=12, choices=Scope.choices, default=Scope.TYPE)
    resource_type = models.ForeignKey(
        ResourceType, null=True, blank=True, on_delete=models.CASCADE, related_name="policies"
    )
    resource = models.ForeignKey(Resource, null=True, blank=True, on_delete=models.CASCADE, related_name="policies")
    slot_minutes = models.PositiveSmallIntegerField(default=30)
    min_duration_minutes = models.PositiveSmallIntegerField(default=30)
    max_duration_minutes = models.PositiveSmallIntegerField(default=180)
    lead_time_minutes = models.PositiveIntegerField(default=0, help_text="Minimum notice before start")
    max_advance_days = models.PositiveSmallIntegerField(default=30, help_text="How far ahead bookings open")
    requires_checkin = models.BooleanField(default=True)
    checkin_opens_minutes = models.PositiveSmallIntegerField(
        default=15, help_text="Check-in opens this long before start"
    )
    checkin_grace_minutes = models.PositiveSmallIntegerField(
        default=15, help_text="Auto-release after this long without check-in"
    )
    enforce_capacity = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "booking policies"
        constraints = [
            _scope_constraint("policy"),
            models.CheckConstraint(
                name="policy_duration_order", condition=Q(min_duration_minutes__lte=models.F("max_duration_minutes"))
            ),
            models.CheckConstraint(name="policy_slot_positive", condition=Q(slot_minutes__gte=5)),
        ]

    def __str__(self):
        return f"Policy · {self.scope_label}"

    @property
    def scope_label(self):
        return str(self.resource or self.resource_type or "Campus default")


class Weekday(models.IntegerChoices):
    MON = 0, "Monday"
    TUE = 1, "Tuesday"
    WED = 2, "Wednesday"
    THU = 3, "Thursday"
    FRI = 4, "Friday"
    SAT = 5, "Saturday"
    SUN = 6, "Sunday"


class AvailabilityRule(TenantModel):
    """Opening hours. If any rule exists at the most specific scope, it wins."""

    scope = models.CharField(max_length=12, choices=Scope.choices, default=Scope.TYPE)
    resource_type = models.ForeignKey(
        ResourceType, null=True, blank=True, on_delete=models.CASCADE, related_name="hours"
    )
    resource = models.ForeignKey(Resource, null=True, blank=True, on_delete=models.CASCADE, related_name="hours")
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    opens = models.TimeField()
    closes = models.TimeField()

    class Meta:
        ordering = ["weekday", "opens"]
        constraints = [
            _scope_constraint("hours"),
            models.CheckConstraint(name="hours_open_before_close", condition=Q(opens__lt=models.F("closes"))),
        ]

    def __str__(self):
        return f"{self.get_weekday_display()} {self.opens:%H:%M}–{self.closes:%H:%M}"


class BlackoutKind(models.TextChoices):
    HOLIDAY = "holiday", "Holiday"
    EXAM = "exam", "Examination period"
    EVENT = "event", "University event"
    RESTRICTED = "restricted", "Restricted period"


class Blackout(TenantModel, TimeStampedModel):
    """A period in which bookings are refused (optionally except for some roles)."""

    title = models.CharField(max_length=140)
    kind = models.CharField(max_length=16, choices=BlackoutKind.choices, default=BlackoutKind.HOLIDAY)
    scope = models.CharField(max_length=12, choices=Scope.choices, default=Scope.CAMPUS)
    resource_type = models.ForeignKey(
        ResourceType, null=True, blank=True, on_delete=models.CASCADE, related_name="blackouts"
    )
    resource = models.ForeignKey(Resource, null=True, blank=True, on_delete=models.CASCADE, related_name="blackouts")
    building = models.ForeignKey(Building, null=True, blank=True, on_delete=models.CASCADE, related_name="blackouts")
    period = DateTimeRangeField()
    exempt_roles = ArrayField(models.CharField(max_length=24, choices=Role.choices), default=list, blank=True)
    note = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["period"]
        constraints = [_scope_constraint("blackout")]
        indexes = [models.Index(fields=["scope"])]

    def __str__(self):
        return self.title


class QuotaPeriod(models.TextChoices):
    DAY = "day", "per day"
    WEEK = "week", "per week"
    MONTH = "month", "per month"


class Quota(TenantModel, TimeStampedModel):
    """
    A ceiling on booked hours and/or number of bookings.

    - role quota: applies to each user holding `role` individually
    - department quota: shared by every booking made for members of `department`
    """

    name = models.CharField(max_length=120)
    role = models.CharField(max_length=24, choices=Role.choices, blank=True)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.CASCADE, related_name="quotas")
    resource_type = models.ForeignKey(
        ResourceType, null=True, blank=True, on_delete=models.CASCADE, related_name="quotas"
    )
    period = models.CharField(max_length=8, choices=QuotaPeriod.choices, default=QuotaPeriod.WEEK)
    max_hours = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    max_bookings = models.PositiveSmallIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                name="quota_targets_role_xor_department",
                condition=(Q(role="", department__isnull=False) | (~Q(role="") & Q(department__isnull=True))),
            ),
            models.CheckConstraint(
                name="quota_has_a_limit", condition=Q(max_hours__isnull=False) | Q(max_bookings__isnull=False)
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_departmental(self):
        return self.department_id is not None


class RestrictionTier(TenantModel):
    """Progressive no-show restriction ladder."""

    no_shows = models.PositiveSmallIntegerField(help_text="Unforgiven no-shows within the window")
    window_days = models.PositiveSmallIntegerField(default=30)
    restrict_days = models.PositiveSmallIntegerField(default=0, help_text="0 = warning only")
    label = models.CharField(max_length=80)

    class Meta:
        ordering = ["no_shows"]
        constraints = [models.UniqueConstraint(fields=["institution", "no_shows"], name="uniq_restriction_tier")]

    def __str__(self):
        return self.label
