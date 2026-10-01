"""
Approval queue (/manage/approvals/): the steps waiting for *this* person, soonest start first,
with enough context on each card (who, what, when, how full, that day's strip) to decide
in one click. Decisions go through approvals.services.decide — never around it.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import is_campus_wide
from apps.bookings.availability import board
from apps.core.errors import DomainError
from apps.core.http import safe_next
from apps.core.manage_views import staff_required

from . import services
from .models import Approval, Decision

QUEUE_LIMIT = 60
DAY_START, DAY_END = 7, 22


def _sla(approval, now):
    if not approval.due_at:
        return None
    mins = int((approval.due_at - now).total_seconds() // 60)
    return {"overdue": mins < 0, "minutes": abs(mins), "soon": 0 <= mins < 120}


def _mark(booking, day_start):
    """Where the requested span sits on the 07:00–22:00 strip, in percent."""
    total = (DAY_END - DAY_START) * 60
    lo = (timezone.localtime(booking.start) - day_start).total_seconds() / 60
    hi = (timezone.localtime(booking.end) - day_start).total_seconds() / 60
    lo, hi = max(0.0, min(total, lo)), max(0.0, min(total, hi))
    return {"left": lo / total * 100, "width": max(0.6, (hi - lo) / total * 100)}


def _decorate(approvals, user, now):
    """Bulk-load everything the cards show: step position, requester history, the day's strip."""
    from apps.checkins.models import NoShow, Restriction

    if not approvals:
        return []
    booking_ids = {a.booking_id for a in approvals}
    orders = defaultdict(list)
    for bid, order in (
        Approval.objects.filter(booking_id__in=booking_ids, step_order__gt=0)
        .order_by("step_order")
        .values_list("booking_id", "step_order")
    ):
        orders[bid].append(order)
    user_ids = {a.booking.booked_for_id for a in approvals}
    no_shows = Counter(
        dict(
            NoShow.objects.filter(user_id__in=user_ids, forgiven=False, detected_at__gte=now - timedelta(days=30))
            .values("user_id")
            .annotate(n=Count("id"))
            .values_list("user_id", "n")
        )
    )
    restricted = set(
        Restriction.objects.filter(
            user_id__in=user_ids, starts_at__lte=now, ends_at__gt=now, lifted_at__isnull=True
        ).values_list("user_id", flat=True)
    )
    # One board() call per day covers every resource requested that day.
    by_day = defaultdict(dict)
    for a in approvals:
        r = a.booking.resource
        by_day[timezone.localtime(a.booking.start).date()][r.pk] = r
    strips = {}
    for day, resources in by_day.items():
        for r, sched in board(list(resources.values()), day, user, now=now):
            strips[(r.pk, day)] = sched

    cards = []
    for a in approvals:
        b = a.booking
        day = timezone.localtime(b.start).date()
        steps = orders.get(b.pk) or [a.step_order]
        day_start = timezone.localtime(b.start).replace(hour=DAY_START, minute=0, second=0, microsecond=0)
        cards.append(
            {
                "a": a,
                "b": b,
                "r": b.resource,
                "day": day,
                "step": steps.index(a.step_order) + 1 if a.step_order in steps else 1,
                "steps": len(steps),
                "sla": _sla(a, now),
                "no_shows": no_shows.get(b.booked_for_id, 0),
                "restricted": b.booked_for_id in restricted,
                "fill": min(1.0, b.attendees / b.resource.capacity) if b.resource.capacity else 0,
                "over_capacity": b.attendees > b.resource.capacity,
                "schedule": strips.get((b.resource_id, day)),
                "mark": _mark(b, day_start),
            }
        )
    return cards


@staff_required("approve_bookings")
def queue(request):
    now = timezone.now()
    qs = services.queue_for(request.user).select_related("booking__requester", "booking__booked_for__department")
    type_counts = Counter()
    types = {}
    for t_code, t_name, t_plural, t_icon in qs.values_list(
        "booking__resource__type__code",
        "booking__resource__type__name",
        "booking__resource__type__plural",
        "booking__resource__type__icon",
    ):
        type_counts[t_code] += 1
        types[t_code] = (t_plural or t_name, t_icon)
    total = sum(type_counts.values())
    chosen = request.GET.get("type", "")
    if chosen and chosen in types:
        qs = qs.filter(booking__resource__type__code=chosen)
    else:
        chosen = ""
    overdue_only = request.GET.get("overdue") == "1"
    if overdue_only:
        qs = qs.filter(due_at__lt=now)
    shown = list(qs[:QUEUE_LIMIT])
    cards = _decorate(shown, request.user, now)
    groups = defaultdict(list)
    for c in cards:
        groups[c["day"]].append(c)
    overdue = services.queue_for(request.user).filter(due_at__lt=now).count()
    ctx = {
        "groups": sorted(groups.items()),
        "total": total,
        "filtered_count": qs.count() if (chosen or overdue_only) else total,
        "shown": len(cards),
        "limit": QUEUE_LIMIT,
        "type_filters": [
            {"code": code, "label": types[code][0], "icon": types[code][1], "count": n}
            for code, n in sorted(type_counts.items(), key=lambda kv: types[kv[0]][0])
        ],
        "chosen": chosen,
        "overdue_only": overdue_only,
        "overdue": overdue,
        "now": now,
        "here": request.get_full_path(),
    }
    return render(request, "manage/approvals.html", ctx)


def _approval_or_404(request, pk):
    try:
        a = Approval.objects.select_related(
            "booking__resource__type", "booking__resource__building", "booking__booked_for__department",
            "booking__requester", "decided_by",
            "workflow",
        ).get(pk=pk, booking__institution_id=request.user.institution_id)
    except Approval.DoesNotExist:
        raise Http404 from None
    return a


@staff_required("approve_bookings")
@require_POST
def decide(request, pk):
    a = _approval_or_404(request, pk)
    # Object-level: an approval you may not decide does not exist for you. A step a colleague
    # decided a moment ago is still reported in place (to people who were asked), not as a 404.
    if a.decision == Decision.PENDING:
        if not services.can_decide(request.user, a):
            raise Http404
    elif not (is_campus_wide(request.user) or services.approvers_for(a).filter(pk=request.user.pk).exists()):
        raise Http404
    action = request.POST.get("action", "")
    comment = request.POST.get("comment", "").strip()
    error = None
    if action not in ("approve", "reject"):
        error = "Choose approve or reject."
    elif a.decision == Decision.PENDING:
        try:
            services.decide(a, request.user, approve=action == "approve", comment=comment, request=request)
        except DomainError as exc:
            error = exc.message
    a = _approval_or_404(request, pk)
    b = a.booking
    back = safe_next(request, reverse("manage:approvals"))

    if request.headers.get("HX-Request"):
        if a.decision == Decision.PENDING and b.status == "pending":
            # Still decidable (e.g. a rejection without a reason): re-render with the sentence.
            [card] = _decorate([a], request.user, timezone.now())
            return render(request, "manage/_approval_card.html", {"c": card, "error": error, "here": back})
        return render(request, "manage/_approval_card.html", {"done": _outcome(a, b, request.user), "c": None})
    if error:
        messages.error(request, error)
    else:
        messages.success(request, _outcome(a, b, request.user)["sentence"])
    return redirect(back)


def _outcome(a, b, user):
    who = b.booked_for.display_name
    if b.status == "approved":
        tone, sentence = "success", f"Approved. {who}'s booking of {b.resource.name} is confirmed and the QR pass is on its way."
    elif b.status == "rejected":
        tone, sentence = "danger", f"Rejected. {who} has been told why."
    elif b.status == "expired":
        tone, sentence = "warn", "The start time passed before a decision, so the request expired and the slot was released."
    elif b.status == "pending" and a.decision == Decision.APPROVED:
        nxt = b.approvals.filter(decision=Decision.PENDING).first()
        step = nxt.get_approver_role_display().lower() if nxt else "the next approver"
        tone, sentence = "success", f"Approved your step. It now goes to {step}."
    elif a.decided_by_id and a.decided_by_id != user.pk:
        tone, sentence = "info", f"Already {a.get_decision_display().lower()} by {a.decided_by.display_name}."
    else:
        tone, sentence = "info", f"This request is {b.get_status_display().lower()}."
    return {"tone": tone, "sentence": sentence, "booking": b, "resource": b.resource}
