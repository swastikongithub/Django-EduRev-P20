#!/usr/bin/env bash
# Smoke test of a running production-like stack (scripts/ci/stack.sh up). Every check talks to
# the real container over HTTP the way a client behind the TLS proxy would. Fails on the first
# broken expectation and says which.
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:${PORT:-8000}}"
WEB="${WEB:-lpr-web}"
HTTPS=(-H "X-Forwarded-Proto: https")
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }
ok() { echo "ok   $*"; }

status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

# Probes answer over plain HTTP (platform health checks do not go through TLS).
[[ "$(status "$BASE/health/")" == 200 ]] || fail "/health/ is not 200"
ok "/health/ 200 (liveness, no database)"
[[ "$(status "$BASE/ready/")" == 200 ]] || fail "/ready/ is not 200 (database or Redis down?)"
ok "/ready/ 200 (database and Redis reachable)"

# Plain HTTP to a page is redirected to HTTPS (SECURE_SSL_REDIRECT).
code="$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$BASE/login/")"
[[ "$code" == 301\ https://* ]] || fail "plain HTTP /login/ should 301 to https, got: $code"
ok "plain HTTP is redirected to HTTPS"

# The sign-in page over "HTTPS", with production headers and cookies.
curl -s -D "$TMP/h" -o "$TMP/login.html" "${HTTPS[@]}" "$BASE/login/"
head -1 "$TMP/h" | grep -q " 200" || fail "/login/ over HTTPS is not 200: $(head -1 "$TMP/h")"
header() { grep -i "^$1:" "$TMP/h" | head -1 | cut -d: -f2- | tr -d '\r' | sed 's/^ //'; }
[[ "$(header Content-Security-Policy)" == *"script-src 'self'"* ]] || fail "CSP missing or allows inline script"
[[ "$(header X-Frame-Options)" == DENY ]] || fail "X-Frame-Options is not DENY"
[[ "$(header X-Content-Type-Options)" == nosniff ]] || fail "X-Content-Type-Options is not nosniff"
[[ "$(header Strict-Transport-Security)" == *max-age=* ]] || fail "HSTS header missing over HTTPS"
[[ -n "$(header Referrer-Policy)" ]] || fail "Referrer-Policy missing"
[[ "$(header Cache-Control)" == *no-store* ]] || fail "sign-in page should be no-store"
csrf_cookie="$(grep -i '^set-cookie: csrftoken=' "$TMP/h")"
grep -qi 'secure' <<<"$csrf_cookie" || fail "CSRF cookie is not Secure"
grep -qi 'httponly' <<<"$csrf_cookie" || fail "CSRF cookie is not HttpOnly"
ok "/login/ 200 with CSP, X-Frame-Options, nosniff, HSTS, Referrer-Policy, no-store, Secure HttpOnly CSRF cookie"

# Static files: hashed names from the manifest, served by WhiteNoise with long caching.
css="$(grep -oE '/static/css/app\.[0-9a-f]{12}\.css' "$TMP/login.html" | head -1)"
[[ -n "$css" ]] || fail "login page does not reference a hashed app.css (manifest storage not active?)"
curl -s -D "$TMP/sh" -o /dev/null "${HTTPS[@]}" "$BASE$css"
head -1 "$TMP/sh" | grep -q " 200" || fail "$css is not served"
grep -qi '^cache-control:.*max-age=315360000' "$TMP/sh" || fail "$css is not cached long-term"
ok "static $css served with immutable caching"

# The API and its live schema refuse anonymous callers.
for path in /api/v1/resources/ /api/v1/bookings/ /api/v1/schema/; do
    code="$(status "${HTTPS[@]}" "$BASE$path")"
    [[ "$code" == 401 || "$code" == 403 ]] || fail "$path answered $code to an anonymous caller"
done
ok "API and schema refuse anonymous callers"

# Django admin signs in through the product's view (lockout, MFA).
grep -q 'id_username' <(curl -s "${HTTPS[@]}" "$BASE/django-admin/login/") || fail "/django-admin/login/ is not the product sign-in"
ok "/django-admin/login/ is the product sign-in"

# The container runs as a non-root user and passes Django's deployment checks.
[[ "$(docker exec "$WEB" id -u)" != 0 ]] || fail "container runs as root"
ok "container runs as uid $(docker exec "$WEB" id -u)"
docker exec "$WEB" python manage.py check --deploy --fail-level WARNING
ok "manage.py check --deploy: no warnings"

# Uploaded photos persist outside the container: write, fetch through the pre-signed URL a
# browser would get, delete.
docker exec "$WEB" python manage.py verify_storage | grep -q "via pre-signed URL" || fail "media storage round trip"
ok "media storage: S3 bucket, pre-signed read"

# Mail leaves the app over SMTP and arrives at the relay.
docker exec "$WEB" python manage.py sendtestemail smoke@example.test >/dev/null
docker exec "$WEB" python -c '
import json, sys, time, urllib.request
for _ in range(20):
    msgs = json.load(urllib.request.urlopen("http://mail:8025/api/v1/messages"))["messages"]
    if any(t["Address"] == "smoke@example.test" for m in msgs for t in m["To"]):
        sys.exit(0)
    time.sleep(0.5)
sys.exit(1)' || fail "test email did not reach the SMTP relay"
ok "email: delivered over SMTP"

echo "SMOKE PASS"
