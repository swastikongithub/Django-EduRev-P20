import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints, field_validator

from app.models.enums import ContactTopic, FssaiKind, MealType, ProviderKind
from app.schemas.auth import Name
from app.schemas.common import ApiModel


class KitchenCard(BaseModel):
    """A kitchen as the public sees it, with what it has on offer right now."""

    id: uuid.UUID
    name: str
    slug: str
    kind: ProviderKind
    description: str
    area: str
    city: str
    is_sample: bool
    live_meals: int
    lowest_price_paise: int | None
    meal_types: list[MealType]


class KitchenDetail(KitchenCard):
    address_line: str
    pincode: str
    pickup_instructions: str
    fssai_number: str
    fssai_kind: FssaiKind


class ContactRequest(BaseModel):
    name: Name
    email: EmailStr
    topic: ContactTopic
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)]
    # Left empty by people; spam bots fill in every field they see. The form hides it from humans.
    website: Annotated[str, StringConstraints(max_length=200)] = ""

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.lower()


class ContactMessageOut(ApiModel):
    id: uuid.UUID
    name: str
    email: str
    topic: ContactTopic
    message: str
    created_at: datetime
    handled_at: datetime | None
