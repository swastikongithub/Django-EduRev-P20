import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, enum_type
from app.models.enums import CancelledBy, PaymentMethod, PaymentStatus, ReservationStatus
from app.models.listing import Listing
from app.models.provider import Provider
from app.models.user import User

ONE_ACTIVE_PER_LISTING = "uq_reservations_one_active_per_listing"
IDEMPOTENCY_UNIQUE = "uq_reservations_customer_idempotency"
PICKUP_CODE_UNIQUE = "uq_reservations_pickup_code"


class Reservation(TimestampMixin, Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("total_paise = unit_price_paise * quantity", name="total_matches"),
        # A customer can hold only one active reservation per meal (no accidental duplicates).
        Index(
            ONE_ACTIVE_PER_LISTING,
            "customer_id",
            "listing_id",
            unique=True,
            postgresql_where=text("status = 'reserved'"),
        ),
        # The same "Reserve" click sent twice (double tap, network retry) creates only one reservation.
        UniqueConstraint("customer_id", "idempotency_key", name=IDEMPOTENCY_UNIQUE),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pickup_code: Mapped[str] = mapped_column(String(6), unique=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="RESTRICT"), index=True)
    # Copied from the listing so provider dashboards don't need a join.
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id", ondelete="RESTRICT"), index=True)

    quantity: Mapped[int]
    # Price frozen at the moment of reserving, even if the provider edits the listing later.
    unit_price_paise: Mapped[int]
    total_paise: Mapped[int]

    status: Mapped[ReservationStatus] = mapped_column(
        enum_type(ReservationStatus, "reservation_status"), default=ReservationStatus.reserved, index=True
    )
    pickup_deadline: Mapped[datetime]

    payment_method: Mapped[PaymentMethod] = mapped_column(
        enum_type(PaymentMethod, "payment_method"), default=PaymentMethod.pay_at_pickup
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        enum_type(PaymentStatus, "payment_status"), default=PaymentStatus.unpaid
    )

    idempotency_key: Mapped[uuid.UUID | None]

    cancelled_by: Mapped[CancelledBy | None] = mapped_column(enum_type(CancelledBy, "cancelled_by"))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None]
    collected_at: Mapped[datetime | None]
    collected_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    listing: Mapped[Listing] = relationship()
    provider: Mapped[Provider] = relationship()
    customer: Mapped[User] = relationship(foreign_keys=[customer_id])
