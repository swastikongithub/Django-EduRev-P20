"""API throttles keyed on the trusted client address (kept apart from apps.core.api to avoid an import cycle with DRF's views)."""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from apps.core.http import client_ip


class _ClientIdentMixin:
    """
    Key anonymous throttling on the same client address as the sign-in rate limiter and the audit
    log (apps.core.http.client_ip), which honours TRUSTED_CLIENT_IP_HEADER (Railway: X-Real-IP)
    or TRUSTED_PROXY_HOPS. DRF's default only understands X-Forwarded-For, so behind an edge that
    sets a different header every anonymous caller would otherwise share the proxy's address.
    """

    def get_ident(self, request):
        return client_ip(request) or super().get_ident(request)


class ClientAnonRateThrottle(_ClientIdentMixin, AnonRateThrottle):
    pass


class ClientUserRateThrottle(_ClientIdentMixin, UserRateThrottle):
    pass
