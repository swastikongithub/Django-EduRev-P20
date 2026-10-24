import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db import get_db
from app.models.enums import Allergen, Diet, MealType
from app.schemas.listing import ListingOut, ListingPage
from app.services import listings as listing_service
from app.services.listings import AvailabilityFilter, Sort

router = APIRouter(prefix="/api/listings", tags=["listings"])


@router.get("", response_model=ListingPage)
def browse(
    db: Session = Depends(get_db),
    q: Annotated[str | None, Query(max_length=80)] = None,
    kitchen: Annotated[str | None, Query(max_length=140, description="a kitchen's slug")] = None,
    meal_type: Annotated[list[MealType], Query()] = [],  # noqa: B006 - FastAPI copies defaults per request
    diet: Annotated[list[Diet], Query()] = [],  # noqa: B006
    exclude_allergen: Annotated[list[Allergen], Query()] = [],  # noqa: B006
    min_price_paise: Annotated[int | None, Query(ge=0, le=1_000_000)] = None,
    max_price_paise: Annotated[int | None, Query(ge=0, le=1_000_000)] = None,
    availability: AvailabilityFilter = "available",
    sort: Sort = "ending_soon",
    limit: Annotated[int, Query(ge=1, le=60)] = 24,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
):
    """Public list of meals you can see right now. Expired food is never included."""
    items, total = listing_service.browse(
        db,
        q=q,
        meal_types=[value.value for value in meal_type],
        diets=[value.value for value in diet],
        min_price_paise=min_price_paise,
        max_price_paise=max_price_paise,
        exclude_allergens=[value.value for value in exclude_allergen],
        availability_filter=availability,
        sort=sort,
        limit=limit,
        offset=offset,
        kitchen_slug=kitchen,
    )
    now = utcnow()
    return {
        "items": [listing_service.listing_out(item, now) for item in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{listing_id}", response_model=ListingOut)
def detail(listing_id: uuid.UUID, db: Session = Depends(get_db)):
    listing = listing_service.get_public(db, listing_id)
    return listing_service.listing_out(listing, utcnow())
