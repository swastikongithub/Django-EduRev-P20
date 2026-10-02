"""
Staff console: catalogue setup. Resource types, buildings (blocks) and departments.

Campus-wide staff only (facility managers and administrators, i.e. `manage_resources` with
campus-wide scope): these records shape the whole campus, so an assignment-scoped custodian or a
head of department can see the resources page but not redefine the catalogue. Every create,
update and delete is written to the audit log with before/after values. A record can be removed
only while nothing refers to it.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.models import Department
from apps.accounts.permissions import is_campus_wide
from apps.audit.services import record, snapshot
from apps.core.http import is_digits, pk_param
from apps.core.manage_views import staff_required

from .models import Building, ResourceType
from .setup_forms import BuildingForm, DepartmentForm, ResourceTypeForm

TABS = [
    ("types", "Resource types", "grid-3x3"),
    ("buildings", "Blocks", "building"),
    ("departments", "Departments", "graduation-cap"),
]
TAB_KEYS = {t[0] for t in TABS}

# tab -> (model, form, noun, audit prefix, how to count what depends on a row)
KINDS = {
    "types": (ResourceType, ResourceTypeForm, "Resource type", "catalogue.type", ("resources",)),
    "buildings": (Building, BuildingForm, "Block", "catalogue.building", ("resources",)),
    "departments": (Department, DepartmentForm, "Department", "catalogue.department", ("members", "resources")),
}


def _require_campus(user):
    if not is_campus_wide(user):
        raise PermissionDenied("The catalogue is set up by facility managers and administrators.")


def _back(tab):
    return redirect(f"{reverse('manage:catalogue')}?tab={tab}")


def _rows(user, tab):
    model, _form, _noun, _prefix, deps = KINDS[tab]
    qs = model.objects.filter(institution_id=user.institution_id)
    for dep in deps:
        qs = qs.annotate(**{f"n_{dep}": Count(dep, distinct=True)})
    rows = list(qs.order_by(*(("sort_order", "name") if tab == "types" else ("code",))))
    for r in rows:
        r.in_use = sum(getattr(r, f"n_{d}") for d in deps)
    return rows


def _save(request, tab):
    model, form_cls, noun, prefix, _deps = KINDS[tab]
    inst = request.user.institution_id
    pk = request.POST.get("pk")
    if pk:
        instance = get_object_or_404(model, institution_id=inst, pk=pk_param(pk))
        before = snapshot(instance)
    else:
        instance, before = model(institution_id=inst), None
    form = form_cls(request.POST, instance=instance, institution_id=inst)
    if not form.is_valid():
        return {"form": form, "editing": bool(pk)}
    obj = form.save(commit=False)
    obj.institution_id = inst
    obj.save()
    record(
        request.user,
        f"{prefix}.{'update' if before else 'create'}",
        obj,
        before=before,
        after=snapshot(obj),
        request=request,
    )
    messages.success(request, f"{noun} {obj} {'saved' if before else 'added'}.")
    return _back(tab)


def _delete(request, tab):
    model, _form, noun, prefix, deps = KINDS[tab]
    obj = get_object_or_404(model, institution_id=request.user.institution_id, pk=pk_param(request.POST.get("pk")))
    used = {d: getattr(obj, d).count() for d in deps}
    if any(used.values()):
        detail = ", ".join(f"{n} {d}" for d, n in used.items() if n).replace("members", "people")
        messages.error(request, f"{noun} {obj} is still in use ({detail}). Move those first; nothing was removed.")
        return _back(tab)
    record(request.user, f"{prefix}.delete", obj, before=snapshot(obj), request=request, label=str(obj))
    obj.delete()
    messages.success(request, f"{noun} {obj} removed.")
    return _back(tab)


@staff_required("manage_resources")
@require_http_methods(["GET", "POST"])
def catalogue(request):
    user = request.user
    _require_campus(user)
    bound = None
    if request.method == "POST":
        kind, _, verb = request.POST.get("action", "").partition(".")
        if kind not in TAB_KEYS or verb not in ("save", "delete"):
            return HttpResponseBadRequest("Unknown action")
        tab = kind
        result = (_save if verb == "save" else _delete)(request, tab)
        if not isinstance(result, dict):
            return result
        bound = result
    else:
        tab = request.GET.get("tab", "")
        if tab not in TAB_KEYS:
            tab = "types"

    model, form_cls, noun, _prefix, _deps = KINDS[tab]
    inst = user.institution_id
    new_form = form_cls(institution_id=inst)
    edit_form, autoopen = None, ""
    if bound:
        if bound["editing"]:
            edit_form, autoopen = bound["form"], "edit-sheet"
        else:
            new_form, autoopen = bound["form"], "new-sheet"
    elif is_digits(request.GET.get("edit")):
        instance = model.objects.filter(institution_id=inst, pk=request.GET["edit"]).first()
        if instance:
            edit_form, autoopen = form_cls(instance=instance, institution_id=inst), "edit-sheet"
    elif request.GET.get("new") == "1":
        autoopen = "new-sheet"

    return render(
        request,
        "manage/catalogue.html",
        {
            "tab": tab,
            "tabs": TABS,
            "noun": noun,
            "rows": _rows(user, tab),
            "new_form": new_form,
            "edit_form": edit_form,
            "autoopen": autoopen,
        },
    )
