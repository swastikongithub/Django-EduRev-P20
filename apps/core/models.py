from django.conf import settings
from django.db import DatabaseError, models


class Institution(models.Model):
    """Tenant root. Every domain record carries an institution (CES §1.2)."""

    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=40, blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name


_default_institution_pk = None


def default_institution_id():
    """Primary key of the default tenant (cached). Safe to call before migrations."""
    global _default_institution_pk
    if _default_institution_pk is None:
        try:
            inst, _ = Institution.objects.get_or_create(
                code=settings.DEFAULT_INSTITUTION_CODE,
                defaults={"name": "Lovely Professional University", "short_name": "LPU"},
            )
        except DatabaseError:
            return None
        _default_institution_pk = inst.pk
    return _default_institution_pk


def reset_default_institution_cache():
    global _default_institution_pk
    _default_institution_pk = None


class TenantModel(models.Model):
    institution = models.ForeignKey(
        Institution, on_delete=models.PROTECT, default=default_institution_id, related_name="+"
    )

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SweepRun(models.Model):
    """Operational record of each background sweep, surfaced on the ops page."""

    task = models.CharField(max_length=64, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    affected = models.PositiveIntegerField(default=0)
    detail = models.JSONField(default=dict, blank=True)
    ok = models.BooleanField(default=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["task", "-started_at"])]
