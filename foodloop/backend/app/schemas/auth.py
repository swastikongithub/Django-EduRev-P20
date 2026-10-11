import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints, field_validator

from app.clock import today_ist
from app.models.enums import FssaiKind, ProviderKind, ProviderStatus, UserRole
from app.schemas.common import ApiModel, Phone, ShortText

# A short list of passwords attackers try first. Length matters more than symbols (NIST guidance).
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "1234567890", "qwerty123",
    "qwertyuiop", "iloveyou", "11111111", "00000000", "abcd1234", "foodloop", "foodloop123",
}  # fmt: skip

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=8, max_length=128)]
    full_name: Name
    phone: Phone | None = None

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def not_common(cls, value: str) -> str:
        if value.lower() in _COMMON_PASSWORDS or len(set(value)) < 4:
            raise ValueError("This password is too easy to guess. Try a short phrase you'll remember.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.lower()


class KitchenFields(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    kind: ProviderKind
    description: ShortText = ""
    address_line: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=200)]
    area: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    city: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    pincode: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[1-9][0-9]{5}$")]
    contact_phone: Phone
    fssai_number: str
    fssai_kind: FssaiKind
    fssai_valid_until: date
    pickup_instructions: ShortText = ""

    @field_validator("fssai_number", mode="before")
    @classmethod
    def clean_fssai(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.replace(" ", "").replace("-", "")
            if len(value) != 14 or not value.isdigit():
                raise ValueError("An FSSAI licence or registration number has exactly 14 digits.")
        return value

    @field_validator("fssai_valid_until")
    @classmethod
    def not_expired(cls, value: date) -> date:
        if value < today_ist():
            raise ValueError("This FSSAI registration has expired. Renew it before joining FoodLoop.")
        return value


class ProviderRegisterRequest(RegisterRequest):
    kitchen: KitchenFields


class UserOut(ApiModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    role: UserRole


class ProviderOut(ApiModel):
    id: uuid.UUID
    name: str
    slug: str
    kind: ProviderKind
    description: str
    address_line: str
    area: str
    city: str
    pincode: str
    contact_phone: str
    fssai_number: str
    fssai_kind: FssaiKind
    fssai_valid_until: date
    pickup_instructions: str
    status: ProviderStatus
    status_reason: str | None
    is_sample: bool


class MeResponse(BaseModel):
    user: UserOut
    provider: ProviderOut | None = None
