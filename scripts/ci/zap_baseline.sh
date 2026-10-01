#!/usr/bin/env bash
# OWASP ZAP baseline scan of a running production-like stack (scripts/ci/stack.sh up + seed).
#
# The baseline is a *passive* scan: ZAP spiders the site and inspects every response for
# problems (headers, cookies, information leaks, caching, CSP...). It sends no attack payloads.
# Two passes in one run: the public surface, and the student-facing pages through a real
# signed-in student session. Every request carries "X-Forwarded-Proto: https" so the app answers
# as it does behind the production TLS proxy. Form posting is disabled: the scan never changes
# data (every state change in the app is a POST anyway).
#
# Writes zap-<pass>.{html,json,md} to $OUT for each pass, then scripts/ci/zap_gate.py decides pass/fail:
# any High alert fails; a Medium fails unless it is accepted, with a reason, in .zap/accepted.tsv.
set -euo pipefail

ZAP_IMAGE="${ZAP_IMAGE:-ghcr.io/zaproxy/zaproxy:stable}"
NET="${NET:-lpr-ci}"
OUT="${OUT:-zap-out}"
TARGET="${TARGET:-http://web:8000/}"
SPIDER_MINUTES="${SPIDER_MINUTES:-3}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

mkdir -p "$OUT"
chmod 777 "$OUT" # the ZAP container runs as its own non-root user

replace() { # n, description, header, value
    printf -- '-config replacer.full_list(%s).description=%s ' "$1" "$2"
    printf -- '-config replacer.full_list(%s).enabled=true ' "$1"
    printf -- '-config replacer.full_list(%s).matchtype=REQ_HEADER ' "$1"
    printf -- '-config replacer.full_list(%s).matchstr=%s ' "$1" "$3"
    printf -- '-config replacer.full_list(%s).regex=false ' "$1"
    printf -- '-config replacer.full_list(%s).replacement=%s ' "$1" "$4"
}
no_forms="-config spider.postform=false -config spider.processform=false"

scan() { # name, extra zap options
    local name="$1" options="$2" code
    echo "zap: pass '$name'"
    set +e
    docker run --rm --network "$NET" -v "$(cd "$OUT" && pwd):/zap/wrk:rw" "$ZAP_IMAGE" \
        zap-baseline.py -t "$TARGET" -m "$SPIDER_MINUTES" -I \
        -r "zap-$name.html" -J "zap-$name.json" -w "zap-$name.md" -z "$options"
    code=$?
    set -e
    # zap-baseline.py: 0 clean, 2 warnings (judged by the gate), 1 fail, 3 scanner error.
    if [[ "$code" == 3 || ! -s "$OUT/zap-$name.json" ]]; then
        echo "zap: pass '$name' did not complete (exit $code)" >&2
        return 1
    fi
}

# Pass 1: what anyone on the internet sees (sign-in, admin sign-in, probes, static, API refusals).
scan public "$(replace 0 tls-proxy X-Forwarded-Proto https)$no_forms"

# Pass 2: the student-facing pages, through a signed-in student session.
session="$("$HERE/stack.sh" session student | tail -1)"
[[ -n "$session" ]] || { echo "zap: could not create a student session" >&2; exit 1; }
scan student "$(replace 0 tls-proxy X-Forwarded-Proto https)$(replace 1 student-session Cookie "sessionid=$session")$no_forms"

python3 "$HERE/zap_gate.py" "$ROOT/.zap/accepted.tsv" "$OUT/zap-public.json" "$OUT/zap-student.json"
