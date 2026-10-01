"""Staff console: people and roles. Administrators change roles and (de)activate; facility managers can look."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.audit.services import record
from apps.core.http import safe_next
from apps.core.manage_views import staff_required

from .models import Department, Role, User
from .permissions import has_cap, is_campus_wide

ROLE_HELP = {
    Role.STUDENT: "Books for themselves.",
    Role.FACULTY: "Books for classes and weekly series.",
    Role.STAFF: "Books for offices and events.",
    Role.CUSTODIAN: "Runs assigned resources: approvals, upkeep, stock, no-shows.",
    Role.DEPT_HEAD: "Approves for the department, sets its quotas, sees its insights.",
    Role.FACILITY_MANAGER: "Runs the whole campus: rules, workflows, timetable, audit.",
    Role.ADMIN: "Everything, including users and roles.",
}


class Refused(Exception):
    pass


def change_role(target: User, new_role: str, *, actor, request=None) -> User:
    """Change a role (the Group follows via the post_save signal), refusing to leave nobody in charge."""
    if new_role not in Role.values:
        raise Refused("Choose one of the listed roles.")
    if new_role == target.role:
        raise Refused(f"{target.display_name} is already {target.get_role_display().lower()}.")
    with transaction.atomic():
        target = User.objects.select_for_update().get(pk=target.pk)
        if target.role == Role.ADMIN and new_role != Role.ADMIN:
            admins = User.objects.select_for_update().filter(institution_id=target.institution_id, role=Role.ADMIN,
                                                             is_active=True)
            if admins.exclude(pk=target.pk).count() == 0:
                raise Refused(f"{target.display_name} is the last active administrator. Make someone else an "
                              "administrator first, so nobody is locked out of user management.")
        before = {"role": target.role}
        target.role = new_role
        target.save(update_fields=["role"])  # signal re-syncs the role group
        record(actor, "user.role_change", target, before=before, after={"role": new_role}, request=request)
    return target


def set_active(target: User, active: bool, *, actor, request=None) -> User:
    if target.pk == actor.pk and not active:
        raise Refused("You can't deactivate your own account. Ask another administrator.")
    if target.is_active == active:
        raise Refused(f"{target.display_name} is already {'active' if active else 'deactivated'}.")
    with transaction.atomic():
        target = User.objects.select_for_update().get(pk=target.pk)
        if not active and target.role == Role.ADMIN and not User.objects.filter(
                institution_id=target.institution_id, role=Role.ADMIN, is_active=True).exclude(pk=target.pk).exists():
            raise Refused(f"{target.display_name} is the last active administrator and can't be deactivated.")
        target.is_active = active
        target.save(update_fields=["is_active"])
        record(actor, "user.activate" if active else "user.deactivate", target, before={"is_active": not active},
               after={"is_active": active}, request=request)
    return target


@staff_required()
@require_http_methods(["GET", "POST"])
def users(request):
    actor = request.user
    can_manage = has_cap(actor, "manage_users")
    if not (can_manage or is_campus_wide(actor)):
        raise PermissionDenied
    inst = actor.institution_id

    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied
        target = get_object_or_404(User, institution_id=inst, pk=request.POST.get("user"))
        action = request.POST.get("action")
        try:
            if action == "role":
                change_role(target, request.POST.get("role", ""), actor=actor, request=request)
                target.refresh_from_db()
                messages.success(request, f"{target.display_name} is now {target.get_role_display().lower()}. "
                                          "Their menus and permissions change on their next page load.")
            elif action in ("activate", "deactivate"):
                set_active(target, action == "activate", actor=actor, request=request)
                messages.success(request, f"{target.display_name} {'can sign in again' if action == 'activate' else 'can no longer sign in. Their bookings and history are kept'}.")
            else:
                return HttpResponseBadRequest("Unknown action")
        except Refused as exc:
            messages.error(request, str(exc))
        return redirect(safe_next(request, reverse("manage:users")))

    from apps.checkins.models import Restriction

    f = {k: request.GET.get(k, "").strip() for k in ("q", "role", "department", "status")}
    qs = User.objects.filter(institution_id=inst).select_related("department")
    if f["q"]:
        qs = qs.filter(Q(first_name__icontains=f["q"]) | Q(last_name__icontains=f["q"]) | Q(username__icontains=f["q"])
                       | Q(vid__icontains=f["q"]) | Q(email__icontains=f["q"]))
    if f["role"] in Role.values:
        qs = qs.filter(role=f["role"])
    if f["department"]:
        qs = qs.filter(department__code=f["department"])
    now = timezone.now()
    restricted_ids = Restriction.objects.filter(institution_id=inst, starts_at__lte=now, ends_at__gt=now,
                                                lifted_at__isnull=True).values("user_id")
    if f["status"] == "active":
        qs = qs.filter(is_active=True)
    elif f["status"] == "inactive":
        qs = qs.filter(is_active=False)
    elif f["status"] == "restricted":
        qs = qs.filter(pk__in=restricted_ids)
    page = Paginator(qs.order_by("first_name", "last_name", "username"), 25).get_page(request.GET.get("page"))
    restrictions = {r.user_id: r for r in Restriction.objects.filter(
        user_id__in=[u.pk for u in page], starts_at__lte=now, ends_at__gt=now, lifted_at__isnull=True).order_by("ends_at")}
    for u in page:
        u.restriction = restrictions.get(u.pk)
    counts = dict(User.objects.filter(institution_id=inst, is_active=True).values_list("role").annotate(n=Count("id")))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "manage/users.html", {
        "page": page, "filters": f, "filtered": any(f.values()), "can_manage": can_manage,
        "roles": Role.choices, "role_help": [(v, label, ROLE_HELP[v], counts.get(v, 0)) for v, label in Role.choices],
        "departments": Department.objects.filter(institution_id=inst),
        "querystring": params.urlencode(), "here": request.get_full_path(),
    })
