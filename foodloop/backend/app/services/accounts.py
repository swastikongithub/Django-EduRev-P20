"""Registration and login."""

import re
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import Provider, ProviderMember, User
from app.models.enums import MemberRole, ProviderStatus, UserRole
from app.schemas.auth import KitchenFields, ProviderRegisterRequest, RegisterRequest
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.services import audit

_EMAIL_TAKEN = DomainError(409, "An account with this email already exists. Try logging in.", field="email")


def _email_exists(db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(User.email == email)) is not None


def register_customer(db: Session, data: RegisterRequest) -> User:
    if _email_exists(db, data.email):
        raise _EMAIL_TAKEN
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        role=UserRole.customer,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # two sign-ups with the same email at the same moment
        db.rollback()
        raise _EMAIL_TAKEN from None
    return user


def unique_slug(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:120] or "kitchen"
    slug = base
    while db.scalar(select(Provider.id).where(Provider.slug == slug)) is not None:
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


def register_provider(db: Session, data: ProviderRegisterRequest) -> tuple[User, Provider]:
    """Create the provider's login and their kitchen in one transaction. The kitchen starts as pending."""
    if _email_exists(db, data.email):
        raise _EMAIL_TAKEN
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        role=UserRole.provider,
    )
    provider = Provider(**kitchen_columns(data.kitchen), slug=unique_slug(db, data.kitchen.name))
    provider.status = ProviderStatus.pending
    db.add_all([user, provider])
    db.flush()
    db.add(ProviderMember(provider_id=provider.id, user_id=user.id, member_role=MemberRole.owner))
    audit.record(db, user, "provider.registered", "provider", provider.id, name=provider.name)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _EMAIL_TAKEN from None
    return user, provider


def kitchen_columns(kitchen: KitchenFields) -> dict:
    return kitchen.model_dump()


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not verify_password(user.password_hash if user else None, password) or user is None:
        raise DomainError(401, "That email and password don't match. Please try again.")
    if not user.is_active:
        raise DomainError(403, "This account has been deactivated. Contact FoodLoop support.")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    return user
