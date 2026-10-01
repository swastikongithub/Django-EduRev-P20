import uuid

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone

from apps.core.models import TenantModel


class Department(TenantModel):
    code = models.CharField(max_length=16)
    name = models.CharField(max_length=160)
    school = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["institution", "code"], name="uniq_department_code")]

    def __str__(self):
        return self.name


class Role(models.TextChoices):
    STUDENT = "student", "Student"
    FACULTY = "faculty", "Faculty"
    STAFF = "staff", "Staff"
    CUSTODIAN = "custodian", "Resource Custodian"
    DEPT_HEAD = "dept_head", "Head of Department"
    FACILITY_MANAGER = "facility_manager", "Facility Manager"
    ADMIN = "admin", "Administrator"


class User(TenantModel, AbstractUser):
    """University identity. `vid` mirrors the UMS registration / employee number."""

    role = models.CharField(max_length=24, choices=Role.choices, default=Role.STUDENT, db_index=True)
    vid = models.CharField("VID", max_length=20, blank=True, db_index=True)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="members")
    section = models.CharField(max_length=20, blank=True)
    programme = models.CharField(max_length=160, blank=True)
    designation = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    calendar_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    mfa_secret = models.TextField(blank=True, help_text="TOTP secret, encrypted at rest (apps.accounts.mfa)")
    mfa_enabled = models.BooleanField(default=False)
    failed_logins = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    class Meta:
        ordering = ["first_name", "last_name"]
        permissions = [
            ("book_resources", "Can book resources"),
            ("book_recurring", "Can create recurring bookings"),
            ("book_on_behalf", "Can book on behalf of a class or group"),
            ("approve_bookings", "Can decide approvals"),
            ("manage_resources", "Can manage resources they are responsible for"),
            ("manage_maintenance", "Can schedule maintenance"),
            ("manage_inventory", "Can manage consumables and accessories"),
            ("view_department_analytics", "Can view departmental utilisation"),
            ("view_campus_analytics", "Can view campus-wide utilisation"),
            ("configure_policy", "Can configure rules, quotas and workflows"),
            ("manage_timetable", "Can publish timetables"),
            ("manage_users", "Can manage users and roles"),
            ("forgive_no_shows", "Can forgive no-shows and lift restrictions"),
            ("view_audit_log", "Can view the audit log"),
        ]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def initials(self):
        parts = [p for p in [self.first_name, self.last_name] if p]
        return "".join(p[0] for p in parts).upper()[:2] or self.username[:2].upper()

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    @property
    def is_staff_side(self):
        return self.role not in (Role.STUDENT,)
