"""Session-level MFA enforcement (CES §1.1; SEC-01 defence in depth, SEC-12)."""

from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse
from django.urls import reverse

from . import mfa


class MFASessionMiddleware:
    """
    A user who needs MFA (privileged role, or enrolled) may only use a session that passed the
    second factor. Anything else — a session created before the user was promoted, or by a sign-in
    path that skipped MFA — is ended and the person signs in again, this time with their code.
    Must sit after AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and mfa.needs_mfa(user):
            if not mfa.session_verified(request, user):
                return self._step_up(request, user)
        return self.get_response(request)

    def _step_up(self, request, user):
        from apps.audit.services import record

        record(user, "auth.mfa_step_up", user, request=request)
        logout(request)
        if request.path.startswith("/api/"):
            return JsonResponse(
                {
                    "error": {
                        "code": "mfa_required",
                        "message": "Sign in again with your authenticator code to continue.",
                        "detail": {},
                    }
                },
                status=401,
            )
        return redirect_to_login(request.get_full_path(), reverse("accounts:login"))
