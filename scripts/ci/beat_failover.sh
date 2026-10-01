#!/usr/bin/env bash
# Exactly one Celery Beat, with real containers against the running CI stack: start two
# `run_beat` processes, check that only the first schedules and the second waits, kill the
# first, and check that the second takes over. This is what keeps a scaled or overlapping
# beat service (for example during a Railway redeploy) from sending every sweep twice.
set -euo pipefail

NET="${NET:-lpr-ci}"
IMAGE="${IMAGE:-lpu-reserve:ci}"
fail() { echo "BEAT FAILOVER FAIL: $*" >&2; docker logs lpr-beat-a 2>&1 | tail -20 >&2 || true; cleanup; exit 1; }
cleanup() { docker rm -f lpr-beat-a lpr-beat-b >/dev/null 2>&1 || true; }
trap cleanup EXIT

env=(
    -e DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
    -e DEBUG=0 -e LOG_JSON=0
    -e DATABASE_URL=postgres://edurev:edurev@db:5432/edurev
    -e REDIS_URL=redis://redis:6379/0 -e CELERY_BROKER_URL=redis://redis:6379/1
)
leader() { docker logs "$1" 2>&1 | grep -q "Scheduler lock acquired"; }
waiting() { docker logs "$1" 2>&1 | grep -q "Another Celery Beat holds the scheduler lock"; }
wait_until() { # seconds, command...
    local deadline=$((SECONDS + $1)); shift
    until "$@"; do ((SECONDS < deadline)) || return 1; sleep 1; done
}

docker run -d --name lpr-beat-a --network "$NET" "${env[@]}" "$IMAGE" python manage.py run_beat >/dev/null
wait_until 60 leader lpr-beat-a || fail "first beat never took the lock"
echo "ok   first beat holds the scheduler lock"

docker run -d --name lpr-beat-b --network "$NET" "${env[@]}" "$IMAGE" python manage.py run_beat >/dev/null
wait_until 60 waiting lpr-beat-b || fail "second beat did not report waiting"
leader lpr-beat-b && fail "second beat started scheduling while the first was alive"
echo "ok   second beat waits instead of scheduling"

docker rm -f lpr-beat-a >/dev/null
wait_until 45 leader lpr-beat-b || fail "second beat did not take over after the first died"
echo "ok   second beat took over after the first died"
echo "BEAT FAILOVER PASS"
