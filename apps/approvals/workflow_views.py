"""Staff console: the approval workflow builder, with a live "Who approves this?" tester."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.models import Role, User
from apps.accounts.permissions import is_campus_wide
from apps.audit.services import record
from apps.catalogue.models import Resource
from apps.core.http import MAX_PK, int_param, is_digits, pk_param
from apps.core.manage_views import staff_required

from .models import ApprovalStep, ApprovalWorkflow, ApproverRole
from .workflow_forms import (
    MAX_STEPS,
    WorkflowForm,
    describe_workflow,
    explain,
    parse_steps,
    save_workflow,
    validate_workflow,
    workflow_snapshot,
)

DURATIONS = [30, 60, 90, 120, 180, 240, 360, 480]


def _workflows(inst):
    return (
        ApprovalWorkflow.objects.filter(institution_id=inst)
        .select_related("resource_type", "resource")
        .prefetch_related(Prefetch("steps", queryset=ApprovalStep.objects.select_related("approver_user")))
    )


def _tester_input(request, inst):
    g = request.GET
    resource = (
        Resource.objects.filter(institution_id=inst, pk=int_param(g.get("resource"), 0, lo=0, hi=MAX_PK))
        .select_related("type")
        .first()
    )
    role = g.get("role") if g.get("role") in Role.values else Role.STUDENT
    try:
        attendees = max(1, min(5000, int(g.get("attendees") or 1)))
        minutes = max(1, min(1440, int(g.get("minutes") or 60)))
    except ValueError:
        attendees, minutes = 1, 60
    return resource, role, attendees, minutes


@staff_required("configure_policy")
@require_http_methods(["GET", "POST"])
def workflows(request):
    user = request.user
    inst = user.institution_id
    can_edit = is_campus_wide(user)

    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        return _post(request)

    resource, role, attendees, minutes = _tester_input(request, inst)
    test = explain(resource, role, attendees, minutes) if resource else None
    if request.headers.get("HX-Request") and "test" in request.GET:
        return render(request, "manage/setup/_workflow_test.html", {"test": test})

    ctx = {
        "can_edit": can_edit,
        "test": test,
        "durations": DURATIONS,
        "roles": Role.choices,
        "tester": {
            "resource": resource.pk if resource else None,
            "role": role,
            "attendees": attendees,
            "minutes": minutes,
        },
        "resources": Resource.objects.filter(institution_id=inst)
        .select_related("type")
        .order_by("type__sort_order", "code"),
    }
    editing = request.GET.get("edit")
    if can_edit and (request.GET.get("new") or is_digits(editing)):
        instance = (
            get_object_or_404(ApprovalWorkflow, institution_id=inst, pk=editing)
            if editing
            else ApprovalWorkflow(institution_id=inst)
        )
        form = WorkflowForm(instance=instance, institution_id=inst)
        rows = (
            [
                {"role": s.approver_role, "user": str(s.approver_user_id or ""), "sla": s.sla_hours}
                for s in instance.steps.all()
            ]
            if instance.pk
            else [{"role": ApproverRole.CUSTODIAN, "user": "", "sla": 24}]
        )
        ctx.update(_editor_ctx(inst, form, rows, []))
    else:
        ctx.update(_list_ctx(inst))
    return render(request, "manage/workflows.html", ctx)


def _list_ctx(inst):
    groups = {2: [], 1: [], 0: []}
    for w in _workflows(inst):
        w.summary = describe_workflow(w, list(w.steps.all()))
        groups[w.specificity].append(w)
    return {
        "groups": [
            ("For one resource", "Checked first.", groups[2]),
            ("For a resource type", "Checked when no resource-level workflow matches.", groups[1]),
            ("For anything", "The fallback when nothing more specific matches.", groups[0]),
        ],
        "count": sum(len(v) for v in groups.values()),
        "active": sum(1 for v in groups.values() for w in v if w.active),
    }


def _editor_ctx(inst, form, rows, errors):
    people = (
        User.objects.filter(institution_id=inst, is_active=True)
        .exclude(role=Role.STUDENT)
        .order_by("role", "first_name", "last_name")
    )
    return {
        "form": form,
        "step_rows": rows or [{"role": "", "user": "", "sla": 24}],
        "step_errors": errors,
        "approver_roles": ApproverRole.choices,
        "people": people,
        "max_steps": MAX_STEPS,
        "editing": True,
    }


def _post(request):
    inst = request.user.institution_id
    action = request.POST.get("action")
    if action == "save":
        pk = request.POST.get("pk")
        instance = (
            get_object_or_404(ApprovalWorkflow, institution_id=inst, pk=pk_param(pk))
            if pk
            else ApprovalWorkflow(institution_id=inst)
        )
        form = WorkflowForm(request.POST, instance=instance, institution_id=inst)
        steps, step_errors, echo = parse_steps(request.POST, inst)
        errors = validate_workflow(form, steps, step_errors)
        if form.is_valid() and not errors:
            w = save_workflow(form, steps, actor=request.user, request=request)
            messages.success(
                request,
                f"{w.name} saved. {describe_workflow(w)}. It applies to the next booking; "
                "requests already waiting keep their current approvers.",
            )
            return redirect(reverse("manage:workflows") + f"#wf-{w.pk}")
        ctx = {
            "can_edit": True,
            "test": None,
            "durations": DURATIONS,
            "roles": Role.choices,
            "tester": {},
            "resources": Resource.objects.filter(institution_id=inst).select_related("type").order_by("code"),
        }
        ctx.update(_editor_ctx(inst, form, echo, errors))
        return render(request, "manage/workflows.html", ctx)

    w = get_object_or_404(ApprovalWorkflow, institution_id=inst, pk=pk_param(request.POST.get("pk")))
    if action == "toggle":
        before = workflow_snapshot(w)
        w.active = not w.active
        w.save(update_fields=["active", "updated_at"])
        record(
            request.user,
            f"workflow.{'activate' if w.active else 'deactivate'}",
            w,
            before=before,
            after=workflow_snapshot(w),
            request=request,
        )
        messages.success(
            request,
            f"{w.name} is {'on. It applies from the next booking' if w.active else 'off. New bookings skip it'}.",
        )
        return redirect(reverse("manage:workflows") + f"#wf-{w.pk}")
    if action == "delete":
        record(request.user, "workflow.delete", w, before=workflow_snapshot(w), request=request)
        name = w.name
        w.delete()
        messages.success(request, f"{name} deleted. Requests already waiting keep their approvers.")
        return redirect("manage:workflows")
    return HttpResponseBadRequest("Unknown action")
