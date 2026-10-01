"""
Maintenance (/manage/maintenance/): open breakdown reports, the next 14 days of planned
windows, and a schedule form that shows what a window would displace *before* it is created.
Every action goes through apps.maintenance.services, which re-checks can_manage_resource.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.db.models import Case, IntegerField, Value, When
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.errors import DomainError
from apps.core.http import safe_next
from apps.core.manage_views import staff_required
from apps.core.scope import managed_resources, resource_q, scope_label
from apps.core.timeutil import aware, trange

from . import services
from .models import BreakdownReport, MaintenanceKind, MaintenanceWindow, ReportStatus, Severity, WindowStatus

HORIZON_DAYS = 14
OPEN_WINDOW = (WindowStatus.SCHEDULED, WindowStatus.IN_PROGRESS)
SEVERITY_ORDER = Case(
    When(severity=Severity.CRITICAL, then=Value(0)),
    When(severity=Severity.HIGH, then=Value(1)),
    default=Value(2),
    output_field=IntegerField(),
)


def _windows(user):
    return MaintenanceWindow.objects.filter(institution_id=user.institution_id).filter(resource_q(user))


def _reports(user):
    return BreakdownReport.objects.filter(institution_id=user.institution_id).filter(resource_q(user))


def _default_form(request, resources):
    tomorrow = timezone.localdate() + timedelta(days=1)
    form = {
        "resource": request.GET.get("resource", ""),
        "start_date": tomorrow.isoformat(),
        "start_time": "08:00",
        "end_date": tomorrow.isoformat(),
        "end_time": "10:00",
        "kind": MaintenanceKind.PREVENTIVE,
        "title": "",
        "vendor": "",
        "notes": "",
    }
    report_id = request.GET.get("report")
    if report_id and report_id.isdigit():
        report = _reports(request.user).filter(pk=report_id).first()
        if report:
            form.update(resource=str(report.resource_id), kind=MaintenanceKind.REPAIR, title=f"Repair: {report.summary}"[:140])
    return form


def _render(request, *, form=None, preview=None, errors=None, error=None):
    user, now = request.user, timezone.now()
    today = timezone.localdate()
    resources = list(managed_resources(user).select_related("building").order_by("name"))
    horizon_end = aware(today + timedelta(days=HORIZON_DAYS), time.min)
    upcoming = list(
        _windows(user)
        .filter(status__in=OPEN_WINDOW, period__overlap=trange(aware(today, time.min), horizon_end))
        .select_related("resource__type", "resource__building", "created_by")
        .order_by("period")
    )
    days = []
    for i in range(HORIZON_DAYS):
        d = today + timedelta(days=i)
        lo, hi = aware(d, time.min), aware(d + timedelta(days=1), time.min)
        items = [
            {"w": w, "continues": w.start < lo, "carries_on": w.end > hi}
            for w in upcoming
            if w.start < hi and w.end > lo
        ]
        days.append({"date": d, "items": items})
    reports = list(
        _reports(user)
        .exclude(status=ReportStatus.RESOLVED)
        .select_related("resource__building", "reported_by", "window")
        .annotate(rank=SEVERITY_ORDER)
        .order_by("rank", "-created_at")
    )
    history = list(
        _windows(user)
        .filter(status__in=(WindowStatus.COMPLETED, WindowStatus.CANCELLED))
        .select_related("resource", "created_by")
        .order_by("-period")[:15]
    )
    ctx = {
        "days": days,
        "busy_days": [d for d in days if d["items"]],
        "upcoming_count": len(upcoming),
        "reports": reports,
        "critical": sum(1 for r in reports if r.severity == Severity.CRITICAL),
        "unacknowledged": sum(1 for r in reports if r.status == ReportStatus.OPEN),
        "history": history,
        "resources": resources,
        "kinds": MaintenanceKind.choices,
        "form": form or _default_form(request, resources),
        "preview": preview,
        "errors": errors or {},
        "error": error,
        "scope_label": scope_label(user),
        "now": now,
        "here": reverse("manage:maintenance"),
    }
    return render(request, "manage/maintenance.html", ctx)


@staff_required("manage_maintenance")
def index(request):
    return _render(request)


def _parse_dt(d, t):
    try:
        return aware(date.fromisoformat(d), datetime.strptime(t, "%H:%M").time())
    except (TypeError, ValueError):
        return None


@staff_required("manage_maintenance")
@require_POST
def schedule(request):
    user, now = request.user, timezone.now()
    p = request.POST
    form = {k: p.get(k, "").strip() for k in ("resource", "start_date", "start_time", "end_date", "end_time",
                                               "kind", "title", "vendor", "notes")}
    errors = {}
    resource = None
    if form["resource"].isdigit():
        resource = managed_resources(user).select_related("type").filter(pk=form["resource"]).first()
    if resource is None:
        errors["resource"] = "Pick one of the resources you look after."
    start = _parse_dt(form["start_date"], form["start_time"])
    end = _parse_dt(form["end_date"], form["end_time"])
    if start is None:
        errors["start"] = "Give a start day and time."
    if end is None:
        errors["end"] = "Give an end day and time."
    if start and end and end <= start:
        errors["end"] = "The window has to end after it starts."
    if start and start < now - timedelta(minutes=15):
        errors["start"] = "That start time has already passed. Start from now or later."
    if not form["title"]:
        errors["title"] = "Say what the work is, e.g. “Projector lamp replacement”."
    if form["kind"] not in MaintenanceKind.values:
        form["kind"] = MaintenanceKind.PREVENTIVE
    if errors:
        return _render(request, form=form, errors=errors)

    signature = f"{resource.pk}|{start.isoformat()}|{end.isoformat()}"
    impact = services.impact(resource, start, end)
    preview = {**impact, "resource": resource, "start": start, "end": end, "signature": signature}
    if p.get("step") != "confirm":
        return _render(request, form=form, preview=preview)
    if p.get("checked") != signature:
        preview["changed"] = True
        return _render(request, form=form, preview=preview)
    try:
        window = services.schedule(
            resource, start, end, title=form["title"], kind=form["kind"], actor=user,
            notes=form["notes"], vendor=form["vendor"][:120], request=request,
        )
    except DomainError as exc:
        preview = {**services.impact(resource, start, end), "resource": resource, "start": start, "end": end,
                   "signature": signature}
        return _render(request, form=form, preview=preview, error=exc.message)
    s, e = timezone.localtime(window.start), timezone.localtime(window.end)
    msg = f"Scheduled. {resource.name} is closed {s:%a %d %b %H:%M} to {e:%a %d %b %H:%M}."
    if window.displaced_bookings:
        n = window.displaced_bookings
        msg += f" {n} booking{'s were' if n != 1 else ' was'} cancelled and the people told why."
    messages.success(request, msg)
    return redirect(reverse("manage:maintenance") + f"#day-{s:%Y%m%d}")


@staff_required("manage_maintenance")
@require_POST
def window_action(request, pk, action):
    if action not in ("cancel", "complete"):
        raise Http404
    try:
        w = _windows(request.user).select_related("resource").get(pk=pk)
    except MaintenanceWindow.DoesNotExist:
        raise Http404 from None
    back = safe_next(request, reverse("manage:maintenance"))
    try:
        if action == "cancel":
            services.cancel(w, request.user, request=request)
            msg = f"Cancelled. {w.resource.name} is bookable again for that time. Bookings it displaced stay cancelled."
        else:
            services.complete(w, request.user, request=request)
            msg = f"Marked complete. {w.resource.name} is back in service and any unused time is bookable again."
    except DomainError as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, msg)
    return redirect(back)


@staff_required("manage_maintenance")
@require_POST
def report_action(request, pk, action):
    if action not in ("acknowledge", "resolve"):
        raise Http404
    try:
        report = _reports(request.user).select_related("resource", "window").get(pk=pk)
    except BreakdownReport.DoesNotExist:
        raise Http404 from None
    back = safe_next(request, reverse("manage:maintenance"))
    if report.status == ReportStatus.RESOLVED:
        messages.info(request, "This report is already resolved.")
        return redirect(back)
    try:
        if action == "acknowledge":
            services.acknowledge(report, request.user)
            msg = "Acknowledged. The report stays open until you mark it resolved."
        else:
            resolution = request.POST.get("resolution", "").strip()
            if not resolution:
                messages.error(request, "Say what was done, so the next person knows. Then resolve it.")
                return redirect(back)
            services.resolve(report, request.user, resolution, request=request)
            report.resource.refresh_from_db(fields=["status"])
            msg = f"Resolved. {report.resource.name} is {'back in service' if report.resource.status == 'active' else 'still out of service: another critical report is open'}."
    except DomainError as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, msg)
    return redirect(back)
