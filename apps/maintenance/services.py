"""
M7 service interface.

    schedule(resource, start, end, ...)   claim the time on the BookingSlot ledger, displacing bookings
    reschedule / cancel / complete        window lifecycle; completion hands unused time back
    report_breakdown(resource, user, ...) anyone can report; critical reports take the resource offline
    acknowledge / resolve                 custodian handling of reports
    sweep_windows(now)                    scheduled -> in progress -> completed
"""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import can_manage_resource, has_cap
from apps.bookings.models import SlotKind
from apps.core.errors import BookingRejected, InvalidTransition, NotPermitted
from apps.core.timeutil import trange

from .models import BreakdownReport, MaintenanceWindow, ReportStatus, Severity, WindowStatus

SOURCE = "maintenance_window"


def _require_manager(actor, resource):
    if not has_cap(actor, "manage_maintenance") or not can_manage_resource(actor, resource):
        raise NotPermitted("You don't manage maintenance for this resource.")


def _notify_custodians(resource, kind, title, body, url="/manage/maintenance/"):
    from apps.notifications.services import notify_many

    notify_many([c.user for c in resource.custodians.select_related("user")], kind, title, body, url, email=False)


def schedule(
    resource,
    start,
    end,
    *,
    title,
    kind="preventive",
    actor,
    notes="",
    vendor="",
    request=None,
    enforce_permissions=True,
) -> MaintenanceWindow:
    from apps.bookings.services import claim_block

    if enforce_permissions:
        _require_manager(actor, resource)
    if end <= start:
        raise BookingRejected("Maintenance must end after it starts.", code="policy")
    with transaction.atomic():
        window = MaintenanceWindow.objects.create(
            institution_id=resource.institution_id,
            resource=resource,
            title=title,
            kind=kind,
            period=trange(start, end),
            notes=notes,
            vendor=vendor,
            created_by=actor,
        )
        _, displaced = claim_block(
            resource,
            start,
            end,
            kind=SlotKind.MAINTENANCE,
            source_type=SOURCE,
            source_id=window.pk,
            label=title,
            reason=f"{resource.name} is closed for maintenance ({title}).",
        )
        window.displaced_bookings = displaced
        window.save(update_fields=["displaced_bookings"])
        from apps.audit.services import record

        record(
            actor,
            "maintenance.schedule",
            window,
            after={"period": str(window.period), "displaced": displaced},
            request=request,
        )
        from apps.notifications.models import Kind

        _notify_custodians(
            resource,
            Kind.MAINTENANCE,
            f"Maintenance scheduled · {resource.name}",
            f"{title}: {timezone.localtime(start):%a %d %b %H:%M} – {timezone.localtime(end):%a %d %b %H:%M}."
            + (f" {displaced} booking(s) moved off." if displaced else ""),
        )
    return window


def cancel(window: MaintenanceWindow, actor, *, request=None):
    from apps.bookings.services import release_blocks

    _require_manager(actor, window.resource)
    if window.status in (WindowStatus.COMPLETED, WindowStatus.CANCELLED):
        raise InvalidTransition("This window is already closed.")
    with transaction.atomic():
        release_blocks(SOURCE, [window.pk])
        window.status = WindowStatus.CANCELLED
        window.save(update_fields=["status", "updated_at"])
        _reopen_if_needed(window.resource)
        from apps.audit.services import record

        record(actor, "maintenance.cancel", window, request=request)
    return window


def complete(window: MaintenanceWindow, actor, *, request=None, now=None):
    from apps.bookings.services import shrink_block

    now = now or timezone.now()
    if actor is not None:
        _require_manager(actor, window.resource)
    if window.status in (WindowStatus.COMPLETED, WindowStatus.CANCELLED):
        raise InvalidTransition("This window is already closed.")
    with transaction.atomic():
        if now < window.end:
            new_end = max(now, window.start + timedelta(minutes=1))
            window.period = trange(window.start, new_end)
            shrink_block(SOURCE, window.pk, new_end)
        window.status = WindowStatus.COMPLETED
        window.completed_at = now
        window.save(update_fields=["status", "completed_at", "period", "updated_at"])
        BreakdownReport.objects.filter(window=window).exclude(status=ReportStatus.RESOLVED).update(
            status=ReportStatus.RESOLVED, resolved_at=now, resolution="Fixed during maintenance"
        )
        _reopen_if_needed(window.resource)
        if actor is not None:
            from apps.audit.services import record

            record(actor, "maintenance.complete", window, request=request)
    return window


def _reopen_if_needed(resource):
    """Bring a resource back into service when no critical breakdown remains open."""
    open_critical = (
        resource.breakdowns.filter(severity=Severity.CRITICAL).exclude(status=ReportStatus.RESOLVED).exists()
    )
    if resource.status == "out_of_service" and not open_critical:
        resource.status = "active"
        resource.status_note = ""
        resource.save(update_fields=["status", "status_note", "updated_at"])


def report_breakdown(resource, user, *, summary, details="", severity=Severity.HIGH, request=None, now=None):
    from apps.notifications.models import Kind

    now = now or timezone.now()
    with transaction.atomic():
        report = BreakdownReport.objects.create(
            institution_id=resource.institution_id,
            resource=resource,
            reported_by=user,
            summary=summary[:160],
            details=details,
            severity=severity,
        )
        if severity == Severity.CRITICAL:
            resource.status = "out_of_service"
            resource.status_note = summary[:200]
            resource.save(update_fields=["status", "status_note", "updated_at"])
            # Block the next 24 hours so nobody walks into a broken room; the custodian
            # shortens or extends the window when the repair is planned.
            # If a timetabled class sits inside that window the claim is refused (classes are
            # never displaced automatically); the resource is still out of service, so no new
            # bookings are accepted, and the custodian relocates the class.
            try:
                with transaction.atomic():
                    window = schedule(
                        resource,
                        now.replace(second=0, microsecond=0),
                        now + timedelta(hours=24),
                        title=f"Breakdown: {summary[:80]}",
                        kind="repair",
                        actor=user,
                        notes=details,
                        request=request,
                        enforce_permissions=False,
                    )
                report.window = window
                report.save(update_fields=["window"])
            except BookingRejected:
                pass
        _notify_custodians(
            resource,
            Kind.BREAKDOWN,
            f"Breakdown reported · {resource.name}",
            f"{report.get_severity_display()}: {summary}",
            "/manage/maintenance/",
        )
        from apps.audit.services import record

        record(user, "maintenance.report", report, after={"severity": severity}, request=request)
    return report


def acknowledge(report: BreakdownReport, actor):
    _require_manager(actor, report.resource)
    report.status = ReportStatus.ACKNOWLEDGED
    report.save(update_fields=["status", "updated_at"])
    return report


def resolve(report: BreakdownReport, actor, resolution: str, *, request=None):
    _require_manager(actor, report.resource)
    with transaction.atomic():
        report.status = ReportStatus.RESOLVED
        report.resolved_at = timezone.now()
        report.resolution = resolution[:240]
        report.save(update_fields=["status", "resolved_at", "resolution", "updated_at"])
        if report.window_id and report.window.status in (WindowStatus.SCHEDULED, WindowStatus.IN_PROGRESS):
            complete(report.window, actor, request=request)
        _reopen_if_needed(report.resource)
    return report


def sweep_windows(now=None) -> int:
    now = now or timezone.now()
    started = MaintenanceWindow.objects.filter(status=WindowStatus.SCHEDULED, period__startswith__lte=now).update(
        status=WindowStatus.IN_PROGRESS
    )
    finished = 0
    for w in MaintenanceWindow.objects.filter(status=WindowStatus.IN_PROGRESS, period__endswith__lte=now):
        w.status = WindowStatus.COMPLETED
        w.completed_at = w.end
        w.save(update_fields=["status", "completed_at", "updated_at"])
        _reopen_if_needed(w.resource)
        finished += 1
    return started + finished
