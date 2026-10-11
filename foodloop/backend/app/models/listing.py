import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, false, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, enum_type
from app.models.enums import Allergen, Diet, ListingStatus, MealType, Storage
from app.models.provider import Provider

_ALLOWED_ALLERGENS = ", ".join(f"'{allergen.value}'" for allergen in Allergen)


class Listing(TimestampMixin, Base):
    """One batch of surplus food offered by a provider.

    "Sold out" and "expired" are deliberately NOT stored. They are worked out from `quantity_available`
    and `pickup_end` at the moment someone looks or buys, so a missed background job can never make
    expired food purchasable.
    """

    __tablename__ = "listings"
    __table_args__ = (
        CheckConstraint("original_price_paise > 0", name="original_price_positive"),
        CheckConstraint("price_paise > 0 AND price_paise <= original_price_paise", name="price_valid"),
        CheckConstraint("quantity_total > 0", name="quantity_total_positive"),
        CheckConstraint(
            "quantity_available >= 0 AND quantity_available <= quantity_total", name="quantity_available_range"
        ),
        CheckConstraint("max_per_order >= 1", name="max_per_order_positive"),
        CheckConstraint(
            "prepared_at <= pickup_start AND pickup_start < pickup_end AND pickup_end <= safe_until",
            name="time_order",
        ),
        CheckConstraint(f"allergens <@ ARRAY[{_ALLOWED_ALLERGENS}]::varchar[]", name="allergens_known"),
        Index("ix_listings_status_pickup_end", "status", "pickup_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)

    title: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    meal_type: Mapped[MealType] = mapped_column(enum_type(MealType, "meal_type"), index=True)
    diet: Mapped[Diet] = mapped_column(enum_type(Diet, "diet"))
    # The provider must choose explicitly; an empty list means "none of the listed allergens".
    allergens: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list, server_default="{}")
    allergen_note: Mapped[str] = mapped_column(String(200), default="", server_default="")

    image_path: Mapped[str | None] = mapped_column(String(255))
    image_is_representative: Mapped[bool] = mapped_column(default=False, server_default=false())

    # Money is stored in paise (₹1 = 100 paise) as whole numbers, never as decimals.
    original_price_paise: Mapped[int]
    price_paise: Mapped[int] = mapped_column(index=True)

    quantity_total: Mapped[int]
    quantity_available: Mapped[int]
    max_per_order: Mapped[int] = mapped_column(default=2, server_default=text("2"))

    storage: Mapped[Storage] = mapped_column(enum_type(Storage, "storage"))
    prepared_at: Mapped[datetime]
    pickup_start: Mapped[datetime]
    pickup_end: Mapped[datetime]
    safe_until: Mapped[datetime]  # "eat by"
    # Optional override of the provider's default pickup instructions.
    pickup_instructions: Mapped[str] = mapped_column(Text, default="", server_default="")

    status: Mapped[ListingStatus] = mapped_column(
        enum_type(ListingStatus, "listing_status"), default=ListingStatus.draft
    )
    removed_reason: Mapped[str | None] = mapped_column(Text)
    removed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    removed_at: Mapped[datetime | None]

    # Who ticked the food-safety checklist for this batch, and when.
    safety_declared_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    safety_declared_at: Mapped[datetime]

    provider: Mapped[Provider] = relationship()
