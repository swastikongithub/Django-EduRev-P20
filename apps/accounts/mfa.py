"""
TOTP multi-factor authentication for privileged roles (CES §1.1).

The shared secret is encrypted at rest with a key derived from DJANGO_SECRET_KEY
(HKDF-free SHA-256 derivation is adequate here: the secret key is already high-entropy).
Rotating DJANGO_SECRET_KEY therefore requires re-enrolment — documented in the runbook.
"""

import base64
import hashlib

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

ISSUER = "LPU Reserve"


def _fernet() -> Fernet:
    key = hashlib.sha256((settings.SECRET_KEY + ":mfa").encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(user, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=user.vid or user.username, issuer_name=ISSUER)


def verify(secret: str | None, code: str) -> bool:
    code = (code or "").replace(" ", "")
    if not secret or not code.isdigit() or len(code) != 6:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def required_for(user) -> bool:
    return settings.MFA_ENFORCED and (user.role in settings.MFA_REQUIRED_ROLES or user.is_superuser)
