"""Provider (kitchen) profile and the admin approval workflow."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import today_ist, utcnow
from app.errors import DomainError
from app.models import Provider, ProviderMember, Reservation, User
from app.models.enums import ProviderStatus
from app.schemas.auth import KitchenFields
from app.services import audit
from app.services.reservations import cancel_open_reservations

# Changing any of these on an approved kitchen sends it back for re-verification.
_VERIFIED_FIELDS = ("name", "fssai_number", "fssai_kind", "fssai_valid_until", "address_line", "pincode", "city")


def provider_for_user(db: Session, user: User) -> Provider | None:
    return db.scalar(select(Provider).join(ProviderMember).where(ProviderMember.user_id == user.id))


def update_profile(db: Session, user: User, provider: Provider, data: KitchenFields) -> Provider:
    changes = data.model_dump()
    needs_review = provider.status == ProviderStatus.approved and any(
        getattr(provider, field) != changes[field] for field in _VERIFIED_FIELDS
    )
    for field, value in changes.items():
        setattr(provider, field, value)
    if needs_review:
        provider.status = ProviderStatus.pending
        provider.status_reason = "Name, address or FSSAI details changed. Awaiting re-verification by FoodLoop."
        audit.record(db, user, "provider.resubmitted", "provider", provider.id)
    db.commit()
    return provider


def _get_for_admin(db: Session, provider_id: uuid.UUID) -> Provider:
    provider = db.get(Provider, provider_id, with_for_update=True)
    if provider is None:
        raise DomainError(404, "Provider not found.")
    return provider


def approve(db: Session, admin: User, provider_id: uuid.UUID) -> Provider:
    provider = _get_for_admin(db, provider_id)
    if provider.fssai_valid_until < today_ist():
        raise DomainError(409, "Cannot approve: the FSSAI registration on file has expired.")
    provider.status = ProviderStatus.approved
    provider.status_reason = None
    provider.reviewed_by = admin.id
    provider.reviewed_at = utcnow()
    audit.record(db, admin, "provider.approved", "provider", provider.id, fssai_number=provider.fssai_number)
    db.commit()
    return provider


def reject(db: Session, admin: User, provider_id: uuid.UUID, reason: str) -> Provider:
    provider = _get_for_admin(db, provider_id)
    if provider.status == ProviderStatus.approved:
        raise DomainError(409, "This kitchen is already approved. Suspend it instead.")
    provider.status = ProviderStatus.rejected
    provider.status_reason = reason
    provider.reviewed_by = admin.id
    provider.reviewed_at = utcnow()
    audit.record(db, admin, "provider.rejected", "provider", provider.id, reason=reason)
    db.commit()
    return provider


def suspend(db: Session, admin: User, provider_id: uuid.UUID, reason: str) -> Provider:
    """Suspension takes effect immediately: every listing of this kitchen stops being reservable (the
    reservation statement checks the provider's status at the moment of buying), and open reservations are
    cancelled so no one is handed food from a kitchen under review."""
    provider = _get_for_admin(db, provider_id)
    provider.status = ProviderStatus.suspended
    provider.status_reason = reason
    provider.reviewed_by = admin.id
    provider.reviewed_at = utcnow()
    cancelled = cancel_open_reservations(
        db,
        Reservation.provider_id == provider.id,
        cancelled_by="admin",
        reason=f"This kitchen was paused by FoodLoop: {reason}",
    )
    audit.record(
        db, admin, "provider.suspended", "provider", provider.id, reason=reason, reservations_cancelled=cancelled
    )
    db.commit()
    return provider
