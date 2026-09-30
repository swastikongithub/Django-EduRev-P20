from celery import shared_task

from apps.core.sweeps import run_sweep

from . import services


@shared_task(name="checkins.sweep_no_shows")
def sweep_no_shows():
    return len(run_sweep("checkins.sweep_no_shows", services.sweep_no_shows))


@shared_task(name="checkins.sweep_completed")
def sweep_completed():
    return run_sweep("checkins.sweep_completed", services.sweep_completed)


@shared_task(name="checkins.sweep_restrictions")
def sweep_restrictions():
    return run_sweep("checkins.sweep_restrictions", services.sweep_restrictions)
