"""Sign-in (with lockout), demo personas, profile and booking standing."""

import logging
import time
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.audit.services import record

from . import mfa
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


log = logging.getLogger("security")

BAD_CREDENTIALS = "That VID / username and password don't match."
MFA_UNREADABLE_MESSAGE = (
    "Your code can't be checked: this server can no longer read the key your authenticator app was set up "
    "with. This is a server configuration problem, not a wrong code, and it does not count against your "
    "account. Ask an administrator to restore the previous secret key or to reset your two-step sign-in."
)
# How long a correct password stays "half signed in" waiting for the TOTP code.
MFA_PENDING_SECONDS = 10 * 60


def _count_failure(user_pk, request) -> bool:
    """
    Add one failed attempt (password or TOTP code) and lock the account at the threshold.

    The count is changed under a row lock: concurrent wrong answers each see the previous one's
    count. A read-modify-write on a stale copy let a burst of simultaneous guesses overwrite each
    other and never reach the lockout. Returns True when this attempt locked the account.
    """
    with transaction.atomic():
        account = User.objects.select_for_update().get(pk=user_pk)
        account.failed_logins += 1
        fields = ["failed_logins"]
        locked = account.failed_logins >= settings.LOGIN_LOCKOUT_THRESHOLD
        if locked:
            account.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            account.failed_logins = 0
            fields.append("locked_until")
        account.save(update_fields=fields)
    if locked:
        record(None, "auth.lockout", account, request=request)
    return locked


def _safe_next(request, fallback="core:home"):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return fallback


@never_cache
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
            account = (
                User.objects.filter(username__iexact=username).first() or User.objects.filter(vid=username).first()
            )
            if account and account.is_locked:
                # Same answer, at about the same cost, as a wrong password: a lockout must not
                # confirm that the account exists (SEC-10). The hint under the form explains
                # lockouts to everyone alike.
                User().set_password(password)
                error = BAD_CREDENTIALS
            else:
                user = authenticate(request, username=account.username if account else username, password=password)
                if user is not None:
                    if mfa.needs_mfa(user):
                        # Password is right, but privileged roles need a second factor before
                        # a session exists. Keep only the pending user id in the anonymous session.
                        # The failure count is left alone until the code is right too, so wrong
                        # codes add up across password re-entries (SEC-03).
                        request.session["mfa_pending"] = user.pk
                        request.session["mfa_pending_at"] = int(time.time())
                        request.session["mfa_next"] = _safe_next(request, fallback="/home/")
                        return redirect("accounts:mfa")
                    User.objects.filter(pk=user.pk).update(failed_logins=0, locked_until=None)
                    login(request, user)
                    record(user, "auth.login", user, request=request)
                    return redirect(_safe_next(request))
                if account:
                    _count_failure(account.pk, request)
                error = BAD_CREDENTIALS
    personas = []
    if settings.DEMO_MODE:
        found = {u.username: u for u in User.objects.filter(username__in=[p[0] for p in DEMO_PERSONAS], is_active=True)}
        personas = [(found[u], label, blurb) for u, label, blurb in DEMO_PERSONAS if u in found]
    return render(
        request,
        "accounts/login.html",
        {"error": error, "username": username, "personas": personas, "next": request.GET.get("next", "")},
    )


def admin_login(request, extra_context=None):
    """
    Replaces Django admin's own login view (`admin.site.login`).

    The stock admin form calls `login()` after a password check alone, which would skip the
    lockout, the rate limit and TOTP MFA. Routing it through `login_view` gives /django-admin/
    exactly the same sign-in as the rest of the product.
    """
    from django.contrib import admin
    from django.core.exceptions import PermissionDenied

    if request.user.is_authenticated:
        if admin.site.has_permission(request):
            return redirect(_safe_next(request, fallback="admin:index"))
        # Signed in but not admin staff: say no rather than bounce between the two login views.
        raise PermissionDenied
    return login_view(request)


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
    mfa.mark_verified(request, user, demo=True)  # demo personas skip MFA, and only while DEMO_MODE=1
    record(user, "auth.demo_login", user, request=request)
    return redirect(_safe_next(request))


@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")


@never_cache
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
    recent_no_shows = NoShow.objects.filter(
        user=user, forgiven=False, detected_at__gte=now - timedelta(days=window)
    ).select_related("resource", "booking")
    stats = {
        "completed": Booking.objects.filter(booked_for=user, status=BookingStatus.COMPLETED).count(),
        "no_shows": NoShow.objects.filter(user=user, forgiven=False).count(),
        "upcoming": Booking.objects.filter(
            booked_for=user, status__in=["pending", "approved"], period__startswith__gte=now
        ).count(),
    }
    feed_url = request.build_absolute_uri(f"/feed/{user.calendar_token}.ics")
    return render(
        request,
        "accounts/me.html",
        {
            "quotas": quota_usage(user),
            "restriction": active_restriction(user),
            "recent_no_shows": recent_no_shows,
            "tiers": tiers,
            "stats": stats,
            "feed_url": feed_url,
        },
    )


@never_cache
@login_required
def export_my_data(request):
    """DPDP Act 2023 data-subject access: everything we hold about the signed-in person, as JSON."""
    import json

    from django.http import HttpResponse

    from apps.bookings.models import Booking
    from apps.checkins.models import NoShow, Restriction
    from apps.notifications.models import Notification

    user = request.user
    data = {
        "generated_at": timezone.now().isoformat(),
        "profile": {
            "username": user.username,
            "name": user.display_name,
            "email": user.email,
            "vid": user.vid,
            "role": user.role,
            "department": str(user.department or ""),
            "section": user.section,
            "programme": user.programme,
            "designation": user.designation,
            "date_joined": user.date_joined.isoformat(),
            "last_login": user.last_login.isoformat() if user.last_login else None,
        },
        "bookings": [
            {
                "reference": b.reference,
                "resource": b.resource.name,
                "start": b.start.isoformat(),
                "end": b.end.isoformat(),
                "status": b.status,
                "title": b.title,
                "group": b.group_label,
                "attendees": b.attendees,
                "checked_in_at": b.checked_in_at.isoformat() if b.checked_in_at else None,
            }
            for b in Booking.objects.filter(booked_for=user).select_related("resource").order_by("period")
        ],
        "no_shows": [
            {
                "booking": n.booking.reference,
                "resource": n.resource.name,
                "detected_at": n.detected_at.isoformat(),
                "forgiven": n.forgiven,
            }
            for n in NoShow.objects.filter(user=user).select_related("booking", "resource")
        ],
        "restrictions": [
            {
                "from": r.starts_at.isoformat(),
                "until": r.ends_at.isoformat(),
                "reason": r.reason,
                "lifted_at": r.lifted_at.isoformat() if r.lifted_at else None,
            }
            for r in Restriction.objects.filter(user=user)
        ],
        "notifications": [
            {"at": n.created_at.isoformat(), "title": n.title, "body": n.body}
            for n in Notification.objects.filter(user=user)[:500]
        ],
    }
    record(user, "privacy.export", user, request=request)
    resp = HttpResponse(json.dumps(data, indent=2), content_type="application/json")
    resp["Content-Disposition"] = 'attachment; filename="my-lpu-reserve-data.json"'
    return resp


@never_cache
@ratelimit(key="ip", rate="20/m", method="POST", block=False)
def mfa_view(request):
    """Second step for privileged roles: verify a TOTP code, or enrol on first sign-in."""
    pk = request.session.get("mfa_pending")
    started = request.session.get("mfa_pending_at") or 0
    if pk and time.time() - started > MFA_PENDING_SECONDS:
        # A password entered long ago no longer vouches for whoever is at the keyboard now.
        for k in ("mfa_pending", "mfa_pending_at", "mfa_new_secret", "mfa_next"):
            request.session.pop(k, None)
        messages.info(request, "Sign-in timed out. Enter your password again.")
        return redirect("accounts:login")
    user = User.objects.filter(pk=pk, is_active=True).first() if pk else None
    if user is None:
        return redirect("accounts:login")
    enrolling = not user.mfa_enabled
    secret = None
    if enrolling:
        secret = mfa.decrypt(request.session.get("mfa_new_secret") or "")
        if secret is None:  # first visit, or the key changed mid-enrolment: start from a fresh secret
            secret = mfa.new_secret()
            request.session["mfa_new_secret"] = mfa.encrypt(secret)
    else:
        secret = mfa.decrypt(user.mfa_secret)
    error = ""
    if secret is None:
        # The stored secret exists but no configured key can read it (DJANGO_SECRET_KEY changed
        # without DJANGO_SECRET_KEY_FALLBACKS). No code can succeed, so say so instead of
        # "didn't match", and do not count it towards the lockout. Reported once per sign-in.
        error = MFA_UNREADABLE_MESSAGE
        if not request.session.get("mfa_unreadable_reported"):
            request.session["mfa_unreadable_reported"] = True
            log.error("MFA secret for user %s cannot be decrypted with the configured keys", user.pk)
            record(None, "auth.mfa_secret_unreadable", user, request=request)
    elif request.method == "POST":
        if getattr(request, "limited", False):
            error = "Too many attempts. Wait a minute and try again."
        elif user.is_locked:
            error = "This account is locked after repeated failed attempts."
        else:
            step = mfa.matched_step(secret, request.POST.get("code", ""))
            if step is not None and mfa.consume_step(user, step):
                if enrolling:
                    user.mfa_secret = mfa.encrypt(secret)
                    user.mfa_enabled = True
                    user.save(update_fields=["mfa_secret", "mfa_enabled"])
                    record(user, "auth.mfa_enrolled", user, request=request)
                elif mfa.reencrypt_if_needed(user):
                    log.info("MFA secret for user %s moved to the current secret key", user.pk)
                nxt = request.session.get("mfa_next") or "/home/"
                for k in ("mfa_pending", "mfa_pending_at", "mfa_new_secret", "mfa_next", "mfa_unreadable_reported"):
                    request.session.pop(k, None)
                User.objects.filter(pk=user.pk).update(failed_logins=0, locked_until=None)
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                mfa.mark_verified(request, user)
                record(user, "auth.login", user, after={"mfa": True}, request=request)
                return redirect(nxt)
            # A wrong code and a replayed one (SEC-11) both count towards the lockout.
            if _count_failure(user.pk, request):
                for k in ("mfa_pending", "mfa_new_secret"):
                    request.session.pop(k, None)
            if step is not None:
                error = "That code has already been used. Wait for the next one, then enter it."
            else:
                error = "That code didn't match. Codes change every 30 seconds; use the current one."
    ctx = {"error": error, "enrolling": enrolling, "user_name": user.display_name}
    if enrolling:
        from apps.checkins.qr import svg

        ctx["qr"] = svg(mfa.provisioning_uri(user, secret), box_size=6)
        ctx["secret"] = secret
    return render(request, "accounts/mfa.html", ctx)
