"""
Run the Celery Beat schedule in-process.

Production runs one `celery beat` plus workers (docker-compose). This command is for
environments without Redis (local development, a laptop demo): it executes the same
tasks on the same intervals, so no-shows release, finished sessions close and
reminders go out exactly as they would under Beat.

    python manage.py run_sweeps            # run every sweep once, now
    python manage.py run_sweeps --loop     # keep running them on their schedule (Ctrl+C to stop)
"""

import time

from celery.schedules import crontab
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Run the Celery Beat sweeps in-process (for setups without a broker)."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep running on each task's interval.")
        parser.add_argument("--tick", type=int, default=20, help="Seconds between schedule checks in --loop mode.")

    def handle(self, *args, **opts):
        from config.celery import app

        app.loader.import_default_modules()
        schedule = settings.CELERY_BEAT_SCHEDULE
        last_run: dict[str, float] = {}

        def due(name, entry, now_ts):
            sched = entry["schedule"]
            if isinstance(sched, crontab):
                # Nightly jobs: run once at start-up, then when the crontab says so.
                if name not in last_run:
                    return True
                return sched.is_due(timezone.localtime() - timezone.timedelta(seconds=now_ts - last_run[name])).is_due
            return now_ts - last_run.get(name, 0) >= float(sched)

        def run_once(names):
            for name in names:
                entry = schedule[name]
                task = app.tasks[entry["task"]]
                started = time.time()
                try:
                    result = task.apply().get(propagate=True)
                    self.stdout.write(
                        f"{timezone.localtime():%H:%M:%S}  {entry['task']:<34} -> {result}  "
                        f"({int((time.time() - started) * 1000)} ms)"
                    )
                except Exception as exc:  # keep the loop alive; the SweepRun row records the failure
                    self.stderr.write(f"{entry['task']} failed: {exc!r}")
                last_run[name] = started

        if not opts["loop"]:
            run_once(list(schedule))
            return
        self.stdout.write("Running Beat schedule in-process. Ctrl+C to stop.")
        try:
            while True:
                now_ts = time.time()
                run_once([n for n, e in schedule.items() if due(n, e, now_ts)])
                time.sleep(opts["tick"])
        except KeyboardInterrupt:
            self.stdout.write("Stopped.")
