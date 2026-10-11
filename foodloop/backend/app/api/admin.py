"""Admin routes: approve kitchens, moderate listings, see platform numbers and the audit trail."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.clock import today_ist, utcnow
from app.db import get_db
from app.errors import DomainError
from app.models import Listing, Provider, ProviderMember, User
from app.models.enums import ListingStatus, MemberRole, ProviderStatus
from app.schemas.admin import AdminProviderOut, AuditEntryOut, ReasonRequest
from app.schemas.auth import ProviderOut
from app.schemas.listing import ProviderListingOut
from app.services import listings as listing_service
from app.services import providers as provider_service
from app.services import stats as stats_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _provider_rows(db: Session, provider_ids: list[uuid.UUID] | None = None, status: str | None = None) -> list[dict]:
    now = utcnow()
    live_counts = (
        select(Listing.provider_id, func.count().label("live"))
        .where(Listing.status == ListingStatus.active, Listing.pickup_end > now)
        .group_by(Listing.provider_id)
        .subquery()
    )
    stmt = (
        select(Provider, User.full_name, User.email, func.coalesce(live_counts.c.live, 0))
        .outerjoin(
            ProviderMember,
            (ProviderMember.provider_id == Provider.id) & (ProviderMember.member_role == MemberRole.owner),
        )
        .outerjoin(User, User.id == ProviderMember.user_id)
        .outerjoin(live_counts, live_counts.c.provider_id == Provider.id)
    )
    if status:
        stmt = stmt.where(Provider.status == status)
    if provider_ids is not None:
        stmt = stmt.where(Provider.id.in_(provider_ids))
    # Pending kitchens first: they are waiting for someone.
    pending_first = (Provider.status != ProviderStatus.pending).asc()
    rows = db.execute(stmt.order_by(pending_first, Provider.created_at.desc())).all()
    today = today_ist()
    return [
        {
            **ProviderOut.model_validate(provider).model_dump(),
            "created_at": provider.created_at,
            "reviewed_at": provider.reviewed_at,
            "owner_name": owner_name,
            "owner_email": owner_email,
            "fssai_expired": provider.fssai_valid_until < today,
            "active_listings": live,
        }
        for provider, owner_name, owner_email, live in rows
    ]


@router.get("/overview")
def overview(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {
        **stats_service.admin_overview(db),
        "recent_activity": [AuditEntryOut(**row) for row in stats_service.recent_audit(db)],
    }


@router.get("/providers", response_model=list[AdminProviderOut])
def providers(
    status: Annotated[ProviderStatus | None, Query()] = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _provider_rows(db, status=status.value if status else None)


def _one(db: Session, provider_id: uuid.UUID) -> dict:
    rows = _provider_rows(db, provider_ids=[provider_id])
    if not rows:
        raise DomainError(404, "Provider not found.")
    return rows[0]


@router.post("/providers/{provider_id}/approve", response_model=AdminProviderOut)
def approve(provider_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    provider_service.approve(db, admin, provider_id)
    return _one(db, provider_id)


@router.post("/providers/{provider_id}/reject", response_model=AdminProviderOut)
def reject(
    provider_id: uuid.UUID, data: ReasonRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    provider_service.reject(db, admin, provider_id, data.reason)
    return _one(db, provider_id)


@router.post("/providers/{provider_id}/suspend", response_model=AdminProviderOut)
def suspend(
    provider_id: uuid.UUID, data: ReasonRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    provider_service.suspend(db, admin, provider_id, data.reason)
    return _one(db, provider_id)


@router.get("/listings")
def listings(
    status: Annotated[Literal["live", "draft", "active", "paused", "removed"] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    items, total = listing_service.admin_listings(db, status, q, limit, offset)
    taken = listing_service.taken_quantities(db, [item.id for item in items])
    now = utcnow()
    return {
        "items": [
            ProviderListingOut(**listing_service.provider_listing_out(item, now, taken[item.id])) for item in items
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/listings/{listing_id}/remove", response_model=ProviderListingOut)
def remove_listing(
    listing_id: uuid.UUID, data: ReasonRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    listing = db.get(Listing, listing_id, with_for_update=True)
    if listing is None:
        raise DomainError(404, "Listing not found.")
    if listing.status == ListingStatus.removed:
        raise DomainError(409, "This listing is already removed.")
    listing = listing_service.remove(db, admin, listing, data.reason, by_admin=True)
    taken = listing_service.taken_quantities(db, [listing.id])[listing.id]
    return listing_service.provider_listing_out(listing, utcnow(), taken)
