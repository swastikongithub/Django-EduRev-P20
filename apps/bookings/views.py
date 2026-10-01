"""
Booking pages. Views parse the request, call apps.bookings.services and render;
every rule lives in the service layer (and, for overlaps, in PostgreSQL).
"""

from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import can_manage_resource, has_cap
from apps.catalogue.models import Resource
from apps.core.errors import DomainError
from apps.core.http import MAX_PK, date_param, int_param
from apps.core.timeutil import aware, trange

from . import services
from .models import HOLDING_STATUSES, Booking, BookingSeries, BookingStatus


def _date(v, default=None):
    return date_param(v, default)


def _time(v):
    try:
        return datetime.strptime(v, "%H:%M").time()
    except (TypeError, ValueError):
        return None


def _int(v, default=1):
    return int_param(v, default, lo=1, hi=100_000)


def _hx_redirect(url):
    resp = HttpResponse(status=204)
    resp["HX-Redirect"] = url
    return resp


@login_required
@require_POST
def create(request, slug):
    resource = get_object_or_404(
        Resource.objects.select_related("type"), institution_id=request.user.institution_id, slug=slug
    )
    p = request.POST
    d, t1, t2 = _date(p.get("date")), _time(p.get("start")), _time(p.get("end"))
    error, code = None, None
    if not (d and t1 and t2):
        error = "Pick a day, a start and an end time."
    else:
        items = {}
        for k, v in p.items():
            if k.startswith("item-") and k[5:].isdigit():
                try:
                    qty = int(v or 0)
                except ValueError:
                    qty = 0
                if qty > 0:  # the form sends every item with 0 by default; only positive quantities are requests
                    items[int(k[5:])] = qty
        try:
            booking = services.create_booking(
                requester=request.user,
                resource=resource,
                start=aware(d, t1),
                end=aware(d, t2),
                title=p.get("title", ""),
                attendees=_int(p.get("attendees")),
                group_label=p.get("group_label", "") if has_cap(request.user, "book_on_behalf") else "",
                notes=p.get("notes", "")[:2000],
                items=items or None,
                request=request,
            )
        except DomainError as exc:
            error = exc.message
            code = exc.code
        else:
            url = booking.get_absolute_url() + "?new=1"
            return _hx_redirect(url) if request.headers.get("HX-Request") else redirect(url)
    if request.headers.get("HX-Request"):
        from apps.catalogue.views import _workflow_preview
        from apps.inventory.services import items_for
        from apps.rules.services import policy_for

        alts = []
        if d and t1 and t2 and code in ("conflict", "timetable", "maintenance"):
            alts = services.suggest_alternatives(
                resource, aware(d, t1), aware(d, t2), attendees=_int(p.get("attendees"))
            )
        return render(
            request,
            "bookings/_book_panel.html",
            {
                "r": resource,
                "error": error,
                "alternatives": alts,
                "form": p,
                "policy": policy_for(resource),
                "workflow": _workflow_preview(resource, request.user),
                "items": items_for(resource),
                "can_book": True,
                "can_on_behalf": has_cap(request.user, "book_on_behalf"),
                "can_recurring": has_cap(request.user, "book_recurring"),
                "day": d or timezone.localdate(),
            },
        )
    messages.error(request, error)
    return redirect(resource.get_absolute_url() + (f"?date={d.isoformat()}" if d else ""))


def _visible_or_404(user, reference):
    try:
        return (
            services.visible_bookings(user)
            .select_related("resource__type", "resource__building", "booked_for", "requester", "series")
            .get(reference=reference)
        )
    except Booking.DoesNotExist:
        raise Http404 from None


@login_required
def detail(request, reference):
    from apps.checkins.qr import pass_url, svg
    from apps.checkins.services import checkin_state

    b = _visible_or_404(request.user, reference)
    is_owner = request.user.pk in (b.booked_for_id, b.requester_id)
    now = timezone.now()
    state = checkin_state(b, now)
    steps = list(b.approvals.select_related("decided_by").order_by("step_order"))
    timeline = _timeline(b, steps)
    ctx = {
        "b": b,
        "is_owner": is_owner,
        "is_manager": can_manage_resource(request.user, b.resource),
        "state": state,
        "qr": svg(pass_url(b)) if b.is_holding else None,
        "approvals": [s for s in steps if s.step_order > 0],
        "auto_note": next((s.comment for s in steps if s.step_order == 0), ""),
        "timeline": timeline,
        "can_cancel": services.can_cancel(request.user, b),
        "issuances": b.issuances.select_related("item"),
        "is_new": request.GET.get("new") == "1",
        "checkin": getattr(b, "checkin", None),
        "series_count": b.series.bookings.filter(status__in=HOLDING_STATUSES).count() if b.series_id else 0,
        "now": now,
    }
    return render(request, "bookings/pass.html", ctx)


def _timeline(b, steps):
    """The four milestones of a booking, each done / current / upcoming / failed."""
    s = b.status
    needs_approval = any(x.step_order > 0 for x in steps)
    out = [{"label": "Requested", "at": b.created_at, "state": "done"}]
    if needs_approval:
        if s == BookingStatus.PENDING:
            out.append({"label": "Approval", "state": "current", "note": "Waiting for a decision"})
        elif s == BookingStatus.REJECTED:
            out.append({"label": "Not approved", "at": b.decided_at, "state": "failed"})
        elif s == BookingStatus.EXPIRED:
            out.append({"label": "Expired", "at": b.updated_at, "state": "failed"})
        else:
            out.append({"label": "Approved", "at": b.decided_at, "state": "done"})
    else:
        out.append(
            {"label": "Confirmed", "at": b.created_at, "state": "done" if s != BookingStatus.PENDING else "current"}
        )
    if s == BookingStatus.NO_SHOW:
        out.append({"label": "Released, no check-in", "at": b.updated_at, "state": "failed"})
    elif s == BookingStatus.CANCELLED:
        out.append({"label": "Cancelled", "at": b.cancelled_at, "state": "failed"})
    elif b.requires_checkin:
        if b.checked_in_at:
            out.append({"label": "Checked in", "at": b.checked_in_at, "state": "done"})
        else:
            out.append({"label": "Check in", "state": "current" if s == BookingStatus.APPROVED else "upcoming"})
    if s == BookingStatus.COMPLETED:
        out.append({"label": "Done", "at": b.checked_out_at or b.end, "state": "done"})
    elif s in (BookingStatus.APPROVED, BookingStatus.CHECKED_IN, BookingStatus.PENDING):
        out.append({"label": "Done", "state": "upcoming"})
    return out


@login_required
@require_POST
def cancel(request, reference):
    b = _visible_or_404(request.user, reference)
    try:
        services.cancel_booking(b, request.user, reason=request.POST.get("reason", "").strip()[:200], request=request)
        messages.success(request, f"Cancelled. {b.resource.name} is free again for everyone else.")
    except DomainError as exc:
        messages.error(request, exc.message)
    return redirect(b.get_absolute_url())


@login_required
def mine(request):
    user = request.user
    now = timezone.now()
    tab = request.GET.get("tab", "upcoming")
    qs = (
        Booking.objects.filter(Q(booked_for=user) | Q(requester=user))
        .select_related("resource__type", "resource__building")
        .distinct()
    )
    counts = {
        "upcoming": qs.filter(
            status__in=[BookingStatus.APPROVED, BookingStatus.CHECKED_IN], period__endswith__gt=now
        ).count(),
        "pending": qs.filter(status=BookingStatus.PENDING).count(),
    }
    if tab == "pending":
        qs = qs.filter(status=BookingStatus.PENDING).order_by("period")
    elif tab == "past":
        qs = qs.filter(Q(period__endswith__lte=now) | ~Q(status__in=HOLDING_STATUSES)).order_by("-period")
    else:
        tab = "upcoming"
        qs = qs.filter(
            status__in=[BookingStatus.APPROVED, BookingStatus.CHECKED_IN], period__endswith__gt=now
        ).order_by("period")
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    groups = []
    for b in page.object_list:
        day = timezone.localtime(b.start).date()
        if not groups or groups[-1][0] != day:
            groups.append((day, []))
        groups[-1][1].append(b)
    series = BookingSeries.objects.filter(requester=user, until_date__gte=timezone.localdate()).select_related(
        "resource"
    )[:5]
    return render(
        request, "bookings/mine.html", {"tab": tab, "page": page, "groups": groups, "counts": counts, "series": series}
    )


@login_required
def calendar(request):
    """The person's own week: bookings as blocks on a Mon–Sun timeline."""
    user = request.user
    today = timezone.localdate()
    d = _date(request.GET.get("date"), today)
    week_start = d - timedelta(days=d.weekday())
    days = [week_start + timedelta(days=i) for i in range(7)]
    start, end = aware(days[0], time.min), aware(days[-1] + timedelta(days=1), time.min)
    bookings = (
        Booking.objects.filter(Q(booked_for=user) | Q(requester=user), period__overlap=trange(start, end))
        .exclude(status__in=[BookingStatus.CANCELLED, BookingStatus.REJECTED, BookingStatus.EXPIRED])
        .select_related("resource")
        .distinct()
    )
    first_hour, last_hour = 7, 22
    by_day = {x: [] for x in days}
    for b in bookings:
        s, e = timezone.localtime(b.start), timezone.localtime(b.end)
        top = max(0, (s.hour - first_hour) * 60 + s.minute)
        height = max(20, int((e - s).total_seconds() // 60))
        by_day.setdefault(s.date(), []).append({"b": b, "top": top, "height": height})
    return render(
        request,
        "bookings/calendar.html",
        {
            "days": [(x, by_day.get(x, [])) for x in days],
            "hours": [f"{h:02d}:00" for h in range(first_hour, last_hour)],
            "total_minutes": (last_hour - first_hour) * 60,
            "prev": week_start - timedelta(days=7),
            "next": week_start + timedelta(days=7),
            "week_start": week_start,
            "today": today,
            "now_minutes": (timezone.localtime().hour - first_hour) * 60 + timezone.localtime().minute,
            "feed_url": request.build_absolute_uri(f"/feed/{user.calendar_token}.ics"),
        },
    )


def _ics(bookings, name="LPU Reserve"):
    from ics import Calendar, Event

    cal = Calendar(creator="-//LPU Reserve//EN")
    for b in bookings:
        ev = Event(name=f"{b.resource.name}: {b.title}", begin=b.start, end=b.end, uid=f"{b.reference}@lpu-reserve")
        ev.location = b.resource.location_label
        ev.description = f"Booking {b.reference} ({b.get_status_display()})"
        cal.events.add(ev)
    return cal.serialize()


@login_required
def ics(request, reference):
    b = _visible_or_404(request.user, reference)
    resp = HttpResponse(_ics([b]), content_type="text/calendar; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{b.reference}.ics"'
    return resp


def feed(request, token):
    """Personal subscription feed (Google / Outlook / Apple). The unguessable token is the credential."""
    from apps.accounts.models import User

    user = User.objects.filter(calendar_token=token, is_active=True).first()
    if not user:
        raise Http404
    since = timezone.now() - timedelta(days=30)
    bookings = Booking.objects.filter(
        booked_for=user, status__in=[*HOLDING_STATUSES, BookingStatus.COMPLETED], period__endswith__gte=since
    ).select_related("resource__building")
    return HttpResponse(_ics(bookings), content_type="text/calendar; charset=utf-8")


@login_required
def series_new(request):
    """Faculty/staff: book the same slot every week, previewing each date before committing."""
    if not has_cap(request.user, "book_recurring"):
        raise Http404
    g = request.POST if request.method == "POST" else request.GET
    resource = (
        Resource.objects.filter(institution_id=request.user.institution_id, slug=g.get("resource"))
        .select_related("type")
        .first()
    )
    resources = (
        Resource.objects.filter(institution_id=request.user.institution_id, status="active", is_bookable=True)
        .select_related("type", "building")
        .order_by("type__sort_order", "code")
    )
    today = timezone.localdate()
    start_date = _date(g.get("start_date"), _date(g.get("date"), today + timedelta(days=1)))
    until_date = _date(g.get("until_date"), start_date + timedelta(weeks=6))
    t1, t2 = _time(g.get("start") or g.get("from")) or time(10), _time(g.get("end") or g.get("to")) or time(11)
    weekdays = [int(x) for x in g.getlist("weekday") if x.isdigit() and 0 <= int(x) <= 6] or [start_date.weekday()]
    ctx = {
        "resource": resource,
        "resources": resources,
        "start_date": start_date,
        "until_date": until_date,
        "t1": t1.strftime("%H:%M"),
        "t2": t2.strftime("%H:%M"),
        "weekdays": weekdays,
        "title": g.get("title", ""),
        "group_label": g.get("group_label", ""),
        "attendees": g.get("attendees", ""),
        "weekday_names": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "plans": None,
        "error": None,
        "times": [f"{h:02d}:{m:02d}" for h in range(6, 23) for m in (0, 30)],
    }
    if resource and g.get("action") in ("preview", "create"):
        occ = services.expand_occurrences(
            frequency="weekly",
            interval=1,
            weekdays=weekdays,
            start_date=start_date,
            until_date=until_date,
            start_time=t1,
            end_time=t2,
        )
        if g.get("action") == "create" and request.method == "POST":
            try:
                series, created, skipped = services.create_series(
                    requester=request.user,
                    resource=resource,
                    title=g.get("title") or "Weekly session",
                    frequency="weekly",
                    interval=1,
                    weekdays=weekdays,
                    start_date=start_date,
                    until_date=until_date,
                    start_time=t1,
                    end_time=t2,
                    attendees=_int(g.get("attendees")),
                    group_label=g.get("group_label", ""),
                    request=request,
                )
            except DomainError as exc:
                ctx["error"] = exc.message
            else:
                msg = f"{len(created)} sessions booked"
                if skipped:
                    msg += f"; {len(skipped)} skipped — see the list below"
                messages.success(request, msg + ".")
                return redirect(f"{request.path}?series={series.pk}")
        ctx["plans"] = services.preview_series(
            requester=request.user, resource=resource, occurrences=occ, attendees=_int(g.get("attendees"))
        )
        ctx["ok_count"] = sum(1 for p in ctx["plans"] if p.ok)
    if series_pk := int_param(g.get("series"), lo=0, hi=MAX_PK):
        ctx["done"] = (
            BookingSeries.objects.filter(pk=series_pk, requester=request.user).select_related("resource").first()
        )
        if ctx["done"]:
            ctx["done_bookings"] = ctx["done"].bookings.order_by("period")
    return render(request, "bookings/series.html", ctx)
