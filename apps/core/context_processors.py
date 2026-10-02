"""
Shell context: navigation built from the user's *capabilities* (not hard-coded per page),
plus the few live counts the rail shows. Hiding a link is only cosmetic — every
destination re-checks the capability server-side.
"""

from dataclasses import dataclass

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _

from apps.accounts.permissions import has_cap


@dataclass
class NavItem:
    label: str
    icon: str
    url: str
    match: tuple
    count: int = 0


def _url(name, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return None


def _nav(user, counts):
    book = [
        ("Home", "house", "core:home", ("/home",)),
        ("Find", "search", "catalogue:find", ("/find", "/r/")),
        ("Calendar", "calendar-days", "bookings:calendar", ("/calendar",)),
        ("Bookings", "calendar-check", "bookings:mine", ("/bookings", "/b/")),
        ("Scan", "scan-line", "checkins:scan", ("/scan", "/c/", "/here/")),
    ]
    manage = []
    if has_cap(user, "approve_bookings"):
        manage.append(
            ("Approvals", "list-checks", "manage:approvals", ("/manage/approvals",), counts.get("approvals", 0))
        )
    if has_cap(user, "manage_resources") or has_cap(user, "approve_bookings"):
        manage.append(("Board", "rows-3", "manage:board", ("/manage/board",), 0))
        manage.append(("Resources", "building-2", "manage:resources", ("/manage/resources",), 0))
    if has_cap(user, "manage_maintenance"):
        manage.append(("Upkeep", "wrench", "manage:maintenance", ("/manage/maintenance",), counts.get("breakdowns", 0)))
    if has_cap(user, "manage_inventory"):
        manage.append(("Stock", "package", "manage:inventory", ("/manage/inventory",), counts.get("low_stock", 0)))
    if has_cap(user, "view_department_analytics") or has_cap(user, "view_campus_analytics"):
        manage.append(("Insights", "chart-column", "analytics:dashboard", ("/insights",), 0))
    if has_cap(user, "configure_policy") or has_cap(user, "manage_timetable") or has_cap(user, "manage_users"):
        manage.append(
            (
                "Setup",
                "sliders-horizontal",
                "manage:setup",
                (
                    "/manage/setup",
                    "/manage/catalogue",
                    "/manage/policies",
                    "/manage/workflows",
                    "/manage/timetable",
                    "/manage/users",
                    "/manage/audit",
                    "/manage/no-shows",
                    "/manage/ops",
                ),
                0,
            )
        )

    def build(items):
        out = []
        for it in items:
            label, ic, name, match = it[:4]
            url = _url(name)
            if url:
                out.append(NavItem(_(label), ic, url, match, it[4] if len(it) > 4 else 0))
        return out

    return build(book), build(manage)


def shell(request):
    user = getattr(request, "user", None)
    # campus_tz: the zone bookings are in; client-side clocks (calendar now-line, "Today") use it.
    ctx = {"DEMO_MODE": settings.DEMO_MODE, "SITE_NAME": "LPU Reserve", "campus_tz": settings.TIME_ZONE}
    if not user or not user.is_authenticated:
        return ctx
    counts = {}
    from apps.notifications.services import unread_count

    counts["unread"] = unread_count(user)
    if has_cap(user, "approve_bookings"):
        from apps.approvals.services import queue_for

        counts["approvals"] = queue_for(user).count()
    if has_cap(user, "manage_maintenance"):
        from apps.maintenance.models import BreakdownReport, ReportStatus

        qs = BreakdownReport.objects.filter(institution_id=user.institution_id, status=ReportStatus.OPEN)
        if user.role == "custodian":
            qs = qs.filter(resource__custodians__user=user)
        counts["breakdowns"] = qs.count()
    if has_cap(user, "manage_inventory"):
        from apps.inventory.services import low_stock

        qs = low_stock(user.institution_id)
        if user.role == "custodian":
            qs = qs.filter(resource__custodians__user=user)
        counts["low_stock"] = qs.count()
    book_nav, manage_nav = _nav(user, counts)
    ctx.update({"nav_book": book_nav, "nav_manage": manage_nav, "counts": counts})
    return ctx


def brand(request):
    """Official LPU artwork when it has been added to static/img/brand/ (docs/branding.md)."""
    from apps.core.branding import brand_assets

    return {"brand": brand_assets()}
