from datetime import date, timedelta

from celery import shared_task
from django.utils import timezone

from apps.core.sweeps import run_sweep

from . import services


@shared_task(name="analytics.build_snapshots")
def build_snapshots(day: str | None = None):
    """
    Nightly (01:15): roll up *yesterday*, which is complete by then. ``day`` (ISO date) lets an
    operator rebuild a specific day by hand; the upsert makes re-running harmless.
    """
    target = date.fromisoformat(day) if day else timezone.localdate() - timedelta(days=1)
    return run_sweep("analytics.build_snapshots", services.build_snapshots, target)
