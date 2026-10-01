# Security review

An adversarial review of LPU Reserve against the CES security baseline (§1.4) and the OWASP
Top 10. Every exploitable finding got an executable proof in `tests/test_security.py`, first
committed as a strict `xfail` asserting the secure behaviour. The fix removed the marker, so
each proof is now a regression test that fails if the finding returns.

**Status: all 14 findings are closed**, and the Phase 3 re-review's findings are fixed or accepted with a recorded reason. No `xfail` markers remain in the security suite.

## Findings

Severity is the impact if exploited in a production deployment: **High** (account or data
takeover, or harm to other users), **Medium** (a control can be bypassed or weakened),
**Low** (information disclosure or robustness).

| ID | Finding | Severity | Fix | Closed in |
|---|---|---|---|---|
| SEC-01 | `/django-admin/login/` created a full session after a password alone: no TOTP, no lockout, no rate limit | High | `admin.site.login` is the product sign-in view (`accounts.views.admin_login`), so the admin gets lockout, rate limit and MFA. `MFASessionMiddleware` (SEC-12) is a second line of defence | `2b3f25b` |
| SEC-02 | Any signed-in user could cancel everyone's bookings on a resource by filing a "critical" breakdown report | High | A critical report takes a resource out of service only when someone who manages it confirms it (at once for their own report, otherwise from the console). Others' reports alert custodians. `BreakdownReport.confirmed_by/confirmed_at` | `2b3f25b` |
| SEC-04 | An approver could approve their own request; a custodian could forgive their own no-show | Medium | Separation of duties: own requests never reach the approver's queue or `can_decide`; own no-shows and restrictions must be cleared by someone else | `2b3f25b` |
| SEC-05 | With `DEBUG=0` and no `DJANGO_SECRET_KEY`, settings silently used the public dev key (sessions, CSRF, password reset and the MFA encryption key all derived from it) | High | Start-up fails with `ImproperlyConfigured` for a missing, placeholder, short (<32), `django-insecure-*` key, or a public `dev-only-*` key outside `DEMO_MODE` | `2b3f25b` |
| SEC-11 | A TOTP code could be replayed within its 90-second validity window | Medium | Codes are single-use: the accepted time step is stored (`User.mfa_last_step`) and an atomic conditional update refuses it or any earlier step | `1377f16` |
| SEC-12 | A session promoted to a privileged role mid-session never had to pass MFA | High | MFA is a property of the session: `mfa_view` stamps it; `MFASessionMiddleware` ends any session of a user who needs MFA without the stamp (pages: sign in again; API: 401 `mfa_required`) | `1377f16` |
| SEC-13 | Malformed input (out-of-range dates, non-numeric ids) raised unhandled exceptions (HTTP 500) | Low | Bounded parsers in `apps/core/http.py` (`pk_param`, `int_param`, `date_param`) at every site; `tests/test_malformed_input.py` sweeps every page, console screen, API list and console form as five roles | `1377f16` |
| SEC-14 | The OpenAPI schema and Swagger UI were served to anonymous users | Low | `SERVE_PERMISSIONS = IsAuthenticated`; integrators use the published `docs/openapi.yaml` | `1377f16` |
| SEC-03 | Re-entering the correct password reset the failure count, giving unlimited TOTP guesses in batches of four | Medium | The count is cleared only after the second factor succeeds; password and TOTP failures add up to one lockout | Security: close SEC-03, SEC-06 … SEC-10 |
| SEC-06 | Audit-log CSV export wrote user text without formula neutralising (CSV injection) | Medium | `apps/core/exports.spreadsheet_safe` on every CSV export (audit, insights, timetable); the timetable importer strips the guard so exports still round-trip | same |
| SEC-07 | The audit IP came from a client-supplied `X-Forwarded-For`; behind a proxy the rate limiter saw only the proxy's address | Medium | `apps/core/http.client_ip` trusts exactly `TRUSTED_PROXY_HOPS` proxies (default 0: header ignored). The audit log and the rate limiter (`RATELIMIT_IP_META_KEY`) share it | same |
| SEC-08 | Quadratic-time regex in `catalogue.search.parse` on a long run of spaces in `?q=` (CPU denial of service) | Medium | Whitespace collapses and the query is capped at 200 characters before any pattern runs | same |
| SEC-09 | The MFA enrolment page (TOTP secret) and the DPDP data export were cacheable | Medium | `@never_cache` (`no-store`) on every page that shows a secret: sign-in, MFA, profile (feed URL), data export, booking pass, QR landing, `.ics` and the private feed, door QR. Every signed-in response is `Cache-Control: private` | same |
| SEC-10 | The lockout message revealed that an account exists | Low | A locked account gets the same answer as a wrong password, after a password hash of comparable cost | same |

## Controls verified to work (regression guards)

These are pinned by plain tests in the same file and did not need changes: CSRF on forms, the
session-authenticated API and sign-in; state-changing views refuse GET; other people's bookings
are 404 (IDOR) in pages and API; QR pass tokens shown only to the booked person; tenant
isolation across institutions; per-account lockout; MFA gating for privileged roles; demo
sign-in off by default; the append-only audit trigger; image upload validation (type, magic
bytes, size, pixel count, re-encode); output escaping; security headers (CSP without inline
script, `frame-ancestors 'none'`, `nosniff`, referrer and permissions policies).

## Phase 3 re-review

An independent re-review in Phase 3 covered authentication and MFA, lockout and rate limiting,
sessions, CSRF, cookies, CSP and headers, authorisation and IDOR on every view and endpoint,
audit coverage, schema exposure, malformed input, forwarded headers, redirects, uploads and CSV
exports, under production-like settings (`DEBUG=0`, `check --deploy` clean). None of SEC-01 to
SEC-14 had regressed. Each finding was reproduced before it was fixed; each fix has a test.

| ID | Finding | Severity | Resolution | Test |
|---|---|---|---|---|
| QA-01 | Concurrent wrong passwords or TOTP codes raced past the lockout: the failure count was read, incremented in Python and saved, so simultaneous requests overwrote each other (12 concurrent guesses left the count at 1) | Medium | Fixed: the count changes under a row lock in one helper used by both paths | `tests/test_lockout_race.py` (failed 3/3 before the fix) |
| QA-02 | `str.isdigit()` guards accepted characters such as `²` that `int()` rejects: HTTP 500 at 17 sites across pages, console and API | Low | Fixed: `apps.core.http.is_digits` (ASCII digits only) at every site; the malformed-input sweep gained a Unicode-digit variant | `test_malformed_input.py`, `test_superscript_digits_are_not_a_server_error`, `test_api_booking_items_with_superscript_keys_are_a_400` |
| QA-03 | A restock quantity beyond the integer column raised a database error (HTTP 500) | Low | Fixed: bounded to 1..100,000 | `test_restock_rejects_absurd_quantities` |
| QA-04 | Acknowledging and resolving breakdowns, restocking, and downloading the audit log or Insights CSVs (which can name people) left no audit entry | Low | Fixed: `maintenance.acknowledge`, `maintenance.resolve`, `inventory.restock`, `audit.export`, `insights.export` are recorded | `test_acknowledging_and_resolving_a_breakdown_are_audited`, `test_csv_exports_of_the_audit_log_and_insights_are_audited`, `test_restock_rejects_absurd_quantities` |
| QA-05 | The API's anonymous throttle keyed on the raw, client-supplied `X-Forwarded-For` | Info | Fixed: DRF `NUM_PROXIES` follows `TRUSTED_PROXY_HOPS` | `test_api_throttle_counts_proxies_like_the_rest_of_the_app` |
| QA-06 | A password-verified sign-in waited for its TOTP code for the whole 10-hour session | Info | Fixed: it expires after 10 minutes | `test_a_half_finished_mfa_sign_in_expires` |
| QA-07 | `X-Forwarded-Proto` is trusted without a declared proxy | Info | Accepted (SEC-R10): only affects the client's own request; coupling it to `TRUSTED_PROXY_HOPS` would risk redirect loops | — |
| QA-08 | First MFA enrolment trusts whoever completes the first password sign-in | Info | Accepted with mitigation (SEC-R8): enrol at onboarding | — |
| QA-09 | Health probes run before host and HTTPS checks and name the failing dependency class | Info | Accepted by design (SEC-R9) | `tests/test_health.py` |

The OWASP ZAP baseline added in the same phase found two further Medium issues, both fixed
(wildcard CORS on static files; Google Fonts without Subresource Integrity, now self-hosted);
see [ci.md](ci.md#owasp-zap-baseline). The CSRF cookie is now `HttpOnly` as well.

## Residual risk and follow-ups

Tracked in [known-issues.md](known-issues.md#security-and-privacy):

- The ZAP baseline is passive and does not cover staff pages or TLS (OPS-10).
- An approval request whose only eligible approver is the requester waits for a campus-wide
  approver; there is no automatic re-routing (SEC-R5).
- Rotating `DJANGO_SECRET_KEY` used to make stored TOTP secrets undecryptable (SEC-R2, resolved in
  production readiness): old keys now go in `DJANGO_SECRET_KEY_FALLBACKS`, secrets move to the new
  key, and an unreadable secret is reported and audited instead of being counted as wrong codes.

## Running the suite

```bash
pytest tests/test_security.py tests/test_malformed_input.py tests/test_lockout_race.py -q
```
