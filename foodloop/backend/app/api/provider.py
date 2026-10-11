"""Routes for kitchens: profile, listings, today's pickups and simple reports."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from app.api.deps import ProviderContext, require_approved_provider, require_provider_member
from app.clock import utcnow
from app.config import get_settings
from app.db import get_db
from app.errors import DomainError
from app.schemas.auth import KitchenFields, ProviderOut
from app.schemas.common import Reason
from app.schemas.listing import ListingCreate, ListingInput, ListingStatusChange, ProviderListingOut
from app.schemas.reservation import CollectRequest, ProviderReservationOut
from app.services import listings as listing_service
from app.services import providers as provider_service
from app.services import reservations as reservation_service
from app.services import stats as stats_service
from app.storage.images import delete_image, save_listing_image

router = APIRouter(prefix="/api/provider", tags=["provider"])


class OptionalReason(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""


class RequiredReason(BaseModel):
    reason: Reason


def _listing_out(db: Session, listing) -> dict:
    taken = listing_service.taken_quantities(db, [listing.id])[listing.id]
    return listing_service.provider_listing_out(listing, utcnow(), taken)


# --- Kitchen profile -------------------------------------------------------------------------------------


@router.get("/me", response_model=ProviderOut)
def my_kitchen(ctx: ProviderContext = Depends(require_provider_member)):
    return ctx.provider


@router.put("/me", response_model=ProviderOut)
def update_my_kitchen(
    data: KitchenFields, ctx: ProviderContext = Depends(require_provider_member), db: Session = Depends(get_db)
):
    """Changing the name, address or FSSAI details of an approved kitchen sends it back for re-verification."""
    return provider_service.update_profile(db, ctx.user, ctx.provider, data)


@router.get("/stats")
def my_stats(ctx: ProviderContext = Depends(require_provider_member), db: Session = Depends(get_db)):
    return stats_service.provider_stats(db, ctx.provider)


# --- Listings ---------------------------------------------------------------------------------------------


@router.get("/listings", response_model=list[ProviderListingOut])
def my_listings(
    include_removed: bool = False,
    ctx: ProviderContext = Depends(require_provider_member),
    db: Session = Depends(get_db),
):
    items = listing_service.provider_listings(db, ctx.provider, include_removed=include_removed)
    taken = listing_service.taken_quantities(db, [item.id for item in items])
    now = utcnow()
    return [listing_service.provider_listing_out(item, now, taken[item.id]) for item in items]


@router.post("/listings", response_model=ProviderListingOut, status_code=201)
def create_listing(
    data: ListingCreate, ctx: ProviderContext = Depends(require_approved_provider), db: Session = Depends(get_db)
):
    listing = listing_service.create(db, ctx.user, ctx.provider, data)
    return _listing_out(db, listing)


@router.get("/listings/{listing_id}", response_model=ProviderListingOut)
def get_listing(
    listing_id: uuid.UUID, ctx: ProviderContext = Depends(require_provider_member), db: Session = Depends(get_db)
):
    return _listing_out(db, listing_service.get_own(db, ctx.provider, listing_id))


@router.put("/listings/{listing_id}", response_model=ProviderListingOut)
def update_listing(
    listing_id: uuid.UUID,
    data: ListingInput,
    ctx: ProviderContext = Depends(require_approved_provider),
    db: Session = Depends(get_db),
):
    listing = listing_service.update(db, ctx.user, ctx.provider, listing_id, data)
    return _listing_out(db, listing)


@router.post("/listings/{listing_id}/status", response_model=ProviderListingOut)
def change_listing_status(
    listing_id: uuid.UUID,
    data: ListingStatusChange,
    ctx: ProviderContext = Depends(require_approved_provider),
    db: Session = Depends(get_db),
):
    listing = listing_service.change_status(db, ctx.user, ctx.provider, listing_id, data.status)
    return _listing_out(db, listing)


@router.post("/listings/{listing_id}/remove", response_model=ProviderListingOut)
def remove_listing(
    listing_id: uuid.UUID,
    data: OptionalReason,
    ctx: ProviderContext = Depends(require_provider_member),
    db: Session = Depends(get_db),
):
    """Removing is always allowed (even for a suspended kitchen). Open reservations are cancelled."""
    listing = listing_service.get_own(db, ctx.provider, listing_id, lock=True)
    if listing.status.value == "removed":
        raise DomainError(409, "This listing is already removed.")
    listing = listing_service.remove(db, ctx.user, listing, data.reason or "Removed by the kitchen", by_admin=False)
    return _listing_out(db, listing)


@router.post("/listings/{listing_id}/image", response_model=ProviderListingOut)
async def upload_listing_image(
    listing_id: uuid.UUID,
    image: UploadFile = File(...),
    is_representative: bool = Form(False),
    ctx: ProviderContext = Depends(require_approved_provider),
    db: Session = Depends(get_db),
):
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    data = await image.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise DomainError(413, f"Photos can be at most {get_settings().max_upload_mb} MB.", field="image")
    listing = listing_service.get_own(db, ctx.provider, listing_id, lock=True)
    if listing.status.value == "removed":
        raise DomainError(409, "A removed listing can't get a new photo.")
    old_path = listing.image_path
    listing.image_path = save_listing_image(data)
    listing.image_is_representative = is_representative
    db.commit()
    delete_image(old_path)
    db.refresh(listing)
    return _listing_out(db, listing)


# --- Pickups ----------------------------------------------------------------------------------------------


@router.get("/reservations", response_model=list[ProviderReservationOut])
def my_reservations(
    scope: Annotated[Literal["open", "all"], Query()] = "open",
    ctx: ProviderContext = Depends(require_provider_member),
    db: Session = Depends(get_db),
):
    now = utcnow()
    return [
        reservation_service.provider_out(item, now)
        for item in reservation_service.for_provider(db, ctx.provider, scope)
    ]


@router.post("/reservations/collect", response_model=ProviderReservationOut)
def collect(
    data: CollectRequest, ctx: ProviderContext = Depends(require_provider_member), db: Session = Depends(get_db)
):
    """Hand over food: staff type the customer's pickup code."""
    reservation = reservation_service.collect(db, ctx.user, ctx.provider, data.pickup_code)
    db.refresh(reservation)
    return reservation_service.provider_out(reservation, utcnow())


@router.post("/reservations/{reservation_id}/cancel", response_model=ProviderReservationOut)
def cancel(
    reservation_id: uuid.UUID,
    data: RequiredReason,
    ctx: ProviderContext = Depends(require_provider_member),
    db: Session = Depends(get_db),
):
    reservation = reservation_service.cancel_by_provider(db, ctx.user, ctx.provider, reservation_id, data.reason)
    db.refresh(reservation)
    return reservation_service.provider_out(reservation, utcnow())
