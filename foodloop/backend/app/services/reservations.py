"""Reservations. Two promises are kept here:

1. Never sell more portions than exist (no overselling), even when many people tap "Reserve" at once.
2. Never sell food that is expired, unsafe, paused, removed or from an unapproved kitchen.

Both are checked inside ONE database UPDATE statement at the moment of reserving, so there is no gap
between "checking" and "taking" for another request to sneak into.
"""

import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.clock import today_ist, utcnow
from app.config import get_settings
from app.errors import DomainError
from app.models import Listing, Provider, Reservation, User
from app.models.enums import (
    CancelledBy,
    ListingStatus,
    PaymentStatus,
    ProviderStatus,
    ReservationStatus,
)
from app.models.reservation import IDEMPOTENCY_UNIQUE, ONE_ACTIVE_PER_LISTING, PICKUP_CODE_UNIQUE
from app.schemas.reservation import ReservationCreate
from app.services import audit
from app.services.listings import media_url, provider_can_sell, reservations_close_at

# No 0/O or 1/I/L, so codes are easy to read aloud at a busy counter.
PICKUP_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

_DUPLICATE = DomainError(409, "You already have an active reservation for this meal. See My reservations.")


class _PickupCodeClash(Exception):
    pass


def new_pickup_code() -> str:
    return "".join(secrets.choice(PICKUP_CODE_ALPHABET) for _ in range(6))


def normalise_code(code: str) -> str:
    return code.upper().replace("-", "").replace(" ", "")


# ---------------------------------------------------------------------------------------------------------
# Reserve
# ---------------------------------------------------------------------------------------------------------


def create(db: Session, customer: User, data: ReservationCreate) -> Reservation:
    for _ in range(3):
        try:
            return _try_create(db, customer, data)
        except _PickupCodeClash:
            continue  # a random code collided with an existing one (very rare); try a new code
    raise DomainError(503, "We couldn't create a pickup code. Please try again.")


def _find_by_idempotency_key(db: Session, customer: User, key: uuid.UUID) -> Reservation | None:
    return db.scalar(
        select(Reservation).where(Reservation.customer_id == customer.id, Reservation.idempotency_key == key)
    )


def _replay(existing: Reservation, data: ReservationCreate) -> Reservation:
    if existing.listing_id != data.listing_id or existing.quantity != data.quantity:
        raise DomainError(409, "This request was already used for a different reservation. Please reload.")
    return existing


def _try_create(db: Session, customer: User, data: ReservationCreate) -> Reservation:
    settings = get_settings()
    now = utcnow()

    # 1. The same click arriving twice (double tap, network retry) returns the first result.
    if data.idempotency_key and (existing := _find_by_idempotency_key(db, customer, data.idempotency_key)):
        return _replay(existing, data)

    # 2. Queue up this customer's own parallel requests, so the per-customer limits below stay exact.
    db.execute(select(User.id).where(User.id == customer.id).with_for_update())
    active = db.scalar(
        select(func.count())
        .select_from(Reservation)
        .where(
            Reservation.customer_id == customer.id,
            Reservation.status == ReservationStatus.reserved,
            Reservation.pickup_deadline > now,
        )
    )
    if active >= settings.max_active_reservations_per_customer:
        db.rollback()
        raise DomainError(
            409,
            f"You can hold up to {settings.max_active_reservations_per_customer} active reservations. "
            "Collect or cancel one first.",
        )
    already = db.scalar(
        select(Reservation.id).where(
            Reservation.customer_id == customer.id,
            Reservation.listing_id == data.listing_id,
            Reservation.status == ReservationStatus.reserved,
        )
    )
    if already:
        db.rollback()
        raise _DUPLICATE

    # 3. The guarantee. Portions are taken only if every condition is true at this exact moment.
    #    If two people race for the last portion, PostgreSQL makes the second wait, re-checks
    #    "quantity_available >= quantity" against the new value, and updates nothing.
    taken = db.execute(
        update(Listing)
        .where(
            Listing.id == data.listing_id,
            Listing.provider_id == Provider.id,
            Provider.status == ProviderStatus.approved,
            Provider.fssai_valid_until >= today_ist(),
            Listing.status == ListingStatus.active,
            Listing.pickup_end > now + timedelta(minutes=settings.reservation_cutoff_minutes),
            Listing.safe_until > now,
            Listing.max_per_order >= data.quantity,
            Listing.quantity_available >= data.quantity,
        )
        .values(quantity_available=Listing.quantity_available - data.quantity)
        .returning(Listing.price_paise, Listing.pickup_end, Listing.provider_id)
        .execution_options(synchronize_session=False)
    ).one_or_none()

    if taken is None:
        db.rollback()
        raise _why_unavailable(db, data.listing_id, data.quantity, now)

    reservation = Reservation(
        pickup_code=new_pickup_code(),
        customer_id=customer.id,
        listing_id=data.listing_id,
        provider_id=taken.provider_id,
        quantity=data.quantity,
        unit_price_paise=taken.price_paise,
        total_paise=taken.price_paise * data.quantity,
        pickup_deadline=taken.pickup_end,
        idempotency_key=data.idempotency_key,
    )
    db.add(reservation)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()  # the rollback also gives the portions back
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == PICKUP_CODE_UNIQUE:
            raise _PickupCodeClash from exc
        if constraint == ONE_ACTIVE_PER_LISTING:
            raise _DUPLICATE from exc
        if constraint == IDEMPOTENCY_UNIQUE and data.idempotency_key:
            existing = _find_by_idempotency_key(db, customer, data.idempotency_key)
            if existing:
                return _replay(existing, data)
        raise
    return reservation


def _why_unavailable(db: Session, listing_id: uuid.UUID, quantity: int, now: datetime) -> DomainError:
    """The UPDATE refused; work out a helpful message (this runs only on the failure path)."""
    listing = db.scalar(select(Listing).options(joinedload(Listing.provider)).where(Listing.id == listing_id))
    if listing is None or listing.status != ListingStatus.active or not provider_can_sell(listing.provider):
        return DomainError(404, "This meal isn't available on FoodLoop.")
    if now >= reservations_close_at(listing) or now >= listing.safe_until:
        return DomainError(409, "Reservations for this meal have closed.")
    if quantity > listing.max_per_order:
        return DomainError(
            422, f"You can reserve at most {listing.max_per_order} of this meal per order.", field="quantity"
        )
    if listing.quantity_available <= 0:
        return DomainError(409, "Sorry, this meal has just sold out.")
    return DomainError(
        409, f"Only {listing.quantity_available} left. Lower the quantity and try again.", field="quantity"
    )


# ---------------------------------------------------------------------------------------------------------
# Cancel and collect
# ---------------------------------------------------------------------------------------------------------


def _return_portions(db: Session, reservation: Reservation) -> None:
    db.execute(
        update(Listing)
        .where(Listing.id == reservation.listing_id)
        .values(
            quantity_available=func.least(Listing.quantity_available + reservation.quantity, Listing.quantity_total)
        )
        .execution_options(synchronize_session=False)
    )


def cancel_by_customer(db: Session, customer: User, reservation_id: uuid.UUID, reason: str) -> Reservation:
    now = utcnow()
    reservation = db.scalar(
        select(Reservation)
        .where(Reservation.id == reservation_id, Reservation.customer_id == customer.id)
        .with_for_update()
    )
    if reservation is None:
        raise DomainError(404, "Reservation not found.")
    if reservation.status != ReservationStatus.reserved:
        raise DomainError(409, f"This reservation is already {reservation.status.value.replace('_', ' ')}.")
    if now >= reservation.pickup_deadline:
        raise DomainError(409, "The pickup window has ended, so this reservation can't be cancelled.")
    reservation.status = ReservationStatus.cancelled
    reservation.cancelled_by = CancelledBy.customer
    reservation.cancel_reason = reason or None
    reservation.cancelled_at = now
    _return_portions(db, reservation)  # someone else can now reserve them
    db.commit()
    return reservation


def cancel_by_provider(
    db: Session, user: User, provider: Provider, reservation_id: uuid.UUID, reason: str
) -> Reservation:
    """For when the food can't be handed over (spoiled, dropped, ran out). Portions are NOT put back on sale."""
    reservation = db.scalar(
        select(Reservation)
        .where(Reservation.id == reservation_id, Reservation.provider_id == provider.id)
        .with_for_update()
    )
    if reservation is None:
        raise DomainError(404, "Reservation not found.")
    if reservation.status != ReservationStatus.reserved:
        raise DomainError(409, f"This reservation is already {reservation.status.value.replace('_', ' ')}.")
    reservation.status = ReservationStatus.cancelled
    reservation.cancelled_by = CancelledBy.provider
    reservation.cancel_reason = reason
    reservation.cancelled_at = utcnow()
    audit.record(db, user, "reservation.cancelled_by_provider", "reservation", reservation.id, reason=reason)
    db.commit()
    return reservation


def collect(db: Session, user: User, provider: Provider, pickup_code: str) -> Reservation:
    """The customer shows their code at the counter; staff type it in to hand over the food."""
    code = normalise_code(pickup_code)
    reservation = db.scalar(
        select(Reservation)
        .options(joinedload(Reservation.listing))
        .where(Reservation.provider_id == provider.id, Reservation.pickup_code == code)
        .with_for_update(of=Reservation)
    )
    if reservation is None:
        raise DomainError(404, "No reservation with that pickup code at your kitchen.", field="pickup_code")
    if reservation.status != ReservationStatus.reserved:
        raise DomainError(
            409, f"This reservation is already {reservation.status.value.replace('_', ' ')}.", field="pickup_code"
        )
    if utcnow() > reservation.listing.safe_until:
        raise DomainError(409, "This food is past its eat-by time. Please don't hand it over.", field="pickup_code")
    reservation.status = ReservationStatus.collected
    reservation.collected_at = utcnow()
    reservation.collected_by = user.id
    reservation.payment_status = PaymentStatus.paid  # pay-at-pickup: paid at the counter
    db.commit()
    return reservation


def cancel_open_reservations(db: Session, condition: ColumnElement[bool], *, cancelled_by: str, reason: str) -> int:
    """Cancel every still-open reservation matching `condition` (used when a listing is removed or a
    kitchen is suspended). The caller commits."""
    result = db.execute(
        update(Reservation)
        .where(condition, Reservation.status == ReservationStatus.reserved)
        .values(
            status=ReservationStatus.cancelled,
            cancelled_by=CancelledBy(cancelled_by),
            cancel_reason=reason,
            cancelled_at=utcnow(),
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


def sweep_no_shows(db: Session) -> int:
    """Mark reservations whose pickup window ended without collection as no-shows.

    Safety never depends on this running: an uncollected reservation already shows as "missed" and
    expired food can't be reserved. This keeps the records tidy for reports.
    """
    result = db.execute(
        update(Reservation)
        .where(Reservation.status == ReservationStatus.reserved, Reservation.pickup_deadline < utcnow())
        .values(status=ReservationStatus.no_show)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount or 0


# ---------------------------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------------------------


def display_status(reservation: Reservation, now: datetime) -> str:
    if reservation.status == ReservationStatus.reserved and now >= reservation.pickup_deadline:
        return "missed"
    return reservation.status.value


def _base_out(reservation: Reservation, now: datetime) -> dict:
    listing = reservation.listing
    return {
        "id": reservation.id,
        "quantity": reservation.quantity,
        "unit_price_paise": reservation.unit_price_paise,
        "total_paise": reservation.total_paise,
        "status": reservation.status,
        "display_status": display_status(reservation, now),
        "pickup_deadline": reservation.pickup_deadline,
        "payment_method": reservation.payment_method,
        "payment_status": reservation.payment_status,
        "cancelled_by": reservation.cancelled_by,
        "cancel_reason": reservation.cancel_reason,
        "created_at": reservation.created_at,
        "collected_at": reservation.collected_at,
        "cancelled_at": reservation.cancelled_at,
        "listing": {
            "id": listing.id,
            "title": listing.title,
            "image_url": media_url(listing.image_path),
            "meal_type": listing.meal_type,
            "diet": listing.diet,
            "pickup_start": listing.pickup_start,
            "pickup_end": listing.pickup_end,
            "safe_until": listing.safe_until,
        },
    }


def customer_out(reservation: Reservation, now: datetime) -> dict:
    provider = reservation.provider
    listing = reservation.listing
    return {
        **_base_out(reservation, now),
        "pickup_code": reservation.pickup_code,
        "can_cancel": reservation.status == ReservationStatus.reserved and now < reservation.pickup_deadline,
        "provider": {
            "id": provider.id,
            "name": provider.name,
            "address_line": provider.address_line,
            "area": provider.area,
            "city": provider.city,
            "contact_phone": provider.contact_phone,
            "pickup_instructions": listing.pickup_instructions or provider.pickup_instructions,
            "is_sample": provider.is_sample,
        },
    }


def provider_out(reservation: Reservation, now: datetime) -> dict:
    return {**_base_out(reservation, now), "customer_name": reservation.customer.full_name}


def for_customer(db: Session, customer: User) -> list[Reservation]:
    return list(
        db.scalars(
            select(Reservation)
            .options(joinedload(Reservation.listing), joinedload(Reservation.provider))
            .where(Reservation.customer_id == customer.id)
            .order_by(Reservation.created_at.desc())
            .limit(100)
        ).all()
    )


def get_for_customer(db: Session, customer: User, reservation_id: uuid.UUID) -> Reservation:
    reservation = db.scalar(
        select(Reservation)
        .options(joinedload(Reservation.listing), joinedload(Reservation.provider))
        .where(Reservation.id == reservation_id, Reservation.customer_id == customer.id)
    )
    if reservation is None:
        raise DomainError(404, "Reservation not found.")
    return reservation


def for_provider(db: Session, provider: Provider, scope: str) -> list[Reservation]:
    now = utcnow()
    stmt = (
        select(Reservation)
        .options(joinedload(Reservation.listing), joinedload(Reservation.customer))
        .where(Reservation.provider_id == provider.id)
    )
    if scope == "open":
        stmt = stmt.where(Reservation.status == ReservationStatus.reserved, Reservation.pickup_deadline > now)
        stmt = stmt.order_by(Reservation.pickup_deadline.asc())
    else:
        stmt = stmt.order_by(Reservation.created_at.desc()).limit(200)
    return list(db.scalars(stmt).all())
