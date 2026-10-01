"""
Console scope: which resources a staff member operates.

    custodian          -> the resources they are custodian of
    dept_head          -> resources owned by their department
    facility_manager / admin -> the whole campus

Every console screen narrows its querysets with these helpers, then re-checks the
object-level rule (`can_manage_resource`, `can_decide`, ...) before acting.
"""

from __future__ import annotations

from django.db.models import Q

from apps.accounts.models import Role
from apps.accounts.permissions import is_campus_wide


def managed_resources(user):
    from apps.catalogue.models import Custodian, Resource

    qs = Resource.objects.filter(institution_id=user.institution_id).exclude(status="retired")
    if is_campus_wide(user):
        return qs
    if user.role == Role.CUSTODIAN:
        return qs.filter(pk__in=Custodian.objects.filter(user=user).values("resource_id"))
    if user.role == Role.DEPT_HEAD and user.department_id:
        return qs.filter(department_id=user.department_id)
    return qs.none()


def resource_q(user, prefix: str = "resource") -> Q:
    """A Q narrowing any model with a `resource` FK to the user's scope (Q() when campus-wide)."""
    if is_campus_wide(user):
        return Q()
    return Q(**{f"{prefix}_id__in": managed_resources(user).values("pk")})


def scope_label(user) -> str:
    if is_campus_wide(user):
        return "Across campus"
    if user.role == Role.CUSTODIAN:
        return "Resources you look after"
    if user.role == Role.DEPT_HEAD and user.department_id:
        return f"{user.department.name}"
    return "Your resources"
