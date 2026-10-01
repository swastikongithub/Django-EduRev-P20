"""
Stock (/manage/inventory/): accessories and consumables in the user's scope, what is low,
what went out recently, and restocking. Changes go through inventory.services.restock.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, F, Q, Sum
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import is_campus_wide
from apps.core.errors import DomainError
from apps.core.http import int_param, safe_next
from apps.core.manage_views import staff_required
from apps.core.scope import managed_resources, scope_label

from . import services
from .models import InventoryItem, Issuance, IssuanceStatus, ItemKind

RECENT_DAYS = 7


def _items(user):
    qs = InventoryItem.objects.filter(institution_id=user.institution_id)
    if is_campus_wide(user):
        return qs
    # can_manage_item: outside campus-wide roles only items tied to a resource you manage.
    return qs.filter(resource_id__in=managed_resources(user).values("pk"))


@staff_required("manage_inventory")
def index(request):
    user, now = request.user, timezone.now()
    base = _items(user)
    low_only = request.GET.get("low") == "1"
    kind = request.GET.get("kind", "")
    q = request.GET.get("q", "").strip()
    items = base.select_related("resource__building", "resource_type")
    if low_only:
        items = items.filter(quantity_available__lte=F("reorder_level"))
    if kind in ItemKind.values:
        items = items.filter(kind=kind)
    else:
        kind = ""
    if q:
        items = items.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    items = list(items.order_by("name"))

    since = now - timedelta(days=RECENT_DAYS)
    recent = defaultdict(dict)
    for item_id, status, n in (
        Issuance.objects.filter(item_id__in=[i.pk for i in items])
        .filter(Q(issued_at__gte=since) | Q(returned_at__gte=since))
        .values("item_id", "status")
        .annotate(n=Sum("quantity"))
        .values_list("item_id", "status", "n")
    ):
        recent[item_id][status] = n
    rows = []
    for i in items:
        r = recent.get(i.pk, {})
        ratio = (i.quantity_available / i.quantity_total) if i.quantity_total else (0 if i.is_low else 1)
        rows.append(
            {
                "i": i,
                "ratio": max(0.0, min(1.0, ratio)),
                "tone": "is-high" if i.is_low else ("is-mid" if i.quantity_available <= i.reorder_level * 2 else ""),
                "issued": r.get(IssuanceStatus.ISSUED, 0),
                "returned": r.get(IssuanceStatus.RETURNED, 0),
                "consumed": r.get(IssuanceStatus.CONSUMED, 0),
                "lost": r.get(IssuanceStatus.LOST, 0),
                "out": i.quantity_total - i.quantity_available if i.kind == ItemKind.ACCESSORY else 0,
            }
        )

    totals = base.aggregate(
        n=Count("id"),
        low=Count("id", filter=Q(quantity_available__lte=F("reorder_level"))),
    )
    out_now = (
        Issuance.objects.filter(item__in=base, status=IssuanceStatus.ISSUED).aggregate(n=Sum("quantity"))["n"] or 0
    )
    activity = list(
        Issuance.objects.filter(item__in=base)
        .exclude(status__in=[IssuanceStatus.RESERVED, IssuanceStatus.CANCELLED])
        .select_related("item", "booking__resource", "booking__booked_for")
        .order_by("-created_at")[:12]
    )
    ctx = {
        "rows": rows,
        "total": totals["n"],
        "low_count": totals["low"],
        "out_now": out_now,
        "consumed_week": Issuance.objects.filter(
            item__in=base, status=IssuanceStatus.CONSUMED, issued_at__gte=since
        ).aggregate(n=Sum("quantity"))["n"]
        or 0,
        "activity": activity,
        "low_only": low_only,
        "kind": kind,
        "kinds": ItemKind.choices,
        "q": q,
        "filtered": bool(low_only or kind or q),
        "recent_days": RECENT_DAYS,
        "scope_label": scope_label(user),
        "here": request.get_full_path(),
    }
    return render(request, "manage/inventory.html", ctx)


# One delivery at most; also keeps stock columns (PostgreSQL integer) far from overflow.
MAX_RESTOCK = 100_000


@staff_required("manage_inventory")
@require_POST
def restock(request, pk):
    try:
        item = _items(request.user).select_related("resource").get(pk=pk)
    except InventoryItem.DoesNotExist:
        raise Http404 from None
    if not services.can_manage_item(request.user, item):
        raise Http404
    back = safe_next(request, reverse("manage:inventory"))
    qty = int_param(request.POST.get("qty"))
    if qty is None or not 0 < qty <= MAX_RESTOCK:
        messages.error(request, f"Enter how many units arrived, as a whole number from 1 to {MAX_RESTOCK:,}.")
        return redirect(back)
    note = request.POST.get("note", "").strip()[:200]
    try:
        item = services.restock(item, qty, request.user, note=note, request=request)
    except DomainError as exc:
        messages.error(request, exc.message)
    else:
        tail = " Still at or under the reorder level." if item.is_low else ""
        messages.success(request, f"Restocked. {item.name}: {item.quantity_available} {item.unit} available now.{tail}")
    return redirect(back)
