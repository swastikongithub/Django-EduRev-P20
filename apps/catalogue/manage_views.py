"""Staff console: the resource catalogue (list, create/edit, CSV import, printable door QR)."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.checkins.qr import door_url, svg
from apps.core.manage_views import staff_required

from .manage_forms import (
    IMPORT_COLUMNS,
    SAMPLE_CSV,
    ResourceForm,
    can_create_resources,
    can_edit_resource,
    commit_import,
    manageable_resources,
    parse_attributes,
    parse_import,
    read_csv_upload,
    save_resource,
)
from .models import Building, Custodian, Resource, ResourceStatus, ResourceType

RESOURCE_CAPS = ("manage_resources", "approve_bookings")


@staff_required(*RESOURCE_CAPS)
@require_http_methods(["GET", "POST"])
def resources(request):
    user = request.user
    if request.method == "POST" or request.GET.get("import"):
        return _import(request)

    scope = manageable_resources(user)
    qs = scope.select_related("type", "building", "department").prefetch_related(
        Prefetch("custodians", queryset=Custodian.objects.select_related("user"))
    )
    f = {k: request.GET.get(k, "").strip() for k in ("q", "type", "building", "status")}
    if f["q"]:
        qs = qs.filter(Q(name__icontains=f["q"]) | Q(code__icontains=f["q"]) | Q(tagline__icontains=f["q"]))
    if f["type"]:
        qs = qs.filter(type__code=f["type"])
    if f["building"]:
        qs = qs.filter(building__code=f["building"])
    if f["status"] == "unbookable":
        qs = qs.filter(is_bookable=False)
    elif f["status"]:
        qs = qs.filter(status=f["status"])
    page = Paginator(qs.order_by("type__sort_order", "building__code", "code"), 30).get_page(request.GET.get("page"))
    for r in page:
        r.editable = can_edit_resource(user, r)
    totals = scope.aggregate(
        total=Count("id"),
        out=Count("id", filter=Q(status=ResourceStatus.OUT_OF_SERVICE)),
        unbookable=Count("id", filter=Q(is_bookable=False)),
    )
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "manage/resources.html",
        {
            "page": page,
            "filters": f,
            "filtered": any(f.values()),
            "totals": totals,
            "types": ResourceType.objects.filter(institution_id=user.institution_id),
            "buildings": Building.objects.filter(institution_id=user.institution_id),
            "statuses": ResourceStatus.choices,
            "can_create": can_create_resources(user),
            "querystring": params.urlencode(),
        },
    )


def _import(request):
    """CSV bulk import: upload, preview every row with its problems, then confirm (all or nothing)."""
    if not can_create_resources(request.user):
        raise PermissionDenied
    if request.GET.get("sample"):
        resp = HttpResponse(SAMPLE_CSV, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="lpu-reserve-resources-template.csv"'
        return resp
    ctx = {"columns": IMPORT_COLUMNS, "preview": None, "text": "", "error": ""}
    action = request.POST.get("action")
    if action == "import_preview":
        try:
            ctx["text"] = read_csv_upload(request.FILES.get("file"))
            ctx["preview"] = parse_import(ctx["text"], request.user.institution_id)
        except ValidationError as exc:
            ctx["error"] = exc.messages[0]
    elif action == "import_confirm":
        # Never trust the round-tripped text: validate it again before writing anything.
        text = request.POST.get("csv_text", "")
        preview = parse_import(text, request.user.institution_id)
        if preview.ok:
            created = commit_import(preview, actor=request.user, request=request)
            messages.success(
                request,
                f"Imported {len(created)} resource{'s' if len(created) != 1 else ''}. "
                "They're bookable now under each type's rules.",
            )
            return redirect(reverse("manage:resources") + "?status=active")
        ctx.update(
            text=text,
            preview=preview,
            error="Something changed since you checked the file, so nothing was imported. Review the rows below.",
        )
    return render(request, "manage/resource_import.html", ctx)


@staff_required("manage_resources")
@require_http_methods(["GET", "POST"])
def resource_new(request):
    if not can_create_resources(request.user):
        raise PermissionDenied
    return _resource_form(request, Resource(institution_id=request.user.institution_id))


@staff_required(*RESOURCE_CAPS)
@require_http_methods(["GET", "POST"])
def resource_edit(request, pk):
    # Out-of-scope resources are a 404, not a 403: custodians shouldn't learn what else exists.
    resource = get_object_or_404(manageable_resources(request.user).select_related("type", "building"), pk=pk)
    if not can_edit_resource(request.user, resource):
        raise PermissionDenied
    return _resource_form(request, resource)


def _resource_form(request, resource):
    creating = resource.pk is None
    if request.method == "POST":
        form = ResourceForm(request.POST, request.FILES, instance=resource, user=request.user)
        attributes, attr_errors = parse_attributes(request.POST)
        if form.is_valid() and not attr_errors:
            saved = save_resource(form, attributes, actor=request.user, request=request)
            messages.success(
                request,
                f"{saved.name} {'added' if creating else 'saved'}. Changes apply to new bookings straight away.",
            )
            return redirect("manage:resource_edit", saved.pk)
        attr_rows = list(zip(request.POST.getlist("attr_key"), request.POST.getlist("attr_value"), strict=False))
    else:
        form = ResourceForm(instance=resource, user=request.user)
        attr_errors = []
        attr_rows = [(a.key, a.value) for a in resource.attributes.all()] if not creating else []
    from apps.rules.services import policy_for, weekly_hours

    ctx = {
        "form": form,
        "r": resource,
        "creating": creating,
        "attr_rows": attr_rows or [("", "")],
        "attr_errors": attr_errors,
        "error_count": len(form.errors) + len(attr_errors),
    }
    if not creating:
        ctx["policy"] = policy_for(resource)
        ctx["hours"] = _hours_summary(weekly_hours(resource))
        ctx["custodian_list"] = resource.custodians.select_related("user")
    return render(request, "manage/resource_form.html", ctx)


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _hours_summary(hours):
    out = []
    for wd, name in enumerate(WEEKDAYS):
        spans = hours.get(wd, [])
        out.append((name, ", ".join(f"{o:%H:%M}–{c:%H:%M}" for o, c in spans) or "Closed"))
    return out


@never_cache
@staff_required(*RESOURCE_CAPS)
def door_qr(request, pk):
    resource = get_object_or_404(manageable_resources(request.user).select_related("type", "building"), pk=pk)
    url = door_url(resource)
    contacts = resource.custodians.select_related("user").order_by("-is_primary")
    return render(
        request, "manage/door_qr.html", {"r": resource, "qr": svg(url, box_size=12), "url": url, "contacts": contacts}
    )
