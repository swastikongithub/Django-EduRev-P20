"""
Workflow builder: the form, the ordered steps, plain-English summaries and the
"Who approves this?" explanation (which always defers to resolve_workflow for the answer).
"""

from __future__ import annotations

from dataclasses import dataclass

from django import forms
from django.db import transaction

from apps.accounts.models import Role, User
from apps.audit.services import record, snapshot
from apps.catalogue.manage_forms import StyledFormMixin
from apps.catalogue.models import Resource, ResourceType
from apps.rules.manage_forms import minutes_label

from .models import ApprovalStep, ApprovalWorkflow, ApproverRole
from .services import resolve_workflow

MAX_STEPS = 6
ROLE_PLURAL_CAP = {
    Role.STUDENT: "Students",
    Role.FACULTY: "Faculty",
    Role.STAFF: "Staff",
    Role.CUSTODIAN: "Custodians",
    Role.DEPT_HEAD: "Heads of department",
    Role.FACILITY_MANAGER: "Facility managers",
    Role.ADMIN: "Administrators",
}


def who_phrase(roles) -> str:
    names = [ROLE_PLURAL_CAP.get(r, r) for r in roles or []]
    if not names:
        return "Anyone"
    names = [names[0]] + [n.lower() for n in names[1:]]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def what_phrase(w) -> str:
    if w.resource_id:
        return w.resource.name
    if w.resource_type_id:
        return w.resource_type.plural or w.resource_type.name
    return "anything"


def step_label(step) -> str:
    if step.approver_role == ApproverRole.USER and step.approver_user_id:
        return step.approver_user.display_name
    return step.get_approver_role_display()


def chain_phrase(steps) -> str:
    labels = [step_label(s) for s in steps]
    if not labels:
        return "nobody (no steps yet, so it can't hold a booking)"
    return labels[0] if len(labels) == 1 else ", then ".join(labels)


def describe_workflow(w, steps=None) -> str:
    steps = list(w.steps.all()) if steps is None else steps
    conds = []
    if w.min_attendees:
        conds.append(f"for {w.min_attendees}+ people")
    if w.min_duration_minutes:
        conds.append(f"for {minutes_label(w.min_duration_minutes)} or longer")
    lead = f"{who_phrase(w.requester_roles)} booking {what_phrase(w)}"
    if conds:
        lead += " " + " and ".join(conds)
    if w.auto_approve:
        return f"{lead}: confirmed instantly"
    return f"{lead}: {chain_phrase(steps)}"


class WorkflowForm(StyledFormMixin, forms.ModelForm):
    APPLIES = [("any", "Anything"), ("type", "A resource type"), ("resource", "One resource")]
    applies = forms.ChoiceField(choices=APPLIES, widget=forms.RadioSelect, label="Applies to", initial="type")
    requester_roles = forms.MultipleChoiceField(
        choices=Role.choices, required=False, widget=forms.CheckboxSelectMultiple, label="When the person booking is"
    )

    class Meta:
        model = ApprovalWorkflow
        fields = [
            "name",
            "description",
            "resource_type",
            "resource",
            "requester_roles",
            "min_attendees",
            "min_duration_minutes",
            "auto_approve",
            "priority",
            "active",
        ]
        labels = {
            "name": "Name",
            "description": "Note for other admins",
            "resource_type": "Type",
            "resource": "Resource",
            "min_attendees": "Only when at least this many people",
            "min_duration_minutes": "Only when at least this long (min)",
            "auto_approve": "Confirm instantly",
            "priority": "Priority",
            "active": "Active",
        }
        help_texts = {
            "priority": "When two workflows are equally specific, the higher number wins.",
            "min_attendees": "Leave empty to apply to any group size.",
            "min_duration_minutes": "Leave empty to apply to any length, e.g. 120 for two hours or more.",
        }
        widgets = {
            "min_attendees": forms.NumberInput(attrs={"min": 1, "inputmode": "numeric", "placeholder": "Any number"}),
            "min_duration_minutes": forms.NumberInput(
                attrs={"min": 1, "inputmode": "numeric", "placeholder": "Any length"}
            ),
            "priority": forms.NumberInput(attrs={"min": 0, "inputmode": "numeric"}),
        }
        error_messages = {"name": {"required": "Give the workflow a name, e.g. Seminar halls for students."}}

    def __init__(self, *args, institution_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.institution_id = institution_id
        self.fields["resource_type"].queryset = ResourceType.objects.filter(institution_id=institution_id)
        self.fields["resource"].queryset = Resource.objects.filter(institution_id=institution_id).order_by("code")
        self.fields["resource"].label_from_instance = lambda r: f"{r.code}, {r.name}"
        self.fields["resource_type"].empty_label = "Choose a type"
        self.fields["resource"].empty_label = "Choose a resource"
        if self.instance.pk and not self.is_bound:
            self.initial["applies"] = (
                "resource" if self.instance.resource_id else "type" if self.instance.resource_type_id else "any"
            )
        self.style()

    def clean(self):
        data = super().clean()
        applies = data.get("applies")
        if applies == "type":
            if not data.get("resource_type"):
                self.add_error("resource_type", "Choose which type of resource this workflow covers.")
            data["resource"] = None
        elif applies == "resource":
            if not data.get("resource"):
                self.add_error("resource", "Choose the resource this workflow covers.")
            data["resource_type"] = None
        else:
            data["resource"] = data["resource_type"] = None
        for name in ("min_attendees", "min_duration_minutes"):
            if data.get(name) == 0:
                data[name] = None
        return data


@dataclass
class StepInput:
    approver_role: str
    approver_user: User | None
    sla_hours: int


def parse_steps(post, institution_id) -> tuple[list[StepInput], list[str], list[dict]]:
    """Ordered steps from the repeated step_* fields (order = position on the page). Blank rows are skipped."""
    roles, users, slas = post.getlist("step_role"), post.getlist("step_user"), post.getlist("step_sla")
    valid_roles = {v for v, _ in ApproverRole.choices}
    user_ids = {u for u in users if u.isdigit()}
    people = {str(u.pk): u for u in User.objects.filter(institution_id=institution_id, is_active=True, pk__in=user_ids)}
    steps, errors, echo = [], [], []
    for role, uid, sla in zip(roles, users, slas, strict=False):
        echo.append({"role": role, "user": uid, "sla": sla})
        if not role:
            continue
        n = len(steps) + 1
        if role not in valid_roles:
            errors.append(f"Step {n} has an approver type we don't recognise.")
            continue
        person = None
        if role == ApproverRole.USER:
            person = people.get(uid)
            if not person:
                errors.append(f"Pick the person who approves step {n}.")
                continue
        try:
            hours = int(sla or 24)
            if not 1 <= hours <= 720:
                raise ValueError
        except ValueError:
            errors.append(f"Step {n}: give the approver between 1 and 720 hours to decide.")
            continue
        steps.append(StepInput(role, person, hours))
    if len(steps) > MAX_STEPS:
        errors.append(f"Keep it to {MAX_STEPS} steps or fewer; long chains make people wait.")
    return steps, errors, echo


def workflow_snapshot(w) -> dict:
    data = snapshot(
        w,
        fields=[
            "name",
            "description",
            "resource_type",
            "resource",
            "requester_roles",
            "min_attendees",
            "min_duration_minutes",
            "auto_approve",
            "priority",
            "active",
        ],
    )
    data["steps"] = [f"{s.order}. {step_label(s)} ({s.sla_hours} h)" for s in w.steps.select_related("approver_user")]
    return data


def save_workflow(form: WorkflowForm, steps: list[StepInput], *, actor, request=None) -> ApprovalWorkflow:
    creating = form.instance.pk is None
    before = None if creating else workflow_snapshot(ApprovalWorkflow.objects.get(pk=form.instance.pk))
    with transaction.atomic():
        w = form.save(commit=False)
        w.institution_id = actor.institution_id
        w.save()
        w.steps.all().delete()
        if not w.auto_approve:
            ApprovalStep.objects.bulk_create(
                [
                    ApprovalStep(
                        workflow=w,
                        order=i,
                        approver_role=s.approver_role,
                        approver_user=s.approver_user,
                        sla_hours=s.sla_hours,
                    )
                    for i, s in enumerate(steps, start=1)
                ]
            )
        record(
            actor,
            "workflow.create" if creating else "workflow.update",
            w,
            before=before,
            after=workflow_snapshot(w),
            request=request,
        )
    return w


def validate_workflow(form: WorkflowForm, steps, step_errors) -> list[str]:
    errors = list(step_errors)
    if form.is_valid() and not form.cleaned_data.get("auto_approve") and not steps and not step_errors:
        errors.append("Add at least one approver, or switch on Confirm instantly.")
    return errors


# ── "Who approves this?" ────────────────────────────────────────────────────


def who_is_asked(step, resource) -> list[str]:
    """The people a step would notify for this resource (mirrors services.approvers_for)."""
    qs = User.objects.filter(institution_id=resource.institution_id, is_active=True)
    role = step.approver_role
    if role == ApproverRole.USER:
        qs = qs.filter(pk=step.approver_user_id)
    elif role == ApproverRole.CUSTODIAN:
        qs = qs.filter(custodianships__resource_id=resource.pk)
    elif role == ApproverRole.DEPT_HEAD:
        qs = (
            qs.filter(role=Role.DEPT_HEAD, department_id=resource.department_id)
            if resource.department_id
            else qs.none()
        )
    elif role == ApproverRole.FACILITY_MANAGER:
        qs = qs.filter(role=Role.FACILITY_MANAGER)
    else:
        qs = qs.filter(role=Role.ADMIN)
    return [u.display_name for u in qs.order_by("first_name")[:4]]


def explain(resource, role: str, attendees: int, minutes: int) -> dict:
    """What resolve_workflow() picks for this request, plus why each other candidate didn't apply."""
    probe = User(role=role, institution_id=resource.institution_id)
    chosen = resolve_workflow(resource, probe, attendees, minutes)
    candidates = (
        ApprovalWorkflow.objects.filter(institution_id=resource.institution_id)
        .select_related("resource_type", "resource")
        .prefetch_related("steps__approver_user")
    )
    rows = []
    for w in candidates:
        if w.resource_id and w.resource_id != resource.pk:
            continue
        if w.resource_type_id and w.resource_type_id != resource.type_id:
            continue
        why = []
        if not w.active:
            why.append("it's switched off")
        if w.requester_roles and role not in w.requester_roles:
            why.append(f"only for {who_phrase(w.requester_roles).lower()}")
        if w.min_attendees is not None and attendees < w.min_attendees:
            why.append(f"needs {w.min_attendees}+ people")
        if w.min_duration_minutes is not None and minutes < w.min_duration_minutes:
            why.append(f"needs {minutes_label(w.min_duration_minutes)} or longer")
        if not why and not w.auto_approve and not w.steps.all():
            why.append("it has no approval steps")
        steps = list(w.steps.all())
        rows.append(
            {
                "w": w,
                "chosen": chosen is not None and w.pk == chosen.pk,
                "why": why,
                "summary": describe_workflow(w, steps),
                "specificity": w.specificity,
            }
        )
    rows.sort(key=lambda r: (not r["chosen"], -r["specificity"], -r["w"].priority))
    outranked = [r for r in rows if not r["chosen"] and not r["why"]]
    for r in outranked:
        r["why"] = ["a more specific or higher-priority workflow wins"]
    steps = list(chosen.steps.select_related("approver_user")) if chosen else []
    for s in steps:
        s.asked = who_is_asked(s, resource)
    return {
        "chosen": chosen,
        "steps": steps,
        "rows": rows,
        "resource": resource,
        "role": role,
        "attendees": attendees,
        "minutes": minutes,
        "role_label": Role(role).label,
    }
