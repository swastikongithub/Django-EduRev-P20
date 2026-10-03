"""Discovery (find) and the resource page (calendar + booking)."""

from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import can_manage_resource, has_cap
from apps.bookings import availability
from apps.core.http import date_param, int_param, is_digits
from apps.core.timeutil import aware, ceil_to

from . import search
from .manage_forms import can_create_resources
from .models import Building, Feature, Resource, ResourceType, SavedResource


def _parse_date(value, default=None):
    return date_param(value, default)


def _parse_time(value):
    try:
        return datetime.strptime(value, "%H:%M").time() if value else None
    except ValueError:
        return None


def _type_q(codes):
    q = Q()
    for c in codes:
        q |= Q(code=c) | Q(category=c) | Q(name__icontains=c.replace("-", " ")) | Q(code__startswith=c.split("-")[0])
    return q


@login_required
def find(request):
    user = request.user
    g = request.GET
    today = timezone.localdate()
    now = timezone.now()
    features_all = list(Feature.objects.filter(institution_id=user.institution_id).order_by("name"))
    intent = search.parse(g.get("q", ""), today=today, feature_names=[f.name for f in features_all])

    # Explicit controls win over what the free-text query implied.
    type_codes = g.getlist("type") or intent.type_codes
    building_code = g.get("building") or intent.building
    people = int_param(g.get("people") or intent.capacity or 0, 0, lo=0, hi=100_000)
    day = _parse_date(g.get("date"), intent.day)
    t_from = _parse_time(g.get("from")) or intent.start
    t_to = _parse_time(g.get("to")) or intent.end
    feature_ids = [int(x) for x in g.getlist("feature") if is_digits(x)] or [
        f.pk for f in features_all if f.name in intent.feature_words
    ]
    free_now = g.get("now") == "1" or intent.free_now
    if free_now:
        start = ceil_to(now, 30) if timezone.localtime(now).minute % 30 else now.replace(second=0, microsecond=0)
        day, t_from = timezone.localtime(start).date(), timezone.localtime(start).time()
        t_to = (timezone.localtime(start) + timedelta(hours=1)).time()
    if t_from and not t_to:
        t_to = (datetime.combine(today, t_from) + timedelta(hours=1)).time()
    if t_from and not day:
        day = today

    qs = (
        Resource.objects.filter(institution_id=user.institution_id)
        .exclude(status="retired")
        .select_related("type", "building")
        .prefetch_related("features")
    )
    types = (
        ResourceType.objects.filter(institution_id=user.institution_id).annotate(n=Count("resources")).filter(n__gt=0)
    )
    selected_types = []
    if type_codes:
        matching = types.filter(_type_q(type_codes))
        selected_types = [t.code for t in matching]
        qs = qs.filter(type__in=matching)
    if building_code:
        qs = qs.filter(Q(building__code=building_code) | Q(building__name__iexact=f"block {building_code}"))
    if people:
        qs = qs.filter(capacity__gte=people)
    for fid in feature_ids:
        qs = qs.filter(features__id=fid)
    qs, ranked = search.apply_text(qs, intent.text if not g.get("text_off") else "")
    if not ranked:
        qs = qs.order_by("type__sort_order", "building__code", "capacity" if people else "code")

    window = None
    unavailable_reasons = {}
    if day and t_from and t_to and t_to > t_from:
        start, end = aware(day, t_from), aware(day, t_to)
        window = (start, end)
        ids = list(qs.values_list("pk", flat=True))
        busy = availability.busy_resource_ids(ids, start, end)
        from apps.rules.services import blackouts_for, opening_intervals

        keep = []
        for r in qs.filter(pk__in=ids).exclude(pk__in=busy):
            if r.status != "active":
                continue
            if not any(o <= start and end <= c for o, c in opening_intervals(r, day)):
                continue
            if any(user.role not in (b.exempt_roles or []) for b in blackouts_for(r, start, end)):
                continue
            keep.append(r.pk)
        unavailable_reasons = {"busy": len(busy)}
        qs = qs.filter(pk__in=keep)

    total = qs.count()
    page = Paginator(qs.distinct(), 18).get_page(g.get("page"))
    show_day = day or today
    rows = availability.board(list(page.object_list), show_day, user, now=now)
    saved = set(SavedResource.objects.filter(user=user).values_list("resource_id", flat=True))

    # Chips describing what we understood from the free text (each removable).
    ctx = {
        "rows": rows,
        "page": page,
        "total": total,
        "intent": intent,
        "types": types,
        "selected_types": selected_types,
        "buildings": Building.objects.filter(institution_id=user.institution_id)
        .annotate(n=Count("resources"))
        .filter(n__gt=0),
        "building_code": building_code or "",
        "features": features_all,
        "feature_ids": feature_ids,
        "people": people or "",
        "day": day,
        "show_day": show_day,
        "t_from": t_from.strftime("%H:%M") if t_from else "",
        "t_to": t_to.strftime("%H:%M") if t_to else "",
        "window": window,
        "free_now": free_now,
        "saved": saved,
        "times": _time_options(),
        "q": g.get("q", ""),
        "today": today,
        "unavailable_reasons": unavailable_reasons,
        "can_book_role": lambda r: r.type.role_may_book(user.role),
        # An empty catalogue is not "nothing matched": say so, and who can fill it.
        "catalogue_empty": not total
        and not Resource.objects.filter(institution_id=user.institution_id).exclude(status="retired").exists(),
        "can_add_resources": can_create_resources(user),
    }
    template = "catalogue/_results.html" if request.headers.get("HX-Request") else "catalogue/find.html"
    return render(request, template, ctx)


def _time_options():
    out, t = [], datetime(2000, 1, 1, 6, 0)
    while t.hour < 23:
        out.append(t.strftime("%H:%M"))
        t += timedelta(minutes=30)
    return out


@login_required
def detail(request, slug):
    user = request.user
    resource = get_object_or_404(
        Resource.objects.select_related("type", "building", "department").prefetch_related(
            "features", "attributes", "custodians__user"
        ),
        institution_id=user.institution_id,
        slug=slug,
    )
    now = timezone.now()
    today = timezone.localdate()
    day = _parse_date(request.GET.get("date"), today)
    view = request.GET.get("view", "week")
    week_start = day - timedelta(days=day.weekday())
    days = [week_start + timedelta(days=i) for i in range(7)] if view == "week" else [day]
    window = (time(7, 0), time(22, 0))
    schedules = availability.schedule(resource, days, user, now=now, window=window)
    columns = [(s, calendar_runs(s, window[0])) for s in schedules]

    from apps.rules.services import policy_for, weekly_hours

    policy = policy_for(resource)
    hours = weekly_hours(resource)
    from apps.inventory.services import items_for
    from apps.maintenance.models import MaintenanceWindow, WindowStatus

    upcoming_maintenance = MaintenanceWindow.objects.filter(
        resource=resource, status__in=[WindowStatus.SCHEDULED, WindowStatus.IN_PROGRESS], period__endswith__gt=now
    ).order_by("period")[:3]
    ctx = {
        "r": resource,
        "day": day,
        "days": days,
        "view": view,
        "schedules": schedules,
        "columns": columns,
        "rows_total": (window[1].hour - window[0].hour) * 2,
        "workflow": _workflow_preview(resource, user),
        "today_schedule": availability.day(resource, today, user, now=now),
        "prev_week": week_start - timedelta(days=7),
        "next_week": week_start + timedelta(days=7),
        "prev_day": day - timedelta(days=1),
        "next_day": day + timedelta(days=1),
        "hours_rows": [(h, f"{h:02d}:00") for h in range(window[0].hour, window[1].hour)],
        "policy": policy,
        "hours": [
            (wd, name, hours.get(wd, [])) for wd, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        ],
        "weekday_names": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "legend": availability.LEGEND,
        "items": items_for(resource),
        "is_manager": can_manage_resource(user, resource),
        "can_book": resource.type.role_may_book(user.role) or has_cap(user, "manage_resources"),
        "can_on_behalf": has_cap(user, "book_on_behalf"),
        "can_recurring": has_cap(user, "book_recurring"),
        "saved": SavedResource.objects.filter(user=user, resource=resource).exists(),
        "maintenance": upcoming_maintenance,
        "today": today,
        "now": now,
        "slot_minutes": policy.slot_minutes,
    }
    template = "catalogue/_calendar.html" if request.headers.get("HX-Request") else "catalogue/detail.html"
    return render(request, template, ctx)


@login_required
@require_POST
def toggle_save(request, slug):
    resource = get_object_or_404(Resource, institution_id=request.user.institution_id, slug=slug)
    obj, created = SavedResource.objects.get_or_create(user=request.user, resource=resource)
    if not created:
        obj.delete()
    if request.headers.get("HX-Request"):
        return render(request, "catalogue/_save_button.html", {"r": resource, "saved": created})
    return redirect(resource.get_absolute_url())


def resource_or_404(user, slug):
    try:
        return Resource.objects.get(institution_id=user.institution_id, slug=slug)
    except Resource.DoesNotExist:
        raise Http404 from None


ROW_MINUTES = 30


def calendar_runs(sched, window_start: time):
    """
    Collapse a day's cells into grid runs. Free cells stay individual (each one is a
    selectable target); anything else merges with its neighbours when state and reason
    match, so a 2-hour class renders as one labelled block rather than four grey cells.
    """
    runs = []
    origin = aware(sched.day, window_start)
    for c in sched.cells:
        row = int((c.start - origin).total_seconds() // (ROW_MINUTES * 60)) + 1
        span = max(1, int((c.end - c.start).total_seconds() // (ROW_MINUTES * 60)))
        prev = runs[-1] if runs else None
        if (
            prev
            and c.state != "free"
            and prev["state"] == c.state
            and prev["reason"] == c.reason
            and prev["end"] == c.start
        ):
            prev["span"] += span
            prev["end"] = c.end
            continue
        runs.append(
            {
                "row": row,
                "span": span,
                "state": c.state,
                "reason": c.reason,
                "start": c.start,
                "end": c.end,
                "selectable": c.selectable,
            }
        )
    return runs


def _workflow_preview(resource, user):
    from apps.approvals.services import resolve_workflow

    wf = resolve_workflow(resource, user, 1, 60)
    if wf is None or wf.auto_approve:
        return {"instant": True, "name": wf.name if wf else ""}
    return {"instant": False, "name": wf.name, "steps": [s.get_approver_role_display() for s in wf.steps.all()]}
