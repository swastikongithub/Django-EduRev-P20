from datetime import date, timedelta

from celery import shared_task
from django.db.models import Max
from django.utils import timezone

from apps.core.sweeps import run_sweep

from . import services
from .models import UtilisationSnapshot

# How far back an automatic catch-up may reach. Longer gaps are an operator decision
# (`build_snapshots(day)` for a specific day, or analytics.services.backfill).
CATCH_UP_MAX_DAYS = 31


def days_to_build(today: date) -> tuple[date, date]:
    """
    The range the nightly job should (re)build: from the day after the newest snapshot up to
    yesterday, and always at least yesterday. A scheduler restart, a deploy at 01:15 or a missed
    night therefore never leaves a hole in the utilisation history (run_beat keeps no state).
    """
    yesterday = today - timedelta(days=1)
    latest = UtilisationSnapshot.objects.aggregate(d=Max("date"))["d"]
    start = yesterday if latest is None else min(latest + timedelta(days=1), yesterday)
    return max(start, yesterday - timedelta(days=CATCH_UP_MAX_DAYS - 1)), yesterday


@shared_task(name="analytics.build_snapshots")
def build_snapshots(day: str | None = None):
    """
    Nightly (01:15): roll up every complete day not yet snapshotted (normally just yesterday).
    ``day`` (ISO date) rebuilds one specific day by hand; the upsert makes re-running harmless.
    """
    if day:
        return run_sweep("analytics.build_snapshots", services.build_snapshots, date.fromisoformat(day))
    start, end = days_to_build(timezone.localdate())
    return run_sweep("analytics.build_snapshots", services.backfill, start, end)
