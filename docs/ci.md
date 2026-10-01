# Continuous integration and QA gates

Every change is checked by `.github/workflows/ci.yml` before it can reach `main`. This page
lists what each job enforces, when the jobs run, the artifacts they keep, and how to run the
same gates on a laptop.

## When CI runs

| Event | Runs |
|---|---|
| Push to `main` | All jobs, then the deploy placeholder |
| Pull request into `main` | All jobs |
| Push to a development branch listed under `on.push.branches` (during Phase 3: `feat/phase3-ci-qa`) | All jobs |
| Manual (`workflow_dispatch`) | All jobs |

A newer push to the same pull request or branch cancels the run already in progress.

## Jobs and gates

| Job | Gate | Fails when |
|---|---|---|
| **Lint (ruff)** | `ruff check`, `ruff format --check` | Any lint error or unformatted file |
| **Django checks + tests** | `manage.py check --fail-level WARNING` | Any system-check warning |
| | `check --deploy --fail-level WARNING` with production-like settings (random 64-character key, `SECURE_SSL_REDIRECT=1`) | Any deployment warning. `security.W021` (HSTS preload) is silenced only while `SECURE_HSTS_PRELOAD` is off; see [environment.md](environment.md) |
| | `makemigrations --check --dry-run`, `migrate` | A model change without a migration, or a migration that does not apply |
| | `collectstatic` with the production manifest storage | A missing or unresolvable static reference |
| | OpenAPI drift: a fresh `spectacular --validate --fail-on-warn` must equal `docs/openapi.yaml` | The committed API specification is stale, or the schema has warnings |
| | `pytest -m "not e2e"` with `--cov-fail-under=75` | Any failing test, or statement coverage of `apps/` below 75% |
| **Browser journeys + accessibility** | `pytest -m e2e` (Playwright + Chromium) | Any journey fails, or axe-core finds a *serious* or *critical* WCAG 2.2 AA violation on a student page in light or dark theme |
| **Security** | `pip-audit -r requirements.txt` | Any known vulnerability in a runtime dependency |
| | gitleaks over the full history | A committed secret |
| **Docker image** | Build the production image; validate `docker-compose.yml`; start the production-like stack; `scripts/ci/smoke.sh` | The image does not build or boot, or any smoke check fails (list below) |
| **OWASP ZAP baseline** | Passive scan of the running stack; `scripts/ci/zap_gate.py` | Any High alert, or a Medium alert not accepted with a reason (see [ZAP baseline](#owasp-zap-baseline)) |

The concurrency proofs (500 simultaneous attempts on one slot, and the lockout race) run in the
tests job against PostgreSQL with `max_connections=700`.

### Production smoke test

`scripts/ci/stack.sh up` starts the built image as deployed: gunicorn, `DEBUG=0`,
`DEMO_MODE=0`, a random secret key, PostgreSQL 16, Redis, migrations on start-up, and
`SECURE_SSL_REDIRECT=1` behind a simulated TLS proxy (clients send `X-Forwarded-Proto: https`).
`scripts/ci/smoke.sh` then checks, over HTTP:

- `/health/` and `/ready/` answer 200 (database and Redis reachable);
- plain HTTP is redirected to HTTPS;
- the sign-in page carries CSP (`script-src 'self'`), `X-Frame-Options: DENY`, `nosniff`, HSTS,
  `Referrer-Policy` and `Cache-Control: no-store`, and its CSRF cookie is `Secure`;
- static files are served by WhiteNoise under manifest-hashed names with immutable caching;
- the API and its live schema refuse anonymous callers;
- `/django-admin/login/` is the product sign-in (lockout and MFA apply);
- the container runs as a non-root user and `manage.py check --deploy` reports no warnings.

## Artifacts

| Artifact | Contents | Kept |
|---|---|---|
| `test-reports` | `coverage.xml`, JUnit XML of the test job | 14 days |
| `e2e-reports` | JUnit XML; Playwright traces and screenshots of failed journeys | 14 days |
| `zap-reports` | `zap-public.*` and `zap-student.*` reports (HTML, JSON, Markdown) | 30 days |

Open a Playwright trace with `python -m playwright show-trace <trace.zip>`.

## OWASP ZAP baseline

CES §1.5 asks for an OWASP ZAP baseline scan, clean at handover.

**What it does.** `scripts/ci/zap_baseline.sh` runs ZAP's `zap-baseline.py` (image
`ghcr.io/zaproxy/zaproxy:stable`) against the production-like stack above, seeded with the demo
campus. ZAP spiders the site for three minutes and **passively** inspects every response:
security headers, cookie flags, caching of sensitive pages, information leaks, CSP, mixed
content, cross-domain settings. Two passes:

1. **public**: what anyone can reach (sign-in, admin sign-in, probes, static files, API refusals);
2. **student**: the student-facing pages, through a real signed-in student session.

Every request carries `X-Forwarded-Proto: https`, so the app answers as it does behind the
production TLS proxy (HSTS, Secure cookies). Form posting is turned off; the scan never changes
data, and every state change in the app is a POST.

**Policy** (`scripts/ci/zap_gate.py`):

- a **High** alert always fails the build and cannot be accepted;
- a **Medium** alert fails unless its plugin id is listed in `.zap/accepted.tsv` with a written
  reason; entries that no longer occur are reported as stale;
- **Low** and **Informational** alerts are listed in the job summary and the reports.

**Accepted Medium alerts**

| Plugin | Alert | Why it is accepted |
|---|---|---|
| 10055 | CSP: `style-src 'unsafe-inline'` | 83 inline `style` attributes in 31 templates carry computed values (bar widths, grid rows). CSP cannot allow style attributes with nonces, and hashes are impossible for dynamic values. Script stays `script-src 'self'` with no inline script, and all output is autoescaped, so the residual risk is CSS injection only ([ADR 0010](adr/0010-strict-csp-no-inline-js.md)) |

**Findings fixed because of the scan (Phase 3)**

| Plugin | Alert | Fix |
|---|---|---|
| 10098 | Cross-Domain Misconfiguration (`Access-Control-Allow-Origin: *` on static files) | `WHITENOISE_ALLOW_ALL_ORIGINS = False`; no other origin uses our static files |
| 90003 | Sub Resource Integrity attribute missing (Google Fonts stylesheet) | Fonts are self-hosted (`static/fonts`, SIL OFL 1.1); no third-party origin remains in the CSP |

**Limitations**, stated plainly:

- It is a *baseline* (passive) scan. It sends no attack payloads; injection, access-control
  and business-logic testing are covered by `tests/test_security.py`,
  `tests/test_malformed_input.py` and the API authorisation tests, not by ZAP.
- The spider reaches pages through links. Staff console pages are not scanned (no staff
  session is given to ZAP, because a privileged session would need MFA automation).
- TLS itself is not scanned: the stack terminates no TLS (the proxy is simulated). Certificate
  and protocol configuration belong to the hosting platform (Phase 6).
- It scans the demo dataset, not production data.

## Running the gates locally

```bash
make lint                                      # ruff
make check                                     # system and migration checks
pytest -m "not e2e"                            # tests (PostgreSQL from scripts/devdb.sh)
pytest -m e2e                                  # browser journeys and axe (python -m playwright install chromium)

docker build -t lpu-reserve:ci .               # the production image
scripts/ci/stack.sh up                         # production-like stack on 127.0.0.1:8000
scripts/ci/smoke.sh
scripts/ci/stack.sh seed
OUT=zap-out scripts/ci/zap_baseline.sh         # ZAP_IMAGE=zaproxy/zap-stable to pull from Docker Hub instead
scripts/ci/stack.sh down
```

`scripts/ci/stack.sh` also serves the [load test](../loadtest/README.md) with
`EXTRA_WEB_ENV="TRUSTED_PROXY_HOPS=1"`.
