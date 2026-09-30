"""
M5 — Approval Workflow.

Workflows are rows, not code: an administrator changes who approves what from
the workflow builder and the change takes effect on the next booking — no
deployment. Matching is most-specific-first (resource > type > any), then by
priority.
"""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from apps.accounts.models import Role
from apps.bookings.models import Booking
from apps.catalogue.models import Resource, ResourceType
from apps.core.models import TenantModel, TimeStampedModel


class ApprovalWorkflow(TenantModel, TimeStampedModel):
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=240, blank=True)
    resource_type = models.ForeignKey(
        ResourceType, null=True, blank=True, on_delete=models.CASCADE, related_name="workflows"
    )
    resource = models.ForeignKey(Resource, null=True, blank=True, on_delete=models.CASCADE, related_name="workflows")
    requester_roles = ArrayField(
        models.CharField(max_length=24, choices=Role.choices),
        default=list,
        blank=True,
        help_text="Applies when the person booking holds one of these roles. Empty = any role.",
    )
    min_attendees = models.PositiveIntegerField(null=True, blank=True, help_text="Only when attendees ≥ this")
    min_duration_minutes = models.PositiveIntegerField(null=True, blank=True, help_text="Only when longer than this")
    auto_approve = models.BooleanField(default=False, help_text="Matching bookings are confirmed instantly")
    priority = models.PositiveSmallIntegerField(default=100)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-priority", "name"]
        constraints = [
            models.CheckConstraint(
                name="workflow_resource_or_type_not_both",
                condition=~Q(resource__isnull=False, resource_type__isnull=False),
            )
        ]

    def __str__(self):
        return self.name

    @property
    def specificity(self):
        return 2 if self.resource_id else 1 if self.resource_type_id else 0


class ApproverRole(models.TextChoices):
    CUSTODIAN = "custodian", "Resource custodian"
    DEPT_HEAD = "dept_head", "Head of owning department"
    FACILITY_MANAGER = "facility_manager", "Facility manager"
    ADMIN = "admin", "Administrator"
    USER = "user", "Named person"


class ApprovalStep(models.Model):
    workflow = models.ForeignKey(ApprovalWorkflow, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField()
    approver_role = models.CharField(max_length=24, choices=ApproverRole.choices)
    approver_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    sla_hours = models.PositiveSmallIntegerField(default=24)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["workflow", "order"], name="uniq_step_order"),
            models.CheckConstraint(
                name="step_named_user_when_user_role",
                condition=~Q(approver_role="user") | Q(approver_user__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.order}. {self.get_approver_role_display()}"


class Decision(models.TextChoices):
    WAITING = "waiting", "Waiting"
    PENDING = "pending", "Awaiting decision"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    SKIPPED = "skipped", "Not required"


class Approval(models.Model):
    """One step of one booking's approval chain — also its audit trail."""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="approvals")
    workflow = models.ForeignKey(ApprovalWorkflow, null=True, on_delete=models.SET_NULL, related_name="+")
    step_order = models.PositiveSmallIntegerField()
    approver_role = models.CharField(max_length=24, choices=ApproverRole.choices)
    approver_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decision = models.CharField(max_length=10, choices=Decision.choices, default=Decision.WAITING, db_index=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="approvals_decided"
    )
    comment = models.CharField(max_length=500, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["booking", "step_order"]
        constraints = [models.UniqueConstraint(fields=["booking", "step_order"], name="uniq_approval_step")]

    def __str__(self):
        return f"{self.booking.reference} step {self.step_order}: {self.decision}"
