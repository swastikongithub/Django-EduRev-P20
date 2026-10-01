"""
Check (and finish) a DJANGO_SECRET_KEY rotation for stored TOTP secrets. Prints no secrets.

    python manage.py mfa_keys            # how many secrets each key can read; exit 1 if any are unreadable
    python manage.py mfa_keys --rotate   # re-encrypt fallback-only secrets with the current key

Rotation (docs/runbook.md#secret-rotation): put the old key in DJANGO_SECRET_KEY_FALLBACKS and the
new one in DJANGO_SECRET_KEY, deploy, run `mfa_keys --rotate`, and remove the fallback once this
command reports nothing left on it.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts import mfa
from apps.accounts.models import User


class Command(BaseCommand):
    help = "Report which secret key can read each stored TOTP secret; optionally move them to the current key."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rotate", action="store_true", help="Re-encrypt fallback-only secrets with the current key."
        )

    def handle(self, *args, rotate=False, **opts):
        current, fallback, unreadable, moved = 0, [], [], 0
        for user in User.objects.exclude(mfa_secret="").order_by("pk"):
            if mfa.under_current_key(user.mfa_secret):
                current += 1
            elif mfa.decrypt(user.mfa_secret) is not None:
                if rotate and mfa.reencrypt_if_needed(user):
                    moved += 1
                    current += 1
                else:
                    fallback.append(user.username)
            else:
                unreadable.append(user.username)
        self.stdout.write(f"current key: {current}")
        self.stdout.write(f"fallback key only: {len(fallback)}" + (f" ({', '.join(fallback)})" if fallback else ""))
        if moved:
            self.stdout.write(self.style.SUCCESS(f"re-encrypted with the current key: {moved}"))
        if unreadable:
            raise CommandError(
                f"unreadable with every configured key: {len(unreadable)} ({', '.join(unreadable)}). Add the key they "
                "were enrolled under to DJANGO_SECRET_KEY_FALLBACKS, or reset their enrolment (docs/runbook.md)."
            )
        self.stdout.write(self.style.SUCCESS("unreadable: 0"))
