"""
M4 — Timetable Integration.

The published timetable (from P13, or a CSV export in the interim) is consumed
as a *hard* availability constraint: each class occurrence is written into the
BookingSlot ledger, so the booking exclusion constraint covers it too.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalogue.models import Resource
from apps.core.models import TenantModel, TimeStampedModel


class AcademicTerm(TenantModel):
    code = models.CharField(max_length=16, help_text="UMS term code, e.g. 26271")
    name = models.CharField(max_length=80)
    starts = models.DateField()
    ends = models.DateField()

    class Meta:
        ordering = ["-starts"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "code"], name="uniq_term_code"),
            models.CheckConstraint(name="term_dates_ordered", condition=Q(starts__lt=models.F("ends"))),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class PublicationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    SUPERSEDED = "superseded", "Superseded"
    FAILED = "failed", "Failed"


class TimetablePublication(TenantModel, TimeStampedModel):
    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE, related_name="publications")
    version = models.PositiveIntegerField()
    source = models.CharField(max_length=32, default="csv", help_text="csv | p13-api | manual")
    status = models.CharField(max_length=12, choices=PublicationStatus.choices, default=PublicationStatus.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    entry_count = models.PositiveIntegerField(default=0)
    occurrence_count = models.PositiveIntegerField(default=0)
    displaced_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    errors = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["term", "version"], name="uniq_publication_version"),
            models.UniqueConstraint(
                fields=["term"], condition=Q(status="published"), name="one_published_timetable_per_term"
            ),
        ]

    def __str__(self):
        return f"{self.term.code} v{self.version}"


class TimetableEntry(models.Model):
    publication = models.ForeignKey(TimetablePublication, on_delete=models.CASCADE, related_name="entries")
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="timetable_entries")
    weekday = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    course_code = models.CharField(max_length=16)
    course_title = models.CharField(max_length=160, blank=True)
    section = models.CharField(max_length=24, blank=True)
    faculty = models.CharField(max_length=120, blank=True)
    kind = models.CharField(max_length=16, default="Lecture", help_text="Lecture | Practical | Tutorial")

    class Meta:
        ordering = ["weekday", "start_time"]
        constraints = [
            models.CheckConstraint(name="entry_times_ordered", condition=Q(start_time__lt=models.F("end_time"))),
            models.CheckConstraint(name="entry_weekday_valid", condition=Q(weekday__gte=0, weekday__lte=6)),
        ]

    def __str__(self):
        return f"{self.course_code} {self.section} · {self.resource.code}"

    @property
    def label(self):
        bits = [self.course_code, self.kind]
        if self.section:
            bits.append(self.section)
        return " · ".join(bits)
