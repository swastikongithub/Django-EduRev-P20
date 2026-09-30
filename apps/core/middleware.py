from django.conf import settings

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
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
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
        if not request.path.startswith(("/api/docs", "/admin/")):
            response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", "camera=(self), geolocation=(), microphone=()")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response
