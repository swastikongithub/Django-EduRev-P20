"""Public kitchen pages: approved kitchens and what each has on offer right now."""

from datetime import timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.clock import today_ist, utcnow
from app.config import get_settings
from app.errors import DomainError
from app.models import Listing, Provider
from app.models.enums import ListingStatus, ProviderStatus


def _kitchens(db: Session, slug: str | None = None) -> list[dict]:
    now = utcnow()
    closes_after = now + timedelta(minutes=get_settings().reservation_cutoff_minutes)
    # Same rules as the public meal list: only food that can still be reserved counts as "live".
    live = (
        select(
            Listing.provider_id,
            func.count().label("live_meals"),
            func.min(Listing.price_paise).label("lowest_price_paise"),
            func.array_agg(distinct(Listing.meal_type)).label("meal_types"),
        )
        .where(
            Listing.status == ListingStatus.active,
            Listing.quantity_available > 0,
            Listing.pickup_end > closes_after,
            Listing.safe_until > now,
        )
        .group_by(Listing.provider_id)
        .subquery()
    )
    stmt = (
        select(Provider, live.c.live_meals, live.c.lowest_price_paise, live.c.meal_types)
        .outerjoin(live, live.c.provider_id == Provider.id)
        .where(Provider.status == ProviderStatus.approved, Provider.fssai_valid_until >= today_ist())
        .order_by(func.coalesce(live.c.live_meals, 0).desc(), Provider.name)
    )
    if slug:
        stmt = stmt.where(Provider.slug == slug)
    rows = []
    for provider, live_meals, lowest, meal_types in db.execute(stmt):
        rows.append(
            {
                **{column: getattr(provider, column) for column in KITCHEN_FIELDS},
                "live_meals": live_meals or 0,
                "lowest_price_paise": lowest,
                "meal_types": sorted(meal_types or []),
            }
        )
    return rows


KITCHEN_FIELDS = (
    "id", "name", "slug", "kind", "description", "area", "city", "is_sample",
    "address_line", "pincode", "pickup_instructions", "fssai_number", "fssai_kind",
)  # fmt: skip


def list_kitchens(db: Session) -> list[dict]:
    return _kitchens(db)


def get_kitchen(db: Session, slug: str) -> dict:
    rows = _kitchens(db, slug)
    if not rows:
        raise DomainError(404, "We couldn't find that kitchen.")
    return rows[0]
