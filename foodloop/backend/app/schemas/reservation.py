import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import CancelledBy, Diet, MealType, PaymentMethod, PaymentStatus, ReservationStatus

DisplayStatus = Literal["reserved", "collected", "cancelled", "no_show", "missed"]


class ReservationCreate(BaseModel):
    listing_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    # The browser sends a fresh random id per "Reserve" click; repeats of the same click are ignored.
    idempotency_key: uuid.UUID | None = None


class CustomerCancel(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""


class CollectRequest(BaseModel):
    pickup_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=12)]


class ListingBrief(BaseModel):
    id: uuid.UUID
    title: str
    image_url: str | None
    meal_type: MealType
    diet: Diet
    pickup_start: datetime
    pickup_end: datetime
    safe_until: datetime


class ProviderBrief(BaseModel):
    id: uuid.UUID
    name: str
    address_line: str
    area: str
    city: str
    contact_phone: str
    pickup_instructions: str
    is_sample: bool


class ReservationBase(BaseModel):
    id: uuid.UUID
    quantity: int
    unit_price_paise: int
    total_paise: int
    status: ReservationStatus
    # Like status, but shows "missed" for an uncollected reservation whose pickup window has ended.
    display_status: DisplayStatus
    pickup_deadline: datetime
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    cancelled_by: CancelledBy | None
    cancel_reason: str | None
    created_at: datetime
    collected_at: datetime | None
    cancelled_at: datetime | None
    listing: ListingBrief


class CustomerReservationOut(ReservationBase):
    # Only the customer sees the code; they show it at the counter, which proves the order is theirs.
    pickup_code: str
    can_cancel: bool
    provider: ProviderBrief


class ProviderReservationOut(ReservationBase):
    customer_name: str
