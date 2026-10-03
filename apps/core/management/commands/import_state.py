"""
Load a bundle written by `export_state` into this database (apps.core.state_transfer):

    python manage.py import_state lpu-state.json.gz --dry-run
    python manage.py import_state lpu-state.json.gz --production-confirm

One transaction: either everything lands or nothing does. `--dry-run` performs every step and
check, reports what would happen, and rolls back (no media is uploaded). Writing to a database
with DEBUG off requires `--production-confirm`. Running it again adds nothing new. Existing
accounts are never modified; imported accounts get no usable password and no MFA enrolment.
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core import state_transfer as st


class Command(BaseCommand):
    help = "Import a state bundle (dependency-ordered, idempotent, sanitised)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Bundle written by export_state ('-' reads stdin)")
        parser.add_argument("--dry-run", action="store_true", help="Run every step, then roll back")
        parser.add_argument(
            "--production-confirm",
            action="store_true",
            help="Required to write when DEBUG is off (a production database)",
        )

    def handle(self, *args, path, dry_run, production_confirm, **opts):
        if not dry_run and not settings.DEBUG and not production_confirm:
            raise CommandError(
                "This looks like production (DEBUG is off). Re-run with --production-confirm, or --dry-run."
            )
        if path == "-":
            import gzip
            import sys

            bundle = json.loads(gzip.decompress(sys.stdin.buffer.read()))
            if bundle.get("format") != st.FORMAT:
                raise CommandError("Unsupported bundle format.")
        else:
            bundle = st.read_bundle(path)
        try:
            report = st.import_bundle(bundle, dry_run=dry_run)
        except st.TransferError as exc:
            raise CommandError(str(exc)) from exc
        r = report.as_dict()
        self.stdout.write(f"{'model':34} {'created':>8} {'kept id':>8} {'matched':>8} {'updated':>8}")
        for label in r["created"]:
            self.stdout.write(
                f"{label:34} {r['created'][label]:>8} {r['kept_source_pk'].get(label, 0):>8} "
                f"{r['matched'].get(label, 0):>8} {r['updated'].get(label, 0):>8}"
            )
        self.stdout.write(
            f"media: {r['media_uploaded']} uploaded, {r['media_present']} already present, "
            f"{r['media_bytes']} bytes, missing in source: {r['media_missing']}"
        )
        self.stdout.write(
            f"accounts created: {len(r['created_usernames'])}; "
            f"accounts_digest {st.accounts_digest(r['created_usernames'])}"
            + (
                f" (bundle credentials digest {bundle['credentials']['accounts_digest']})"
                if "credentials" in bundle
                else ""
            )
        )
        if r["existing_users_kept"]:
            self.stdout.write(f"existing accounts kept unchanged: {', '.join(r['existing_users_kept'])}")
        verb = "Dry run complete; rolled back" if dry_run else "Imported"
        self.stdout.write(self.style.SUCCESS(verb))
