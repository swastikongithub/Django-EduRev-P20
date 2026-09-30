"""Sign-in (with lockout), demo personas, profile and booking standing."""

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.audit.services import record

from .models import User

# Stable usernames created by `manage.py seed_demo`. Only reachable when DEMO_MODE=1.
DEMO_PERSONAS = [
    ("student", "Student", "Find a room, book it, check in with QR"),
    ("faculty", "Faculty", "Book for a class, set up a weekly lab"),
    ("custodian", "Custodian", "Approve requests, run the board, upkeep"),
    ("hod", "Head of Department", "Department usage and quotas"),
    ("facility", "Facility Manager", "Campus insights, policies, timetable"),
    ("admin", "Administrator", "Workflows, roles and system setup"),
]


def _safe_next(request, fallback="core:home"):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return fallback


@ratelimit(key="ip", rate="20/m", method="POST", block=False)
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))
    error = ""
    username = ""
    if request.method == "POST":
        if getattr(request, "limited", False):
            error = "Too many sign-in attempts from this network. Wait a minute and try again."
        else:
            username = (request.POST.get("username") or "").strip()
            password = request.POST.get("password") or ""
            account = User.objects.filter(username__iexact=username).first() or User.objects.filter(vid=username).first()
            if account and account.is_locked:
                mins = int((account.locked_until - timezone.now()).total_seconds() // 60) + 1
                error = f"This account is locked after repeated failed attempts. Try again in {mins} min."
            else:
                user = authenticate(request, username=account.username if account else username, password=password)
                if user is not None:
                    User.objects.filter(pk=user.pk).update(failed_logins=0, locked_until=None)
                    login(request, user)
                    record(user, "auth.login", user, request=request)
                    return redirect(_safe_next(request))
                if account:
                    account.failed_logins += 1
                    fields = ["failed_logins"]
                    if account.failed_logins >= settings.LOGIN_LOCKOUT_THRESHOLD:
                        account.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
                        account.failed_logins = 0
                        fields.append("locked_until")
                        record(None, "auth.lockout", account, request=request)
                    account.save(update_fields=fields)
                error = "That VID / username and password don't match."
    personas = []
    if settings.DEMO_MODE:
        found = {u.username: u for u in User.objects.filter(username__in=[p[0] for p in DEMO_PERSONAS], is_active=True)}
        personas = [(found[u], label, blurb) for u, label, blurb in DEMO_PERSONAS if u in found]
    return render(request, "accounts/login.html", {"error": error, "username": username, "personas": personas,
                                                   "next": request.GET.get("next", "")})


@require_POST
@ratelimit(key="ip", rate="30/m", method="POST", block=True)
def demo_login(request):
    """One-click persona sign-in for demonstrations. Disabled unless DEMO_MODE=1."""
    if not settings.DEMO_MODE:
        raise Http404
    username = request.POST.get("username", "")
    if username not in {p[0] for p in DEMO_PERSONAS}:
        raise Http404
    user = User.objects.filter(username=username, is_active=True).first()
    if not user:
        messages.error(request, "Demo data isn't loaded. Run: python manage.py seed_demo")
        return redirect("accounts:login")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    record(user, "auth.demo_login", user, request=request)
    return redirect(_safe_next(request))


@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")


@login_required
def me(request):
    from apps.bookings.models import Booking, BookingStatus
    from apps.checkins.models import NoShow
    from apps.checkins.services import active_restriction
    from apps.rules.models import RestrictionTier
    from apps.rules.services import quota_usage

    user = request.user
    now = timezone.now()
    tiers = list(RestrictionTier.objects.filter(institution_id=user.institution_id).order_by("no_shows"))
    window = max([t.window_days for t in tiers], default=30)
    recent_no_shows = NoShow.objects.filter(user=user, forgiven=False, detected_at__gte=now - timedelta(days=window)).select_related("resource", "booking")
    stats = {
        "completed": Booking.objects.filter(booked_for=user, status=BookingStatus.COMPLETED).count(),
        "no_shows": NoShow.objects.filter(user=user, forgiven=False).count(),
        "upcoming": Booking.objects.filter(booked_for=user, status__in=["pending", "approved"], period__startswith__gte=now).count(),
    }
    feed_url = request.build_absolute_uri(f"/feed/{user.calendar_token}.ics")
    return render(request, "accounts/me.html", {
        "quotas": quota_usage(user),
        "restriction": active_restriction(user),
        "recent_no_shows": recent_no_shows,
        "tiers": tiers,
        "stats": stats,
        "feed_url": feed_url,
    })
