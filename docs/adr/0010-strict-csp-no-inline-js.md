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
default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; media-src 'self' blob:;
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
- Google Fonts is the only third-party origin.

## Alternatives considered

- **Nonce-based CSP allowing inline script.** Rejected: needs a nonce per response in every
  template and still tempts inline code.
- **No CSP, rely on escaping.** Rejected: one mistake (`|safe`, `format_html` misuse) would be
  exploitable.
