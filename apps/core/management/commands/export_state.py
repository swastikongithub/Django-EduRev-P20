"""
Write this installation's business state to a sanitised bundle (apps.core.state_transfer):

    python manage.py export_state lpu-state.json.gz [--institution LPU]
    python manage.py export_state lpu-state.json.gz --existing-usernames swastik,Demo1 \
        --credentials "C:/Users/me/Desktop/LPU_RESERVE_DEMO_CREDENTIALS.md"

Reads only. The bundle holds none of this installation's password hashes, MFA secrets, sessions,
tokens or audit trail. With --credentials, every account the target does not already have
(--existing-usernames) gets a fresh random password: its hash goes into the bundle, the plaintext
only into that file, which must be outside the repository and is never overwritten. Nothing here
prints a password. Load the bundle elsewhere with `import_state`.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core import state_transfer as st


class Command(BaseCommand):
    help = "Export catalogue, rules, timetable, bookings, approvals and related state to a bundle file."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Where to write the bundle (gzip JSON)")
        parser.add_argument("--institution", default="LPU", help="Institution code to export (default LPU)")
        parser.add_argument(
            "--credentials", help="Private Markdown file for the generated passwords (outside the repo)"
        )
        parser.add_argument(
            "--existing-usernames", default="", help="Comma-separated usernames the target already has (never reset)"
        )
        parser.add_argument("--site-url", default="", help="Shown in the credentials file")
        parser.add_argument(
            "--public-demo-vids",
            default="",
            help="Comma-separated VIDs of Student accounts whose passwords will be published (README demo)",
        )
        parser.add_argument("--public-demo-out", help="Where to write just those VIDs and passwords (outside the repo)")

    def handle(
        self,
        *args,
        path,
        institution,
        credentials,
        existing_usernames,
        site_url,
        public_demo_vids,
        public_demo_out,
        **opts,
    ):
        out = self._private_path(credentials) if credentials else None
        public_out = self._private_path(public_demo_out) if public_demo_out else None
        public_vids = [v.strip() for v in public_demo_vids.split(",") if v.strip()]
        if public_vids and not (out and public_out):
            raise CommandError("--public-demo-vids needs --credentials and --public-demo-out.")
        try:
            bundle = st.export_bundle(institution_code=institution)
        except st.TransferError as exc:
            raise CommandError(str(exc)) from exc
        issued = []
        if out:
            existing = [u.strip() for u in existing_usernames.split(",") if u.strip()]
            try:
                issued = st.generate_credentials(bundle, existing_usernames=existing, public_vids=public_vids)
            except st.TransferError as exc:
                raise CommandError(str(exc)) from exc
            out.write_text(st.credentials_markdown(issued, site_url=site_url), encoding="utf-8")
            if public_out:
                public_out.write_text(st.public_demo_markdown(issued), encoding="utf-8")
        st.write_bundle(bundle, path)
        summary = st.bundle_summary(bundle)
        for label, n in summary["counts"].items():
            self.stdout.write(f"{label:34} {n}")
        self.stdout.write(f"media files {summary['media_files']} ({summary['media_bytes']} bytes)")
        if summary["media_missing"]:
            self.stdout.write(self.style.WARNING(f"referenced but missing: {summary['media_missing']}"))
        if out:
            self.stdout.write(
                f"passwords generated: {len(issued)} (written only to {out}); "
                f"accounts_digest {bundle['credentials']['accounts_digest']}"
            )
        if public_out:
            self.stdout.write(f"public demo accounts: {len(public_vids)} (VID and password only, in {public_out})")
        self.stdout.write(self.style.SUCCESS(f"Wrote {path}"))

    @staticmethod
    def _private_path(value):
        out = Path(value).resolve()
        repo = Path(settings.BASE_DIR).resolve()
        if out == repo or repo in out.parents:
            raise CommandError("The credentials file must be outside the repository.")
        if out.exists():
            raise CommandError(f"{out} already exists; it is the record of an earlier export. Move it first.")
        return out
