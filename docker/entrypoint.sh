#!/bin/sh
# Container entrypoint for web / worker / beat / seed.
#   1. wait until PostgreSQL accepts connections (DATABASE_URL)
#   2. RUN_MIGRATIONS=1 (web service only) -> manage.py migrate --noinput
#   3. exec the container command (gunicorn, celery, manage.py ...)
set -eu

DB_WAIT_TIMEOUT="${DB_WAIT_TIMEOUT:-60}"

if [ -n "${DATABASE_URL:-}" ]; then
    echo "entrypoint: waiting for PostgreSQL (timeout ${DB_WAIT_TIMEOUT}s)..."
    python - <<'PY'
import os
import sys
import time

import psycopg

deadline = time.monotonic() + int(os.environ.get("DB_WAIT_TIMEOUT", "60"))
last_error = None
while time.monotonic() < deadline:
    try:
        psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3).close()
    except psycopg.OperationalError as exc:
        last_error = exc
        time.sleep(1)
    else:
        print("entrypoint: PostgreSQL is ready", flush=True)
        sys.exit(0)
print(f"entrypoint: PostgreSQL not reachable: {type(last_error).__name__}", file=sys.stderr, flush=True)
sys.exit(1)
PY
fi

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "entrypoint: applying migrations..."
    python manage.py migrate --noinput
fi

exec "$@"
