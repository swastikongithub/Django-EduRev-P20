"""
Counts of the state `export_state` covers, and the availability the scheduling engine computes for
chosen resources, as JSON, to compare two installations line by line:

    python manage.py state_inventory --resources 34-301,LT-1 --days 2026-10-05,2026-10-06 \
        --now 2026-10-03T08:00:00+00:00
"""

import json
from datetime import date, datetime

from django.core.management.base import BaseCommand

from apps.core import state_transfer as st


class Command(BaseCommand):
    help = "Print model counts and computed availability as JSON (read only)."

    def add_arguments(self, parser):
        parser.add_argument("--institution", default="LPU")
        parser.add_argument("--resources", default="", help="Comma-separated resource codes")
        parser.add_argument("--days", default="", help="Comma-separated ISO dates")
        parser.add_argument("--now", default="", help="ISO timestamp the schedule is computed at (default: now)")

    def handle(self, *args, institution, resources, days, now, **opts):
        out = st.inventory(
            institution_code=institution,
            resource_codes=[c for c in resources.split(",") if c],
            days=[date.fromisoformat(d) for d in days.split(",") if d],
            now=datetime.fromisoformat(now) if now else None,
        )
        out["availability_digest"] = {code: st.digest(v) for code, v in out["availability"].items()}
        self.stdout.write(json.dumps(out, indent=1, sort_keys=True))
