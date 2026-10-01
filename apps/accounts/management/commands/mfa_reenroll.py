"""
Local development only: make one account enrol a new authenticator at its next sign-in.

    python manage.py mfa_reenroll <username>

Use it when a development database holds an enrolment that can no longer be used, for example a
TOTP secret encrypted under a DJANGO_SECRET_KEY that is gone (`manage.py mfa_keys` lists those).
It does not enrol anything itself and changes no MFA policy. It clears the stale enrolment and
ends the account's sessions. The next password sign-in then runs the normal enrolment step
(`accounts.views.mfa_view`): a new secret, a QR code from the standard otpauth provisioning URI,
and activation only after a correct, non-replayed code. The replay counter (`mfa_last_step`) is
kept, so no code that was already accepted can be accepted again.

Refused unless DEBUG is on and the database is on this machine. In production, an administrator's
lost device is handled as in docs/runbook.md#secret-rotation.
"""

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.accounts import mfa
from apps.accounts.models import User
from apps.audit.services import record

LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}


def ensure_local_development() -> None:
    if not settings.DEBUG:
        raise CommandError("mfa_reenroll is for local development only: DEBUG is off.")
    host = connection.settings_dict.get("HOST") or ""
    if host not in LOCAL_HOSTS and not host.startswith("/"):  # "/..." is a local Unix socket
        raise CommandError(f"mfa_reenroll is for local development only: the database is on {host!r}.")


class Command(BaseCommand):
    help = "LOCAL DEVELOPMENT ONLY: clear one account's MFA enrolment so it enrols again at next sign-in."

    def add_arguments(self, parser):
        parser.add_argument("username", help="The account to re-enrol (required; there is no 'all').")

    def handle(self, *args, username, **opts):
        ensure_local_development()
        user = User.objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"No account named {username!r}.")
        if not user.is_active:
            raise CommandError(f"{username!r} is not active.")

        readable = bool(user.mfa_secret) and mfa.decrypt(user.mfa_secret) is not None
        with transaction.atomic():
            user.mfa_enabled = False
            user.mfa_secret = ""
            user.save(update_fields=["mfa_enabled", "mfa_secret"])  # mfa_last_step kept: no replays
            ended = 0
            for session in Session.objects.all().iterator():
                if session.get_decoded().get("_auth_user_id") == str(user.pk):
                    session.delete()
                    ended += 1
            record(None, "auth.mfa_reset", user, after={"via": "manage.py mfa_reenroll", "was_readable": readable})

        self.stdout.write(self.style.SUCCESS(f"Cleared the MFA enrolment of {username!r}; ended {ended} session(s)."))
        if mfa.required_for(user):
            self.stdout.write(
                "Next: sign in with the password at /login/ (or /django-admin/). The page shows a new QR code; "
                "scan it with your authenticator app and enter the 6-digit code to finish."
            )
        else:
            self.stdout.write(
                "This account's role does not require MFA; it can enrol again from its next sign-in only if required."
            )
