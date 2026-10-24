"""Food listings: food-safety validation, public browsing and provider edits."""

import uuid
from datetime import datetime, timedelta
from typing import Literal, Protocol

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.clock import today_ist, utcnow
from app.config import Settings, get_settings
from app.errors import DomainError
from app.models import Listing, Provider, Reservation, User
from app.models.enums import LABELS, ListingStatus, ProviderStatus, ReservationStatus, Storage
from app.schemas.listing import ListingCreate, ListingInput
from app.services import audit

Sort = Literal["ending_soon", "price_low", "discount", "newest"]
AvailabilityFilter = Literal["available", "pickup_now", "all"]

# Reservations that still "use up" portions of a listing (cancelled ones don't).
TAKEN_STATUSES = (ReservationStatus.reserved, ReservationStatus.collected, ReservationStatus.no_show)


class _FoodTiming(Protocol):
    storage: Storage
    prepared_at: datetime
    pickup_start: datetime
    pickup_end: datetime
    safe_until: datetime
    price_paise: int
    original_price_paise: int
    max_per_order: int
    quantity_total: int


# ---------------------------------------------------------------------------------------------------------
# Computed values: availability is worked out from the clock, never stored.
# ---------------------------------------------------------------------------------------------------------


def media_url(path: str | None) -> str | None:
    return f"/media/{path}" if path else None


def reservations_close_at(listing: Listing, settings: Settings | None = None) -> datetime:
    settings = settings or get_settings()
    return listing.pickup_end - timedelta(minutes=settings.reservation_cutoff_minutes)


def provider_can_sell(provider: Provider) -> bool:
    return provider.status == ProviderStatus.approved and provider.fssai_valid_until >= today_ist()


def availability(listing: Listing, now: datetime) -> str:
    if listing.status != ListingStatus.active:
        return listing.status.value  # draft / paused / removed
    if not provider_can_sell(listing.provider):
        return "unavailable"
    if now >= listing.pickup_end or now >= listing.safe_until:
        return "expired"
    if listing.quantity_available <= 0:
        return "sold_out"
    if now >= reservations_close_at(listing):
        return "closed"
    return "available"


def discount_percent(listing: Listing) -> int:
    return round(100 * (listing.original_price_paise - listing.price_paise) / listing.original_price_paise)


def listing_out(listing: Listing, now: datetime) -> dict:
    provider = listing.provider
    return {
        "id": listing.id,
        "title": listing.title,
        "description": listing.description,
        "meal_type": listing.meal_type,
        "diet": listing.diet,
        "allergens": listing.allergens,
        "allergen_note": listing.allergen_note,
        "image_url": media_url(listing.image_path),
        "image_is_representative": listing.image_is_representative,
        "original_price_paise": listing.original_price_paise,
        "price_paise": listing.price_paise,
        "discount_percent": discount_percent(listing),
        "quantity_total": listing.quantity_total,
        "quantity_available": listing.quantity_available,
        "max_per_order": listing.max_per_order,
        "storage": listing.storage,
        "prepared_at": listing.prepared_at,
        "pickup_start": listing.pickup_start,
        "pickup_end": listing.pickup_end,
        "safe_until": listing.safe_until,
        "reservations_close_at": reservations_close_at(listing),
        "pickup_instructions": listing.pickup_instructions or provider.pickup_instructions,
        "availability": availability(listing, now),
        "provider": provider,
    }


# ---------------------------------------------------------------------------------------------------------
# Validation, including the food-safety window
# ---------------------------------------------------------------------------------------------------------


def validate_listing(data: _FoodTiming, now: datetime, *, publishing: bool) -> None:
    """Collect every problem at once so the form can highlight all of them."""
    settings = get_settings()
    errors: list[dict[str, str]] = []

    def problem(field: str, message: str) -> None:
        errors.append({"field": field, "message": message})

    if data.price_paise > data.original_price_paise:
        problem("price_paise", "The FoodLoop price can't be higher than the original price.")
    if data.max_per_order > data.quantity_total:
        problem("max_per_order", "The limit per order can't be more than the total quantity.")
    if data.prepared_at > now + timedelta(minutes=5):
        problem("prepared_at", "The preparation time can't be in the future.")
    if data.pickup_start < data.prepared_at:
        problem("pickup_start", "Pickup can't start before the food was prepared.")
    if data.pickup_end <= data.pickup_start:
        problem("pickup_end", "Pickup must end after it starts.")
    if data.safe_until < data.pickup_end:
        problem("safe_until", "The eat-by time must be at or after the end of the pickup window.")

    max_hours = settings.max_safe_hours(data.storage)
    if data.safe_until - data.prepared_at > timedelta(hours=max_hours):
        label = LABELS["storage"][data.storage.value].lower()
        problem(
            "safe_until",
            f"FoodLoop's safety policy: food {label} must be eaten within {max_hours:g} hours of preparation.",
        )

    lead = settings.reservation_cutoff_minutes + 5
    if publishing and data.pickup_end <= now + timedelta(minutes=lead):
        problem("pickup_end", f"To publish, the pickup window must end at least {lead} minutes from now.")

    if errors:
        raise DomainError(422, "Please check the highlighted fields.", errors=errors)


# ---------------------------------------------------------------------------------------------------------
# Public browsing
# ---------------------------------------------------------------------------------------------------------


def _publicly_visible() -> list:
    return [
        Listing.status == ListingStatus.active,
        Provider.status == ProviderStatus.approved,
        Provider.fssai_valid_until >= today_ist(),
    ]


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def browse(
    db: Session,
    *,
    q: str | None,
    meal_types: list[str],
    diets: list[str],
    min_price_paise: int | None,
    max_price_paise: int | None,
    exclude_allergens: list[str],
    availability_filter: AvailabilityFilter,
    sort: Sort,
    limit: int,
    offset: int,
    kitchen_slug: str | None = None,
) -> tuple[list[Listing], int]:
    now = utcnow()
    closes_after = now + timedelta(minutes=get_settings().reservation_cutoff_minutes)

    stmt: Select = (
        select(Listing)
        .join(Provider, Listing.provider_id == Provider.id)
        # Expired food is never shown, whatever the filter.
        .where(*_publicly_visible(), Listing.pickup_end > now, Listing.safe_until > now)
    )
    if availability_filter in ("available", "pickup_now"):
        stmt = stmt.where(Listing.quantity_available > 0, Listing.pickup_end > closes_after)
    if availability_filter == "pickup_now":
        stmt = stmt.where(Listing.pickup_start <= now)
    if q:
        pattern = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                Listing.title.ilike(pattern, escape="\\"),
                Listing.description.ilike(pattern, escape="\\"),
                Provider.name.ilike(pattern, escape="\\"),
                Provider.area.ilike(pattern, escape="\\"),
                Provider.city.ilike(pattern, escape="\\"),
            )
        )
    if kitchen_slug:
        stmt = stmt.where(Provider.slug == kitchen_slug)
    if meal_types:
        stmt = stmt.where(Listing.meal_type.in_(meal_types))
    if diets:
        stmt = stmt.where(Listing.diet.in_(diets))
    if min_price_paise is not None:
        stmt = stmt.where(Listing.price_paise >= min_price_paise)
    if max_price_paise is not None:
        stmt = stmt.where(Listing.price_paise <= max_price_paise)
    if exclude_allergens:
        stmt = stmt.where(~Listing.allergens.overlap(exclude_allergens))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    order = {
        "ending_soon": [Listing.pickup_end.asc()],
        "price_low": [Listing.price_paise.asc(), Listing.pickup_end.asc()],
        "discount": [
            ((Listing.original_price_paise - Listing.price_paise) * 1.0 / Listing.original_price_paise).desc(),
            Listing.pickup_end.asc(),
        ],
        "newest": [Listing.created_at.desc()],
    }[sort]
    items = db.scalars(
        stmt.options(joinedload(Listing.provider)).order_by(*order, Listing.id).limit(limit).offset(offset)
    ).all()
    return list(items), total


def get_public(db: Session, listing_id: uuid.UUID) -> Listing:
    """Detail page. Shows expired/sold-out listings (with that status) but never unapproved or removed ones."""
    listing = db.scalar(
        select(Listing)
        .join(Provider, Listing.provider_id == Provider.id)
        .options(joinedload(Listing.provider))
        .where(Listing.id == listing_id, *_publicly_visible())
    )
    if listing is None:
        raise DomainError(404, "This meal isn't available on FoodLoop.")
    return listing


# ---------------------------------------------------------------------------------------------------------
# Provider actions
# ---------------------------------------------------------------------------------------------------------


def taken_quantities(db: Session, listing_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    """Reserved and collected portions per listing, for provider dashboards and quantity edits."""
    result: dict[uuid.UUID, dict[str, int]] = {
        listing_id: {"reserved": 0, "collected": 0, "no_show": 0} for listing_id in listing_ids
    }
    if not listing_ids:
        return result
    rows = db.execute(
        select(Reservation.listing_id, Reservation.status, func.sum(Reservation.quantity))
        .where(Reservation.listing_id.in_(listing_ids), Reservation.status.in_(TAKEN_STATUSES))
        .group_by(Reservation.listing_id, Reservation.status)
    ).all()
    for listing_id, status, quantity in rows:
        result[listing_id][status.value] = int(quantity)
    return result


def provider_listing_out(listing: Listing, now: datetime, taken: dict[str, int]) -> dict:
    return {
        **listing_out(listing, now),
        "status": listing.status,
        "removed_reason": listing.removed_reason,
        "reserved_quantity": taken["reserved"],
        "collected_quantity": taken["collected"],
        "created_at": listing.created_at,
        "updated_at": listing.updated_at,
    }


def get_own(db: Session, provider: Provider, listing_id: uuid.UUID, *, lock: bool = False) -> Listing:
    stmt = select(Listing).where(Listing.id == listing_id, Listing.provider_id == provider.id)
    if lock:
        stmt = stmt.with_for_update()
    listing = db.scalar(stmt)
    if listing is None:
        # 404 (not 403) so providers can't probe which ids belong to other kitchens.
        raise DomainError(404, "Listing not found.")
    return listing


_INPUT_FIELDS = (
    "title", "description", "meal_type", "diet", "allergens", "allergen_note", "original_price_paise",
    "price_paise", "quantity_total", "max_per_order", "storage", "prepared_at", "pickup_start", "pickup_end",
    "safe_until", "pickup_instructions", "image_is_representative",
)  # fmt: skip


def create(db: Session, user: User, provider: Provider, data: ListingCreate) -> Listing:
    now = utcnow()
    validate_listing(data, now, publishing=data.publish)
    listing = Listing(
        provider_id=provider.id,
        **{field: getattr(data, field) for field in _INPUT_FIELDS},
        quantity_available=data.quantity_total,
        status=ListingStatus.active if data.publish else ListingStatus.draft,
        safety_declared_by=user.id,
        safety_declared_at=now,
    )
    db.add(listing)
    db.flush()
    audit.record(db, user, "listing.created", "listing", listing.id, title=listing.title, status=listing.status)
    db.commit()
    db.refresh(listing)
    return listing


def update(db: Session, user: User, provider: Provider, listing_id: uuid.UUID, data: ListingInput) -> Listing:
    now = utcnow()
    # Lock the row: a reservation happening right now waits until this edit is saved, then re-checks stock.
    listing = get_own(db, provider, listing_id, lock=True)
    if listing.status == ListingStatus.removed:
        raise DomainError(409, "A removed listing can't be edited. Create a new one instead.")
    validate_listing(data, now, publishing=listing.status == ListingStatus.active)

    taken = sum(taken_quantities(db, [listing.id])[listing.id].values())
    if data.quantity_total < taken:
        raise DomainError(
            422,
            f"{taken} portions are already reserved or collected, so the total can't be lower.",
            field="quantity_total",
        )
    for field in _INPUT_FIELDS:
        setattr(listing, field, getattr(data, field))
    listing.quantity_available = data.quantity_total - taken
    listing.safety_declared_by = user.id
    listing.safety_declared_at = now
    audit.record(db, user, "listing.updated", "listing", listing.id)
    db.commit()
    db.refresh(listing)
    return listing


def change_status(db: Session, user: User, provider: Provider, listing_id: uuid.UUID, status: str) -> Listing:
    listing = get_own(db, provider, listing_id, lock=True)
    if listing.status == ListingStatus.removed:
        raise DomainError(409, "A removed listing can't be changed.")
    new_status = ListingStatus(status)
    if new_status == ListingStatus.active:
        validate_listing(listing, utcnow(), publishing=True)
    listing.status = new_status
    audit.record(db, user, f"listing.{new_status.value}", "listing", listing.id)
    db.commit()
    db.refresh(listing)
    return listing


def remove(db: Session, actor: User, listing: Listing, reason: str, *, by_admin: bool) -> Listing:
    """Hide a listing for good and cancel its open reservations so nobody is handed that food."""
    from app.services.reservations import cancel_open_reservations

    listing.status = ListingStatus.removed
    listing.removed_reason = reason
    listing.removed_by = actor.id
    listing.removed_at = utcnow()
    cancelled = cancel_open_reservations(
        db,
        Reservation.listing_id == listing.id,
        cancelled_by="admin" if by_admin else "provider",
        reason=f"The listing was removed: {reason}",
    )
    audit.record(
        db,
        actor,
        "listing.removed",
        "listing",
        listing.id,
        reason=reason,
        by_admin=by_admin,
        reservations_cancelled=cancelled,
    )
    db.commit()
    db.refresh(listing)
    return listing


def provider_listings(db: Session, provider: Provider, *, include_removed: bool) -> list[Listing]:
    stmt = select(Listing).options(joinedload(Listing.provider)).where(Listing.provider_id == provider.id)
    if not include_removed:
        stmt = stmt.where(Listing.status != ListingStatus.removed)
    return list(db.scalars(stmt.order_by(Listing.pickup_end.desc())).all())


def admin_listings(db: Session, status: str | None, q: str | None, limit: int, offset: int) -> tuple[list, int]:
    stmt = select(Listing).join(Provider, Listing.provider_id == Provider.id)
    if status == "live":
        now = utcnow()
        stmt = stmt.where(*_publicly_visible(), Listing.pickup_end > now)
    elif status:
        stmt = stmt.where(Listing.status == status)
    if q:
        pattern = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(or_(Listing.title.ilike(pattern, escape="\\"), Provider.name.ilike(pattern, escape="\\")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.options(joinedload(Listing.provider))
        .order_by(Listing.created_at.desc(), Listing.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), total
