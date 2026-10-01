"""
Operations health for the staff console: readiness checks, Celery mode, and the background
sweeps (last run, how much they changed, whether one has stalled), with a "Run now" button.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.permissions import is_campus_wide
from apps.audit.services import record

from .health import check_database, check_redis
from .manage_views import staff_required
from .models import SweepRun

DAY = 86400.0


@dataclass(frozen=True)
class Sweep:
    task: str  # Celery task name == SweepRun.task
    module: str
    func: str
    label: str
    what: str
    result: str  # sentence template for the Run-now toast; {n} is the count


SWEEPS = [
    Sweep(
        "checkins.sweep_no_shows",
        "apps.checkins.tasks",
        "sweep_no_shows",
        "Release no-shows",
        "Frees confirmed bookings nobody checked into within the grace period, and applies the no-show ladder.",
        "Released {n} booking{s} that nobody checked into.",
    ),
    Sweep(
        "checkins.sweep_completed",
        "apps.checkins.tasks",
        "sweep_completed",
        "Complete finished bookings",
        "Checks out bookings whose time is over, so the history and utilisation stay accurate.",
        "Marked {n} finished booking{s} as completed.",
    ),
    Sweep(
        "approvals.sweep_expired",
        "apps.approvals.tasks",
        "sweep_expired",
        "Expire stale requests",
        "Releases pending requests that reached their start time without a decision.",
        "Expired {n} request{s} that weren't decided in time.",
    ),
    Sweep(
        "notifications.send_reminders",
        "apps.notifications.tasks",
        "send_reminders",
        "Send reminders",
        "Reminds people 30 minutes before a confirmed booking starts.",
        "Sent {n} reminder{s}.",
    ),
    Sweep(
        "notifications.send_checkin_nudges",
        "apps.notifications.tasks",
        "send_checkin_nudges",
        "Check-in nudges",
        "Tells people their check-in window is open once a booking starts.",
        "Sent {n} check-in nudge{s}.",
    ),
    Sweep(
        "maintenance.sweep_windows",
        "apps.maintenance.tasks",
        "sweep_windows",
        "Maintenance transitions",
        "Starts and finishes scheduled maintenance windows on time.",
        "Moved {n} maintenance window{s} along.",
    ),
    Sweep(
        "checkins.sweep_restrictions",
        "apps.checkins.tasks",
        "sweep_restrictions",
        "Lapsed restrictions",
        "Reports booking pauses that ended in the last hour.",
        "{n} booking pause{s} ended in the last hour.",
    ),
    Sweep(
        "analytics.build_snapshots",
        "apps.analytics.tasks",
        "build_snapshots",
        "Utilisation snapshot",
        "Rolls up yesterday's bookings into the utilisation figures on Insights.",
        "Rebuilt yesterday's utilisation ({n} row{s}).",
    ),
]
SWEEP_BY_TASK = {s.task: s for s in SWEEPS}


def _interval_seconds(schedule) -> float:
    if isinstance(schedule, (int, float)):
        return float(schedule)
    if isinstance(schedule, timedelta):
        return schedule.total_seconds()
    return DAY  # crontab entries in this project run daily


def schedule_intervals() -> dict[str, float]:
    return {e["task"]: _interval_seconds(e["schedule"]) for e in settings.CELERY_BEAT_SCHEDULE.values()}


def _every(seconds: float) -> str:
    if seconds >= DAY:
        return "daily"
    if seconds >= 3600:
        h = seconds / 3600
        return "hourly" if h == 1 else f"every {h:g} hours"
    m = seconds / 60
    return "every minute" if m == 1 else f"every {m:g} minutes"


def sweep_status(now=None) -> list[dict]:
    """One row per scheduled sweep with its latest run and a stalled flag (> 3x its interval)."""
    now = now or timezone.now()
    intervals = schedule_intervals()
    latest = {r.task: r for r in SweepRun.objects.order_by("task", "-started_at").distinct("task")}
    day_ago = now - timedelta(days=1)
    stats = {
        row["task"]: row
        for row in SweepRun.objects.filter(started_at__gte=day_ago)
        .values("task")
        .annotate(runs=Count("id"), failed=Count("id", filter=Q(ok=False)), affected=Sum("affected"))
    }
    rows = []
    for s in SWEEPS:
        interval = intervals.get(s.task)
        last = latest.get(s.task)
        age = (now - last.started_at).total_seconds() if last else None
        stalled = bool(interval) and (age is None or age > 3 * interval)
        rows.append(
            {
                "sweep": s,
                "interval": interval,
                "every": _every(interval) if interval else "not scheduled",
                "last": last,
                "age": age,
                "stalled": stalled,
                "failed": bool(last and not last.ok),
                "day": stats.get(s.task, {"runs": 0, "failed": 0, "affected": 0}),
            }
        )
    return rows


def celery_mode() -> dict:
    eager = bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False))
    broker = getattr(settings, "CELERY_BROKER_URL", "") or ""
    parts = urlsplit(broker)
    shown = (
        f"{parts.scheme}://{parts.hostname or ''}{':' + str(parts.port) if parts.port else ''}" if parts.scheme else ""
    )
    if eager:
        return {
            "label": "Eager",
            "tone": "warn",
            "broker": shown,
            "text": "Tasks run inline inside the web request. Fine for demos and tests; the beat schedule doesn't run, "
            "so use Run now below.",
        }
    if parts.scheme == "memory":
        return {
            "label": "In-memory broker",
            "tone": "warn",
            "broker": shown,
            "text": "No Redis broker is configured, so no worker or beat process can pick up work. Use Run now, "
            "or set REDIS_URL.",
        }
    return {
        "label": "Broker",
        "tone": "ok",
        "broker": shown,
        "text": "Tasks go through the broker to Celery workers; Celery Beat runs the sweeps on schedule.",
    }


def run_now(task_name: str) -> int:
    """Run one sweep synchronously in this process (recorded in SweepRun by the task itself)."""
    s = SWEEP_BY_TASK[task_name]
    task = getattr(importlib.import_module(s.module), s.func)
    result = task.apply(throw=True).result
    return len(result) if isinstance(result, (list, tuple, set)) else int(result or 0)


@staff_required()
@require_http_methods(["GET", "POST"])
def ops(request):
    if not is_campus_wide(request.user):
        raise PermissionDenied
    if request.method == "POST":
        name = request.POST.get("task", "")
        if name not in SWEEP_BY_TASK:
            return HttpResponseBadRequest("Unknown task")
        s = SWEEP_BY_TASK[name]
        try:
            n = run_now(name)
        except Exception as exc:  # noqa: BLE001 - shown to the operator, details are in the SweepRun row
            messages.error(request, f"{s.label} failed: {type(exc).__name__}. The error is recorded below.")
            record(
                request.user,
                "ops.run_sweep",
                request.user,
                after={"task": name, "ok": False},
                request=request,
                label=s.label,
            )
        else:
            messages.success(request, s.result.format(n=n, s="" if n == 1 else "s"))
            record(
                request.user,
                "ops.run_sweep",
                request.user,
                after={"task": name, "ok": True, "affected": n},
                request=request,
                label=s.label,
            )
        return redirect("manage:ops")

    checks = {"database": check_database()}
    redis_url = getattr(settings, "REDIS_URL", "")
    checks["redis"] = check_redis(redis_url) if redis_url else {"status": "off"}
    rows = sweep_status()
    recent = list(SweepRun.objects.all()[:25])
    for run in recent:
        run.took = (run.finished_at - run.started_at).total_seconds() if run.finished_at else None
    return render(
        request,
        "manage/ops.html",
        {
            "checks": checks,
            "celery": celery_mode(),
            "rows": rows,
            "stalled": [r for r in rows if r["stalled"]],
            "recent": recent,
            "labels": {s.task: s.label for s in SWEEPS},
            "demo": settings.DEMO_MODE,
        },
    )
