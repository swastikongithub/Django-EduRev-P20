"""M9 — Analytics & Reporting."""

from django.db import models

from apps.catalogue.models import Resource


class UtilisationSnapshot(models.Model):
    """Daily roll-up per resource, built nightly by Celery Beat (and on demand)."""

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="snapshots")
    date = models.DateField(db_index=True)
    open_minutes = models.PositiveIntegerField(
        default=0, help_text="Bookable supply after hours, blackouts, maintenance"
    )
    class_minutes = models.PositiveIntegerField(default=0)
    maintenance_minutes = models.PositiveIntegerField(default=0)
    booked_minutes = models.PositiveIntegerField(default=0)
    used_minutes = models.PositiveIntegerField(default=0, help_text="Booked minutes that were checked into")
    released_minutes = models.PositiveIntegerField(default=0, help_text="No-show / early check-out time returned")
    bookings = models.PositiveIntegerField(default=0)
    no_shows = models.PositiveIntegerField(default=0)
    cancellations = models.PositiveIntegerField(default=0)
    denied_attempts = models.PositiveIntegerField(
        default=0, help_text="Unmet demand: attempts refused for lack of supply"
    )
    hourly_booked = models.JSONField(default=list, blank=True, help_text="24 buckets of booked minutes")
    built_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["resource", "date"], name="uniq_snapshot_resource_date")]

    @property
    def utilisation(self):
        """(class + booked) / (open + class), 0..1 — see apps.analytics.services for why."""
        supply = self.open_minutes + self.class_minutes
        return min(1.0, (self.class_minutes + self.booked_minutes) / supply) if supply else 0.0

    @property
    def idle_minutes(self):
        return max(0, self.open_minutes - self.booked_minutes)
