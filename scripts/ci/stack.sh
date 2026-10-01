#!/usr/bin/env bash
# A production-like LPU Reserve stack in Docker, for the CI smoke test, the OWASP ZAP baseline
# and load tests. The app runs exactly as deployed: the built image, gunicorn, DEBUG=0,
# DEMO_MODE=0, a random secret key, PostgreSQL 16 and Redis, migrations as a separate step
# before the web process starts (as Railway's pre-deploy command runs them), photos in a
# private S3-compatible bucket (moto), mail over SMTP (Mailpit), and SECURE_SSL_REDIRECT=1
# behind a TLS-terminating proxy. Clients play the proxy by sending
# "X-Forwarded-Proto: https" (Django trusts it through SECURE_PROXY_SSL_HEADER), so HSTS,
# Secure cookies and the HTTP->HTTPS redirect all behave as in production.
#
#   scripts/ci/stack.sh up                 start db, redis, s3, mail and web; wait until /ready/ is 200
#   scripts/ci/stack.sh seed               load the demo campus (DEMO_PASSWORD optional)
#   scripts/ci/stack.sh session <user>     print a session id for an existing user (scanners)
#   scripts/ci/stack.sh logs               web container logs
#   scripts/ci/stack.sh down               remove everything
#
# Environment: IMAGE (default lpu-reserve:ci), DB_IMAGE, REDIS_IMAGE, S3_IMAGE, MAIL_IMAGE, NET (lpr-ci),
# PORT (host port, default 8000), EXTRA_WEB_ENV (space-separated KEY=VALUE pairs).
set -euo pipefail

IMAGE="${IMAGE:-lpu-reserve:ci}"
DB_IMAGE="${DB_IMAGE:-postgres:16-alpine}"
REDIS_IMAGE="${REDIS_IMAGE:-redis:7-alpine}"
S3_IMAGE="${S3_IMAGE:-motoserver/moto:5.1.4}"
MAIL_IMAGE="${MAIL_IMAGE:-axllent/mailpit:v1.27}"
NET="${NET:-lpr-ci}"
PORT="${PORT:-8000}"
WEB=lpr-web
DB=lpr-db
REDIS=lpr-redis
S3=lpr-s3
MAIL=lpr-mail
CREATE_BUCKET='
import os, boto3
boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT_URL"], region_name=os.environ["S3_REGION"],
             aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
             aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"]).create_bucket(Bucket=os.environ["S3_BUCKET"])
'

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
    docker run -d --name "$S3" --network "$NET" --network-alias s3 "$S3_IMAGE" >/dev/null
    docker run -d --name "$MAIL" --network "$NET" --network-alias mail "$MAIL_IMAGE" >/dev/null
    env=(
        -e DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
        -e DEBUG=0 -e DEMO_MODE=0
        -e ALLOWED_HOSTS=localhost,127.0.0.1,web
        -e CSRF_TRUSTED_ORIGINS="https://localhost:${PORT},https://web:8000"
        -e SITE_URL="https://localhost:${PORT}"
        -e SECURE_SSL_REDIRECT=1
        -e DATABASE_URL=postgres://edurev:edurev@db:5432/edurev
        -e REDIS_URL=redis://redis:6379/0 -e CELERY_BROKER_URL=redis://redis:6379/1
        -e USE_S3=1 -e S3_BUCKET=lpr-media -e S3_ENDPOINT_URL=http://s3:5000 -e S3_REGION=us-east-1
        -e S3_ACCESS_KEY_ID=ci-access-key -e S3_SECRET_ACCESS_KEY=ci-secret-key -e S3_ADDRESSING_STYLE=path
        -e EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
        -e EMAIL_HOST=mail -e EMAIL_PORT=1025 -e EMAIL_USE_TLS=0
        -e LOG_JSON=1
    )
    for kv in ${EXTRA_WEB_ENV:-}; do env+=(-e "$kv"); done
    # Railway buckets exist before the app does; the S3 emulator starts empty.
    docker run --rm --network "$NET" "${env[@]}" "$IMAGE" python -c "$CREATE_BUCKET"
    # Pre-deploy step, as on Railway: deployment checks and migrations in a one-off container
    # (docker/predeploy.sh), then start web with
    # RUN_MIGRATIONS unset. The entrypoint waits for PostgreSQL before running either.
    docker run --rm --network "$NET" "${env[@]}" "$IMAGE" sh /app/docker/predeploy.sh >/dev/null
    docker run -d --name "$WEB" --network "$NET" --network-alias web \
        -p "127.0.0.1:${PORT}:8000" "${env[@]}" "$IMAGE" >/dev/null
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
    docker rm -f "$WEB" "$MAIL" "$S3" "$REDIS" "$DB" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
    ;;
*)
    sed -n '2,18p' "$0"
    exit 2
    ;;
esac
