"""Basic numbers for the provider and admin dashboards."""

from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.clock import start_of_today_ist, today_ist, utcnow
from app.models import AuditLog, Listing, Provider, Reservation, User
from app.models.enums import ListingStatus, ProviderStatus, ReservationStatus, UserRole


def _sum_if(condition, value=Reservation.quantity):
    return func.coalesce(func.sum(case((condition, value), else_=0)), 0)


def _funnel(db: Session, provider_id, start: datetime, end: datetime) -> dict:
    """listed → reserved → collected, for listings whose pickup started in [start, end).

    Everything is grouped by the day the food was offered (pickup start), so a pickup that runs past
    midnight still counts for the day it was listed.
    """
    now = utcnow()
    in_period = [Listing.provider_id == provider_id, Listing.pickup_start >= start, Listing.pickup_start < end]
    listed = db.scalar(
        select(func.coalesce(func.sum(Listing.quantity_total), 0)).where(
            *in_period, Listing.status != ListingStatus.draft
        )
    )
    missed = (Reservation.status == ReservationStatus.no_show) | (
        (Reservation.status == ReservationStatus.reserved) & (Reservation.pickup_deadline <= now)
    )
    row = db.execute(
        select(
            _sum_if(Reservation.status != ReservationStatus.cancelled),
            _sum_if(Reservation.status == ReservationStatus.collected),
            _sum_if(Reservation.status == ReservationStatus.cancelled),
            _sum_if(missed),
            _sum_if(Reservation.status == ReservationStatus.collected, Reservation.total_paise),
        )
        .join(Listing, Reservation.listing_id == Listing.id)
        .where(*in_period)
    ).one()
    reserved, collected, cancelled, missed_count, revenue = (int(value) for value in row)
    return {
        "portions_listed": int(listed),
        "portions_reserved": reserved,
        "portions_collected": collected,
        "portions_cancelled": cancelled,
        "portions_missed": missed_count,
        "revenue_recovered_paise": revenue,
        "sell_through_percent": round(100 * reserved / listed) if listed else None,
        "collection_rate_percent": round(100 * collected / reserved) if reserved else None,
    }


def provider_stats(db: Session, provider: Provider) -> dict:
    now = utcnow()
    today_start = start_of_today_ist()
    tomorrow = today_start + timedelta(days=1)
    live = db.scalar(
        select(func.count())
        .select_from(Listing)
        .where(
            Listing.provider_id == provider.id,
            Listing.status == ListingStatus.active,
            Listing.pickup_end > now,
        )
    )
    open_pickups = db.scalar(
        select(func.count())
        .select_from(Reservation)
        .where(
            Reservation.provider_id == provider.id,
            Reservation.status == ReservationStatus.reserved,
            Reservation.pickup_deadline > now,
        )
    )
    return {
        "live_listings": live,
        "open_pickups": open_pickups,
        "today": _funnel(db, provider.id, today_start, tomorrow),
        "last_7_days": _funnel(db, provider.id, today_start - timedelta(days=6), tomorrow),
    }


def admin_overview(db: Session) -> dict:
    now = utcnow()
    today_start = start_of_today_ist()
    provider_counts = dict(db.execute(select(Provider.status, func.count()).group_by(Provider.status)).all())
    user_counts = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    live_listings = db.scalar(
        select(func.count())
        .select_from(Listing)
        .join(Provider, Listing.provider_id == Provider.id)
        .where(
            Listing.status == ListingStatus.active,
            Provider.status == ProviderStatus.approved,
            Provider.fssai_valid_until >= today_ist(),
            Listing.pickup_end > now,
            Listing.quantity_available > 0,
        )
    )
    today_rows = dict(
        db.execute(
            select(Reservation.status, func.sum(Reservation.quantity))
            .where(Reservation.created_at >= today_start)
            .group_by(Reservation.status)
        ).all()
    )
    collected_all_time = db.scalar(
        select(func.coalesce(func.sum(Reservation.quantity), 0)).where(
            Reservation.status == ReservationStatus.collected
        )
    )
    return {
        "providers": {status.value: int(provider_counts.get(status, 0)) for status in ProviderStatus},
        "customers": int(user_counts.get(UserRole.customer, 0)),
        "live_listings": live_listings,
        "portions_reserved_today": {status.value: int(today_rows.get(status, 0)) for status in ReservationStatus},
        "portions_collected_all_time": int(collected_all_time),
    }


def recent_audit(db: Session, limit: int = 30) -> list[dict]:
    rows = db.execute(
        select(AuditLog, User.full_name)
        .outerjoin(User, AuditLog.actor_user_id == User.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": entry.id,
            "action": entry.action,
            "entity_type": entry.entity_type,
            "entity_id": entry.entity_id,
            "actor_name": actor_name,
            "details": entry.details,
            "created_at": entry.created_at,
        }
        for entry, actor_name in rows
    ]
