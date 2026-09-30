"""Run a sweep and record it in SweepRun so operators can see background work happening."""

import logging

from django.utils import timezone

from .models import SweepRun

log = logging.getLogger("sweeps")


def run_sweep(task_name: str, fn, *args, **kwargs):
    run = SweepRun.objects.create(task=task_name)
    try:
        result = fn(*args, **kwargs)
        affected = len(result) if isinstance(result, (list, tuple, set)) else int(result or 0)
        run.affected = affected
        run.ok = True
        return result
    except Exception as exc:
        run.ok = False
        run.detail = {"error": repr(exc)[:500]}
        log.exception("sweep %s failed", task_name)
        raise
    finally:
        run.finished_at = timezone.now()
        run.save(update_fields=["affected", "ok", "detail", "finished_at"])
