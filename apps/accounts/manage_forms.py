"""
Administrator-created accounts (staff console). There is no public sign-up: people are added by an
administrator, with a role, until university single sign-on exists (INT-1).

The initial password is checked against AUTH_PASSWORD_VALIDATORS and only ever stored hashed; it is
never logged, audited or shown again. Privileged roles still enrol TOTP at their first sign-in
(apps.accounts.mfa), exactly like every other privileged account. Superuser and Django-admin
staff flags cannot be granted here.
"""

from __future__ import annotations

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import transaction

from apps.catalogue.manage_forms import StyledFormMixin

from .models import Department, Role, User


class UserCreateForm(StyledFormMixin, forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    username = forms.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()],
        help_text="What they type to sign in. Letters, digits and @ . + - _ only.",
    )
    email = forms.EmailField(help_text="Booking confirmations and approvals are sent here.")
    vid = forms.CharField(
        label="VID",
        max_length=20,
        required=False,
        help_text="UMS registration or employee number. It can be used to sign in.",
    )
    role = forms.ChoiceField(choices=Role.choices, initial=Role.STUDENT)
    department = forms.ModelChoiceField(queryset=Department.objects.none(), required=False)
    designation = forms.CharField(max_length=120, required=False)
    password1 = forms.CharField(
        label="Initial password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="At least 10 characters, not a common password and not like their name. Share it with them privately.",
    )
    password2 = forms.CharField(
        label="Repeat the password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )

    def __init__(self, *args, institution_id: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.institution_id = institution_id
        self.fields["department"].queryset = Department.objects.filter(institution_id=institution_id).order_by("code")
        if not self.is_bound:  # a bound form is styled after validation (StyledFormMixin.full_clean)
            self.style()

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(f"Someone already signs in as {username}. Choose another username.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(institution_id=self.institution_id, email__iexact=email).exists():
            raise forms.ValidationError(f"{email} already belongs to another account.")
        return email

    def clean_vid(self):
        vid = self.cleaned_data.get("vid", "").strip()
        if vid and User.objects.filter(institution_id=self.institution_id, vid__iexact=vid).exists():
            raise forms.ValidationError(f"VID {vid} already belongs to another account.")
        return vid

    def clean_role(self):
        role = self.cleaned_data["role"]
        if role not in Role.values:
            raise forms.ValidationError("Choose one of the listed roles.")
        return role

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords don't match.")
        elif p1:
            # Validate against the would-be user so similarity to their name and email is caught.
            probe = User(
                username=data.get("username", ""),
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
                email=data.get("email", ""),
            )
            try:
                password_validation.validate_password(p1, probe)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        if data.get("role") == Role.DEPT_HEAD and not data.get("department"):
            self.add_error("department", "A head of department needs a department to head.")
        return data

    def save(self) -> User:
        d = self.cleaned_data
        with transaction.atomic():
            user = User(
                institution_id=self.institution_id,
                username=d["username"],
                email=d["email"],
                first_name=d["first_name"].strip(),
                last_name=(d.get("last_name") or "").strip(),
                vid=d.get("vid", ""),
                role=d["role"],
                department=d.get("department"),
                designation=(d.get("designation") or "").strip(),
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            user.set_password(d["password1"])
            user.save()  # post_save puts them in their role's permission group
        return user
