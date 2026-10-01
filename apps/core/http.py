"""Request helpers: client address, safe redirects and bounded parsing of untrusted values."""

import ipaddress
from datetime import date, timedelta

from django.conf import settings
from django.http import Http404
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

# PostgreSQL bigint; ids outside it raise DataError (HTTP 500) instead of "not found".
MAX_PK = 2**63 - 1
# Calendar views and forms only make sense within a few years of today. Bounding dates keeps
# `day ± timedelta` arithmetic away from date.min/date.max, where it overflows (SEC-13).
MAX_DATE_DISTANCE = timedelta(days=3660)


def client_ip(request) -> str | None:
    """
    The address of whoever connected to our outermost trusted proxy (SEC-07).

    X-Forwarded-For is written left to right by each hop, and anything left of our own proxies is
    whatever the client chose to send. With TRUSTED_PROXY_HOPS = n reverse proxies in front of the
    app, the real client is the n-th entry from the right. With 0 (the default) the header is
    ignored and REMOTE_ADDR is used. Shared by the audit log and the rate limiter
    (RATELIMIT_IP_META_KEY), so both see the same address.
    """
    if request is None:
        return None
    remote = request.META.get("REMOTE_ADDR") or None
    hops = getattr(settings, "TRUSTED_PROXY_HOPS", 0)
    if hops > 0:
        chain = [part.strip() for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if part.strip()]
        if len(chain) >= hops:
            candidate = chain[-hops]
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass
    return remote


def safe_next(request, fallback: str) -> str:
    """Return ?next / POST next only when it points back to this site (no open redirects)."""
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return fallback


def int_param(value, default=None, *, lo=None, hi=None):
    """`int(value)` clamped to [lo, hi], or `default` when it is not a whole number."""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def pk_param(value):
    """A primary key from untrusted input, or Http404: 'abc', '' and out-of-range ids are not found."""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        raise Http404 from None
    if not 0 < n <= MAX_PK:
        raise Http404
    return n


def date_param(value, default=None, *, today: date | None = None):
    """An ISO date within ten years of today, else `default`."""
    if not value:
        return default
    try:
        d = date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return default
    today = today or timezone.localdate()
    return d if abs(d - today) <= MAX_DATE_DISTANCE else default
