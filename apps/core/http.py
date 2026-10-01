"""Request helpers: safe redirects and bounded parsing of untrusted query/form values."""

from datetime import date, timedelta

from django.http import Http404
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

# PostgreSQL bigint; ids outside it raise DataError (HTTP 500) instead of "not found".
MAX_PK = 2**63 - 1
# Calendar views and forms only make sense within a few years of today. Bounding dates keeps
# `day ± timedelta` arithmetic away from date.min/date.max, where it overflows (SEC-13).
MAX_DATE_DISTANCE = timedelta(days=3660)


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
