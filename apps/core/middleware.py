from django.conf import settings
from django.utils.cache import patch_cache_control

from .models import Institution


class InstitutionMiddleware:
    """Resolve the tenant for this request (user's institution, else the default)."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._default = None

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            request.institution_id = user.institution_id
        else:
            if self._default is None:
                self._default = (
                    Institution.objects.filter(code=settings.DEFAULT_INSTITUTION_CODE)
                    .values_list("pk", flat=True)
                    .first()
                )
            request.institution_id = self._default
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Content-Security-Policy and Permissions-Policy (camera allowed for QR scanning, same origin only)."""

    CSP = "; ".join(
        [
            "default-src 'self'",
            "img-src 'self' data: blob:",
            "style-src 'self' 'unsafe-inline'",
            "font-src 'self'",
            "script-src 'self'",
            "connect-src 'self'",
            "media-src 'self' blob:",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith(("/api/v1/docs/", "/django-admin/")):
            response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", "camera=(self), geolocation=(), microphone=()")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            # Personal pages are never stored by shared caches (proxies, CDNs). Pages that show a
            # secret (TOTP seed, data export, QR passes, feed URL) also send no-store via
            # @never_cache (SEC-09).
            patch_cache_control(response, private=True)
        return response
