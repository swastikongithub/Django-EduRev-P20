"""
Run Celery Beat as the single scheduler, guarded by a PostgreSQL advisory lock.

Celery Beat must run exactly once: two schedulers send every sweep twice. Platforms make that
easy to get wrong (a scaled service, or the old and new deployment overlapping during a
rolling deploy), so the guarantee lives here rather than in deployment settings alone:

  * the process takes a session-level advisory lock on a dedicated connection before starting
    Beat; a second instance waits (logging) until the first exits, then takes over;
  * a watchdog checks that connection every 30 s. If it is lost, PostgreSQL has already released
    the lock, so this process exits at once and the platform restarts it as a follower;
  * the schedule file is ephemeral (/tmp). Every interval sweep is idempotent and the nightly
    analytics job catches up on any day it missed, so a fresh schedule after a restart loses
    nothing; no persistent volume (which would need a root container on Railway) is required.

    python manage.py run_beat
"""

import logging
import os
import tempfile
import threading
import time

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand

log = logging.getLogger("beat")

# Two-int advisory key: (namespace, id). 20020 is used by booking claims (per resource id), so
# the scheduler uses its own namespace.
BEAT_LOCK = (20021, 1)


def _conninfo() -> str:
    db = settings.DATABASES["default"]
    parts = {
        "dbname": db.get("NAME"),
        "user": db.get("USER"),
        "password": db.get("PASSWORD"),
        "host": db.get("HOST"),
        "port": db.get("PORT"),
    }
    return psycopg.conninfo.make_conninfo(**{k: str(v) for k, v in parts.items() if v})


def try_lead(conn) -> bool:
    """Take the scheduler lock on this connection without waiting. True if we are now the leader."""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s, %s)", BEAT_LOCK)
        return bool(cur.fetchone()[0])


def wait_for_leadership(conninfo: str, *, poll_seconds: float = 15.0, log_every: int = 4):
    """Block until this process holds the lock; returns the connection that holds it."""
    attempts = 0
    while True:
        conn = psycopg.connect(conninfo, autocommit=True, application_name="lpu-reserve-beat")
        if try_lead(conn):
            return conn
        conn.close()
        if attempts % log_every == 0:
            log.info("Another Celery Beat holds the scheduler lock; waiting to take over.")
        attempts += 1
        time.sleep(poll_seconds)


def _watchdog(conn, interval: float = 30.0):
    while True:
        time.sleep(interval)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        except Exception:  # the lock went with the connection: stop scheduling immediately
            log.error("Lost the scheduler-lock connection; exiting so a single Beat can take over.")
            os._exit(1)


class Command(BaseCommand):
    help = "Run Celery Beat as the only scheduler (PostgreSQL advisory-lock leader election)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schedule",
            default=os.path.join(tempfile.gettempdir(), "celerybeat-schedule"),
            help="Ephemeral schedule file.",
        )
        parser.add_argument("--loglevel", default="INFO")

    def handle(self, *args, **opts):
        from config.celery import app

        conn = wait_for_leadership(_conninfo())
        log.info("Scheduler lock acquired; this process is the only Celery Beat.")
        threading.Thread(target=_watchdog, args=(conn,), daemon=True, name="beat-lock-watchdog").start()
        app.Beat(loglevel=opts["loglevel"], schedule=opts["schedule"]).run()
