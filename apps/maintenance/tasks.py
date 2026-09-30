from celery import shared_task

from apps.core.sweeps import run_sweep

from . import services


@shared_task(name="maintenance.sweep_windows")
def sweep_windows():
    return run_sweep("maintenance.sweep_windows", services.sweep_windows)
