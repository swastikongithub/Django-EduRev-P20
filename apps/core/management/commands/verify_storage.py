"""
Prove that uploaded media really persists: write a probe object through Django's default
storage, read it back through the URL the app would give a browser (pre-signed for S3), then
delete it. Run once after configuring a bucket, and after rotating its credentials:

    python manage.py verify_storage
"""

import secrets
import urllib.request

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Write, fetch (via the URL browsers get) and delete a probe object in media storage."

    def handle(self, *args, **opts):
        payload = secrets.token_bytes(32)
        name = default_storage.save(f"healthcheck/probe-{secrets.token_hex(8)}.bin", ContentFile(payload))
        try:
            url = default_storage.url(name)
            if url.startswith(("http://", "https://")):
                with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310 - our own storage URL
                    fetched = resp.read()
                where = "pre-signed URL" if "Signature" in url or "X-Amz-" in url else "URL"
            else:  # local disk: browsers are served by the web server, so read through storage instead
                with default_storage.open(name) as fh:
                    fetched = fh.read()
                where = "storage"
            if fetched != payload:
                raise CommandError(f"Probe object read back through {where} did not match what was written.")
        finally:
            default_storage.delete(name)
        if default_storage.exists(name):
            raise CommandError("Probe object could not be deleted.")
        backend = type(default_storage).__name__
        self.stdout.write(self.style.SUCCESS(f"Media storage OK ({backend}): write, read via {where}, delete."))
