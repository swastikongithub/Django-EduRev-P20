# 0009. TOTP MFA for privileged roles; demo personas behind DEMO_MODE

- Status: accepted
- Related: CES §1.1 ("TOTP MFA for admin roles"), §1.4

## Context

CES requires TOTP multi-factor authentication for administrative roles. University SSO is not
available to the project, so accounts sign in with a password. Demonstrations and reviews also
need quick access to each role without sharing passwords, but a one-click sign-in must never
be reachable in a real deployment.

## Decision

- Roles in `MFA_REQUIRED_ROLES` (default `admin`, `facility_manager`) and superusers must pass
  a TOTP step after a correct password (`accounts.views.mfa_view`). A user who has enrolled
  voluntarily (`mfa_enabled`) is also asked. On first sign-in the user enrols by scanning a
  QR (otpauth URI, issuer "LPU Reserve") and confirming a code.
- The TOTP secret is stored Fernet-encrypted in `User.mfa_secret`, with a key derived from
  `DJANGO_SECRET_KEY` (`apps/accounts/mfa.py`). Codes allow one 30-second step of drift.
- Until the second factor succeeds, the session holds only a pending user id; no
  authenticated session exists. Failed codes count toward the same lockout as passwords, and
  the MFA view is rate limited per IP.
- `MFA_ENFORCED=0` disables the requirement (development only).
- Demo personas (`student`, `faculty`, `custodian`, `hod`, `facility`, `admin`) created by
  `seed_demo` can sign in with one click only when `DEMO_MODE=1`. The endpoint returns 404
  otherwise, the default is off, and persona sign-in skips MFA. Every persona sign-in is
  audited (`auth.demo_login`).

## Consequences

- Rotating `DJANGO_SECRET_KEY` makes stored MFA secrets undecryptable; every enrolled user
  must re-enrol (clear `mfa_enabled` and `mfa_secret`). The runbook documents this.
- There are no recovery codes yet; a user who loses their authenticator needs an
  administrator to reset enrolment in the database (see [known issues](../known-issues.md)).
- Docker compose sets `DEMO_MODE=1` by default for local demos; production must set it to 0.
  `tests/test_pages.py::test_demo_login_is_disabled_unless_demo_mode` guards the default.
- Seeded accounts have unusable passwords unless `DEMO_PASSWORD` is set at seed time.

## Alternatives considered

- **WebAuthn / passkeys.** Stronger, but more client work and not named by CES.
- **Email or SMS one-time codes.** Weaker and needs an SMS provider.
- **MFA for every role.** Rejected for students: friction without matching risk; the CES
  requirement is for admin roles.
- **Separate encryption key variable for MFA.** Would decouple rotation; deferred to keep
  configuration small. Recorded as technical debt.
