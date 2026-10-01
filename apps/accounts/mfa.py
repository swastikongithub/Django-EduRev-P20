"""
TOTP multi-factor authentication for privileged roles (CES §1.1).

The shared secret is encrypted at rest with a key derived from DJANGO_SECRET_KEY
(HKDF-free SHA-256 derivation is adequate here: the secret key is already high-entropy).
Secrets encrypted under a previous key stay readable while that key is listed in
DJANGO_SECRET_KEY_FALLBACKS, and move to the current key at their next sign-in. A secret that no
configured key can read is reported as such (`secret_unreadable`), never as a wrong code: the
person cannot fix it by typing, so it must not count towards their lockout either.

A session counts as MFA-verified only when `mark_verified` has stamped it. The
`MFASessionMiddleware` refuses any session of a user who needs MFA without that stamp,
whatever created it (SEC-01 defence in depth, SEC-12 role elevation). Each accepted code
is single-use: its 30-second time step is recorded and never accepted again (SEC-11).
"""

import base64
import hashlib
import time

import pyotp
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db.models import Q

SESSION_KEY = "mfa_verified"
DEMO_MARKER = "demo"

ISSUER = "LPU Reserve"


def _fernet_for(secret_key: str) -> Fernet:
    key = hashlib.sha256((secret_key + ":mfa").encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _fernet() -> Fernet:
    return _fernet_for(settings.SECRET_KEY)


def _all_fernets() -> MultiFernet:
    """The current key first, then SECRET_KEY_FALLBACKS: old secrets stay readable during rotation."""
    keys = [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]
    return MultiFernet([_fernet_for(k) for k in keys])


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str | None:
    """The secret, or None when no configured key can read it (a key changed without a fallback)."""
    try:
        return _all_fernets().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def under_current_key(token: str) -> bool:
    """True when `token` is encrypted with the current SECRET_KEY (not only with a fallback)."""
    try:
        _fernet().decrypt(token.encode())
    except (InvalidToken, ValueError):
        return False
    return True


def reencrypt_if_needed(user) -> bool:
    """Move a secret readable only through a fallback key onto the current key. True if it moved."""
    from .models import User

    if not user.mfa_secret or under_current_key(user.mfa_secret):
        return False
    secret = decrypt(user.mfa_secret)
    if secret is None:
        return False
    token = encrypt(secret)
    # Only replace the exact ciphertext we read, so a concurrent re-enrolment is never overwritten.
    moved = User.objects.filter(pk=user.pk, mfa_secret=user.mfa_secret).update(mfa_secret=token) == 1
    if moved:
        user.mfa_secret = token
    return moved


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(user, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=user.vid or user.username, issuer_name=ISSUER)


def matched_step(secret: str | None, code: str, *, for_time: float | None = None) -> int | None:
    """The TOTP time step `code` belongs to (current step ± 1 for clock drift), or None."""
    code = (code or "").replace(" ", "")
    if not secret or not code.isascii() or not code.isdigit() or len(code) != 6:
        return None
    totp = pyotp.TOTP(secret)
    now = for_time if for_time is not None else time.time()
    current = int(now // totp.interval)
    for step in (current, current - 1, current + 1):
        if pyotp.utils.strings_equal(code, totp.generate_otp(step)):
            return step
    return None


def verify(secret: str | None, code: str) -> bool:
    return matched_step(secret, code) is not None


def consume_step(user, step: int) -> bool:
    """Record `step` as used. False when it (or a later step) was already used: a replay."""
    from .models import User

    fresh = Q(mfa_last_step__isnull=True) | Q(mfa_last_step__lt=step)
    if User.objects.filter(fresh, pk=user.pk).update(mfa_last_step=step) != 1:
        return False
    user.mfa_last_step = step
    return True


def required_for(user) -> bool:
    return settings.MFA_ENFORCED and (user.role in settings.MFA_REQUIRED_ROLES or user.is_superuser)


def needs_mfa(user) -> bool:
    """Sessions of this user must carry the MFA stamp: required by role, or enrolled voluntarily."""
    return bool(user.mfa_enabled or required_for(user))


def mark_verified(request, user, *, demo: bool = False) -> None:
    """Stamp the (already logged-in) session as having passed the second factor."""
    request.session[SESSION_KEY] = DEMO_MARKER if demo else user.pk


def session_verified(request, user) -> bool:
    stamp = request.session.get(SESSION_KEY)
    if stamp == DEMO_MARKER:
        return bool(settings.DEMO_MODE)  # demo sign-in skips MFA only while DEMO_MODE is on
    return stamp == user.pk
