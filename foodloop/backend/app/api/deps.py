"""Reusable checks ("dependencies") that protect routes. Authorization always happens here, on the
server. Hiding a button in React is only for convenience."""

from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DomainError
from app.models import Provider, User
from app.models.enums import ProviderStatus, UserRole
from app.security.sessions import COOKIE_NAME, user_for_token
from app.services.providers import provider_for_user


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    return user_for_token(db, request.cookies.get(COOKIE_NAME))


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise DomainError(401, "Please log in to continue.")
    return user


def require_customer(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.customer:
        raise DomainError(403, "Only customer accounts can reserve meals.")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.admin:
        raise DomainError(403, "Admins only.")
    return user


@dataclass
class ProviderContext:
    user: User
    provider: Provider


def require_provider_member(user: User = Depends(current_user), db: Session = Depends(get_db)) -> ProviderContext:
    if user.role != UserRole.provider:
        raise DomainError(403, "This area is for registered kitchens.")
    provider = provider_for_user(db, user)
    if provider is None:
        raise DomainError(403, "Your account isn't linked to a kitchen. Contact FoodLoop support.")
    return ProviderContext(user=user, provider=provider)


def require_approved_provider(ctx: ProviderContext = Depends(require_provider_member)) -> ProviderContext:
    if ctx.provider.status != ProviderStatus.approved:
        messages = {
            ProviderStatus.pending: "Your kitchen is waiting for approval. You can add listings once FoodLoop "
            "has verified your FSSAI details.",
            ProviderStatus.rejected: "Your kitchen application was not approved, so you can't list food.",
            ProviderStatus.suspended: "Your kitchen is suspended, so listings are paused. Contact FoodLoop.",
        }
        raise DomainError(403, messages[ctx.provider.status])
    return ctx
