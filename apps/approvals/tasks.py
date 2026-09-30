from celery import shared_task

from apps.core.sweeps import run_sweep

from . import services


@shared_task(name="approvals.sweep_expired")
def sweep_expired():
    return run_sweep("approvals.sweep_expired", services.expire_stale)
