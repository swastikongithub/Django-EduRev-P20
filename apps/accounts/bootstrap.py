"""
First-run setup: creating the very first administrator of a brand-new installation.

LPU Reserve has no public sign-up. People are added by an administrator (Setup → Users → Add a
person), which leaves a fresh database with nobody able to sign in to add anyone. This module is
the one way out through the product itself, and it exists only while the user table is empty:

* `is_system_bootstrap_required()` is decided by the database alone (no flag, cookie, query
  parameter or form field can turn it on), so it switches itself off the moment any account
  exists, including one made with `manage.py createsuperuser`, which stays the operator fallback.
* `create_first_administrator()` re-checks emptiness inside a transaction that holds a
  SHARE ROW EXCLUSIVE lock on the user table. That lock conflicts with itself and with every
  insert, so two simultaneous set-up requests (or set-up racing createsuperuser) are serialised:
  the second sees the first's account and is refused. Reads are not blocked. The empty check
  outside the lock keeps every request after set-up from taking the lock at all.
* The account gets the Administrator role, and nothing else: not superuser, not Django-admin
  staff, whatever the request contains. Administrators must enrol TOTP at their first sign-in
  (apps.accounts.mfa), so the new account is never signed in here; it signs in normally.
* The creation is audited without the password, its hash or any secret.
"""

from __future__ import annotations

import hmac

from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import IntegrityError, connection, transaction

from apps.audit.services import record
from apps.catalogue.manage_forms import StyledFormMixin
from apps.core.models import default_institution_id

from .models import Role, User

BOOTSTRAP_ROLE = Role.ADMIN


class BootstrapClosed(Exception):
    """An account already exists, so first-run set-up is no longer available."""


def is_system_bootstrap_required() -> bool:
    """True only while the database holds no accounts at all (active or not)."""
    return not User.objects.exists()


def _lock_user_table() -> None:
    """Serialise account inserts for the rest of the current transaction (PostgreSQL)."""
    if connection.vendor != "postgresql":  # pragma: no cover - the project runs on PostgreSQL only
        return
    with connection.cursor() as cursor:
        cursor.execute(f"LOCK TABLE {connection.ops.quote_name(User._meta.db_table)} IN SHARE ROW EXCLUSIVE MODE")


def create_first_administrator(
    *, username: str, email: str, first_name: str, last_name: str, password: str, request=None
) -> User:
    """
    Create the first administrator, or raise BootstrapClosed if any account exists, now or by the
    time the lock is held. `password` must already have passed AUTH_PASSWORD_VALIDATORS.
    """
    if not is_system_bootstrap_required():
        raise BootstrapClosed
    user = User(
        institution_id=default_institution_id(),
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        role=BOOTSTRAP_ROLE,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )
    user.set_password(password)  # hash before taking the lock: hashing is deliberately slow
    try:
        with transaction.atomic():
            _lock_user_table()
            if User.objects.exists():
                raise BootstrapClosed
            user.save()  # post_save puts the account in the Administrator role's group
            record(
                None,
                "auth.bootstrap_admin",
                user,
                after={
                    "username": user.username,
                    "email": user.email,
                    "role": user.role,
                    "is_superuser": False,
                    "is_staff": False,
                    "via": "first-run setup",
                },
                request=request,
            )
    except IntegrityError as exc:  # pragma: no cover - the lock makes this unreachable on PostgreSQL
        raise BootstrapClosed from exc
    return user


def setup_code_required() -> bool:
    return bool(getattr(settings, "BOOTSTRAP_SETUP_CODE", ""))


class BootstrapForm(StyledFormMixin, forms.Form):
    """
    Only what the first administrator needs. There is deliberately no role, staff or superuser
    field: the role is fixed server-side, and extra POST keys are ignored.
    """

    full_name = forms.CharField(label="Full name", max_length=300)
    email = forms.EmailField(help_text="Approval requests and alerts are sent here.")
    username = forms.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()],
        help_text="What you type to sign in. Letters, digits and @ . + - _ only.",
    )
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="At least 10 characters, not a common password and not like your name or email.",
    )
    password2 = forms.CharField(
        label="Repeat the password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    setup_code = forms.CharField(
        label="Setup code",
        required=False,
        strip=True,
        widget=forms.PasswordInput(attrs={"autocomplete": "off"}),
        help_text="The BOOTSTRAP_SETUP_CODE value your deployment was configured with.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if setup_code_required():
            self.fields["setup_code"].required = True
        else:
            del self.fields["setup_code"]
        if not self.is_bound:  # a bound form is styled after validation (StyledFormMixin.full_clean)
            self.style()

    def clean_full_name(self):
        name = " ".join(self.cleaned_data["full_name"].split())
        if not name:
            raise forms.ValidationError("Enter your name.")
        first, _, last = name.rpartition(" ") if " " in name else (name, "", "")
        if len(first) > 150 or len(last) > 150:
            raise forms.ValidationError("That name is too long.")
        self.first_name, self.last_name = first, last
        return name

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(f"Someone already signs in as {username}. Choose another username.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(f"{email} already belongs to another account.")
        return email

    def clean_setup_code(self):
        code = self.cleaned_data.get("setup_code", "")
        if not hmac.compare_digest(code.encode(), settings.BOOTSTRAP_SETUP_CODE.encode()):
            raise forms.ValidationError("That setup code isn't right.")
        return code

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords don't match.")
        elif p1:
            probe = User(
                username=data.get("username", ""),
                first_name=getattr(self, "first_name", ""),
                last_name=getattr(self, "last_name", ""),
                email=data.get("email", ""),
            )
            try:
                password_validation.validate_password(p1, probe)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return data

    def save(self, request=None) -> User:
        d = self.cleaned_data
        return create_first_administrator(
            username=d["username"],
            email=d["email"],
            first_name=self.first_name,
            last_name=self.last_name,
            password=d["password1"],
            request=request,
        )
