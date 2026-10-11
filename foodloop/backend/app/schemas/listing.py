import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, field_validator

from app.models.enums import Allergen, Diet, FssaiKind, ListingStatus, MealType, ProviderKind, Storage
from app.schemas.common import ApiModel, ShortText

Availability = Literal["available", "sold_out", "closed", "expired", "paused", "draft", "removed", "unavailable"]


class ListingInput(BaseModel):
    """What a provider sends to create or fully update a listing. Cross-field rules (prices, times,
    food-safety window) are checked in services/listings.py because they depend on the clock and settings."""

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=80)]
    description: ShortText = ""
    meal_type: MealType
    diet: Diet
    # Required with no default: the provider must actively choose (an empty list = none of these).
    allergens: list[Allergen]
    allergen_note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    original_price_paise: int = Field(ge=100, le=100_000)
    price_paise: int = Field(ge=100, le=100_000)
    quantity_total: int = Field(ge=1, le=500)
    max_per_order: int = Field(default=2, ge=1, le=10)
    storage: Storage
    prepared_at: AwareDatetime
    pickup_start: AwareDatetime
    pickup_end: AwareDatetime
    safe_until: AwareDatetime
    pickup_instructions: ShortText = ""
    image_is_representative: bool = False
    safety_confirmed: bool = Field(description="The provider ticked the food-safety checklist.")

    @field_validator("allergens")
    @classmethod
    def unique_allergens(cls, value: list[Allergen]) -> list[Allergen]:
        return sorted(set(value))

    @field_validator("safety_confirmed")
    @classmethod
    def must_confirm(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Please confirm the food-safety checklist before saving.")
        return value


class ListingCreate(ListingInput):
    publish: bool = True


class ListingStatusChange(BaseModel):
    status: Literal["draft", "active", "paused"]


class ProviderPublic(ApiModel):
    id: uuid.UUID
    name: str
    slug: str
    kind: ProviderKind
    address_line: str
    area: str
    city: str
    fssai_number: str
    fssai_kind: FssaiKind
    is_sample: bool


class ListingOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    meal_type: MealType
    diet: Diet
    allergens: list[str]
    allergen_note: str
    image_url: str | None
    image_is_representative: bool
    original_price_paise: int
    price_paise: int
    discount_percent: int
    quantity_total: int
    quantity_available: int
    max_per_order: int
    storage: Storage
    prepared_at: datetime
    pickup_start: datetime
    pickup_end: datetime
    safe_until: datetime
    reservations_close_at: datetime
    pickup_instructions: str
    availability: Availability
    provider: ProviderPublic


class ProviderListingOut(ListingOut):
    status: ListingStatus
    removed_reason: str | None
    reserved_quantity: int
    collected_quantity: int
    created_at: datetime
    updated_at: datetime


class ListingPage(BaseModel):
    items: list[ListingOut]
    total: int
    limit: int
    offset: int
