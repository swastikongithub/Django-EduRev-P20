from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request, fallback: str) -> str:
    """Return ?next / POST next only when it points back to this site (no open redirects)."""
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return fallback
