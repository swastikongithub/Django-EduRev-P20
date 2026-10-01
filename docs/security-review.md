# Security review

An adversarial review of LPU Reserve against the CES security baseline (§1.4) and the OWASP
Top 10. Every exploitable finding got an executable proof in `tests/test_security.py`, first
committed as a strict `xfail` asserting the secure behaviour. The fix removed the marker, so
each proof is now a regression test that fails if the finding returns.

**Status: all 14 findings are closed.** No `xfail` markers remain in the security suite.

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

## Residual risk and follow-ups

Tracked in [known-issues.md](known-issues.md):

- The OWASP ZAP baseline scan is not yet part of CI (CES §1.5).
- An approval request whose only eligible approver is the requester waits for a campus-wide
  approver; there is no automatic re-routing.
- Rotating `DJANGO_SECRET_KEY` makes stored TOTP secrets undecryptable; the runbook describes
  re-enrolment.

## Running the suite

```bash
pytest tests/test_security.py tests/test_malformed_input.py -q
```
