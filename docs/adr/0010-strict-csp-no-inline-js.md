# 0010. Strict Content-Security-Policy, no inline JavaScript

- Status: accepted
- Related: CES §1.4 (OWASP Top 10); [design-system.md](../design-system.md#rules)

## Context

The application renders user-supplied text (booking titles, notes, resource descriptions,
breakdown reports, approval comments) on pages seen by staff with broad permissions. A stored
XSS would let a student act as a facility manager. Django auto-escaping is the first defence;
a Content-Security-Policy that forbids inline script is the second.

## Decision

`apps/core/middleware.SecurityHeadersMiddleware` sets, on every response except the Swagger UI
and Django admin:

```
default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline';
font-src 'self'; script-src 'self'; connect-src 'self'; media-src 'self' blob:;
frame-ancestors 'none'; base-uri 'self'; form-action 'self'
```

plus `Permissions-Policy: camera=(self), geolocation=(), microphone=()` (camera for the QR
scanner) and `Cross-Origin-Opener-Policy: same-origin`.

- No inline `<script>` blocks and no `on*=` handler attributes in templates. Behaviour lives in
  `static/js/*.js` and binds to `data-*` attributes.
- htmx and the QR decoder (`jsQR`) are vendored under `static/vendor/`; no third-party script
  CDNs.
- htmx runs with `allowEval: false` (`<meta name="htmx-config">` in `base.html`).

## Consequences

- An injected `<script>` or event handler does not execute even if escaping were bypassed.
- Inline styles remain allowed (`'unsafe-inline'` for `style-src`) because templates set
  computed widths (meters, board positions); CSS injection is a lower risk but not zero.
- The axe-core accessibility tests must bypass CSP to inject the audit script
  (`tests/e2e/test_accessibility.py`), which is confined to that module.
- Swagger UI at `/api/v1/docs/` is excluded because it loads inline script; it requires
  sign-in.
- No third-party origin remains. *Update (Phase 3):* the fonts were loaded from Google Fonts
  until the OWASP ZAP baseline flagged the stylesheet for lacking Subresource Integrity, which
  Google's per-browser CSS cannot carry. They are now self-hosted under `static/fonts`.
- The `'unsafe-inline'` style allowance is the one Medium alert the ZAP baseline accepts, with
  this reasoning, in `.zap/accepted.tsv` ([ci.md](../ci.md#owasp-zap-baseline)).

## Alternatives considered

- **Nonce-based CSP allowing inline script.** Rejected: needs a nonce per response in every
  template and still tempts inline code.
- **No CSP, rely on escaping.** Rejected: one mistake (`|safe`, `format_html` misuse) would be
  exploitable.
