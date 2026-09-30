"""
Role-based access control.

Each role maps to a Django Group carrying a set of permissions (the RBAC half).
Object-level checks (the attribute half) live in `can_manage_resource` and the
per-app `visible_*` queryset helpers. Templates only *reflect* these checks;
every view and API endpoint enforces them server-side.
"""

from django.contrib.auth.models import Group, Permission

from .models import Role

P = "accounts."

ROLE_PERMISSIONS: dict[str, set[str]] = {
    Role.STUDENT: {"book_resources"},
    Role.FACULTY: {"book_resources", "book_recurring", "book_on_behalf"},
    Role.STAFF: {"book_resources", "book_recurring", "book_on_behalf"},
    Role.CUSTODIAN: {
        "book_resources",
        "book_recurring",
        "approve_bookings",
        "manage_resources",
        "manage_maintenance",
        "manage_inventory",
        "forgive_no_shows",
    },
    Role.DEPT_HEAD: {
        "book_resources",
        "book_recurring",
        "book_on_behalf",
        "approve_bookings",
        "view_department_analytics",
        "configure_policy",
    },
    Role.FACILITY_MANAGER: {
        "book_resources",
        "book_recurring",
        "book_on_behalf",
        "approve_bookings",
        "manage_resources",
        "manage_maintenance",
        "manage_inventory",
        "view_department_analytics",
        "view_campus_analytics",
        "configure_policy",
        "manage_timetable",
        "forgive_no_shows",
        "view_audit_log",
    },
    Role.ADMIN: {
        "book_resources",
        "book_recurring",
        "book_on_behalf",
        "approve_bookings",
        "manage_resources",
        "manage_maintenance",
        "manage_inventory",
        "view_department_analytics",
        "view_campus_analytics",
        "configure_policy",
        "manage_timetable",
        "manage_users",
        "forgive_no_shows",
        "view_audit_log",
    },
}

# Roles with campus-wide (not assignment-scoped) authority over resources.
CAMPUS_WIDE_ROLES = {Role.FACILITY_MANAGER, Role.ADMIN}


def group_name(role: str) -> str:
    return f"role:{role}"


def sync_role_groups(**_kwargs):
    """Create/refresh one Group per role. Idempotent; runs on post_migrate."""
    perms = {p.codename: p for p in Permission.objects.filter(content_type__app_label="accounts")}
    for role, codenames in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=group_name(role))
        group.permissions.set([perms[c] for c in codenames if c in perms])


def assign_role_group(user):
    role_groups = Group.objects.filter(name__startswith="role:")
    user.groups.remove(*role_groups.exclude(name=group_name(user.role)))
    group = Group.objects.filter(name=group_name(user.role)).first()
    if group:
        user.groups.add(group)


def has_cap(user, codename: str) -> bool:
    if not user or not user.is_authenticated or not user.is_active:
        return False
    return user.has_perm(P + codename)


def is_campus_wide(user) -> bool:
    return user.is_authenticated and (user.role in CAMPUS_WIDE_ROLES or user.is_superuser)


def can_manage_resource(user, resource) -> bool:
    """Object-level check: may this user operate this resource?"""
    if not has_cap(user, "manage_resources") and not has_cap(user, "approve_bookings"):
        return False
    if is_campus_wide(user):
        return True
    if user.role == Role.CUSTODIAN:
        return resource.custodians.filter(user=user).exists()
    if user.role == Role.DEPT_HEAD:
        return resource.department_id is not None and resource.department_id == user.department_id
    return False
