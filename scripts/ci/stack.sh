#!/usr/bin/env bash
# A production-like LPU Reserve stack in Docker, for the CI smoke test, the OWASP ZAP baseline
# and load tests. The app runs exactly as deployed: the built image, gunicorn, DEBUG=0,
# DEMO_MODE=0, a random secret key, PostgreSQL 16 and Redis, migrations on start-up, and
# SECURE_SSL_REDIRECT=1 behind a TLS-terminating proxy. Clients play the proxy by sending
# "X-Forwarded-Proto: https" (Django trusts it through SECURE_PROXY_SSL_HEADER), so HSTS,
# Secure cookies and the HTTP->HTTPS redirect all behave as in production.
#
#   scripts/ci/stack.sh up                 start db, redis and web; wait until /ready/ is 200
#   scripts/ci/stack.sh seed               load the demo campus (DEMO_PASSWORD optional)
#   scripts/ci/stack.sh session <user>     print a session id for an existing user (scanners)
#   scripts/ci/stack.sh logs               web container logs
#   scripts/ci/stack.sh down               remove everything
#
# Environment: IMAGE (default lpu-reserve:ci), DB_IMAGE, REDIS_IMAGE, NET (lpr-ci),
# PORT (host port, default 8000), EXTRA_WEB_ENV (space-separated KEY=VALUE pairs).
set -euo pipefail

IMAGE="${IMAGE:-lpu-reserve:ci}"
DB_IMAGE="${DB_IMAGE:-postgres:16-alpine}"
REDIS_IMAGE="${REDIS_IMAGE:-redis:7-alpine}"
NET="${NET:-lpr-ci}"
PORT="${PORT:-8000}"
WEB=lpr-web
DB=lpr-db
REDIS=lpr-redis

wait_for() { # url, seconds
    local url="$1" deadline=$((SECONDS + $2))
    until curl -fs -o /dev/null -H "X-Forwarded-Proto: https" "$url" 2>/dev/null; do
        if ((SECONDS >= deadline)); then
            echo "stack: $url not ready after $2 s" >&2
            docker logs --tail 80 "$WEB" >&2 || true
            return 1
        fi
        sleep 2
    done
}

case "${1:-}" in
up)
    docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null
    docker run -d --name "$DB" --network "$NET" --network-alias db \
        -e POSTGRES_USER=edurev -e POSTGRES_PASSWORD=edurev -e POSTGRES_DB=edurev \
        --shm-size=256m "$DB_IMAGE" -c max_connections=200 >/dev/null
    docker run -d --name "$REDIS" --network "$NET" --network-alias redis \
        "$REDIS_IMAGE" redis-server --save "" --appendonly no >/dev/null
    extra=()
    for kv in ${EXTRA_WEB_ENV:-}; do extra+=(-e "$kv"); done
    docker run -d --name "$WEB" --network "$NET" --network-alias web \
        -p "127.0.0.1:${PORT}:8000" \
        -e DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" \
        -e DEBUG=0 -e DEMO_MODE=0 \
        -e ALLOWED_HOSTS=localhost,127.0.0.1,web \
        -e CSRF_TRUSTED_ORIGINS="https://localhost:${PORT},https://web:8000" \
        -e SITE_URL="https://localhost:${PORT}" \
        -e SECURE_SSL_REDIRECT=1 \
        -e DATABASE_URL=postgres://edurev:edurev@db:5432/edurev \
        -e REDIS_URL=redis://redis:6379/0 -e CELERY_BROKER_URL=redis://redis:6379/1 \
        -e RUN_MIGRATIONS=1 -e LOG_JSON=1 \
        "${extra[@]}" "$IMAGE" >/dev/null
    wait_for "http://127.0.0.1:${PORT}/ready/" 180
    echo "stack: web is ready on http://127.0.0.1:${PORT} (send X-Forwarded-Proto: https)"
    ;;
seed)
    docker exec -e DEMO_PASSWORD="${DEMO_PASSWORD:-}" "$WEB" python manage.py seed_demo
    ;;
session)
    user="${2:?usage: stack.sh session <username>}"
    docker exec -e LPR_USER="$user" "$WEB" python manage.py shell -c '
import os
from django.test import Client
from apps.accounts.models import User
c = Client()
c.force_login(User.objects.get(username=os.environ["LPR_USER"]))
print(c.cookies["sessionid"].value)
'
    ;;
logs)
    docker logs "$WEB"
    ;;
down)
    docker rm -f "$WEB" "$REDIS" "$DB" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
    ;;
*)
    sed -n '2,16p' "$0"
    exit 2
    ;;
esac
