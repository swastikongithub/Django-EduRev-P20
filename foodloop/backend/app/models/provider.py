import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, enum_type
from app.models.enums import FssaiKind, MemberRole, ProviderKind, ProviderStatus


class Provider(TimestampMixin, Base):
    """A kitchen that sells surplus food: canteen, cafeteria, hostel mess or PG kitchen.

    New providers start as `pending`. Nothing they list can be seen or bought until an admin approves them.
    """

    __tablename__ = "providers"
    __table_args__ = (
        CheckConstraint("pincode ~ '^[1-9][0-9]{5}$'", name="pincode_format"),
        CheckConstraint("fssai_number ~ '^[0-9]{14}$'", name="fssai_number_format"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140), unique=True)
    kind: Mapped[ProviderKind] = mapped_column(enum_type(ProviderKind, "provider_kind"))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    address_line: Mapped[str] = mapped_column(String(200))
    area: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    pincode: Mapped[str] = mapped_column(String(6))
    contact_phone: Mapped[str] = mapped_column(String(20))

    fssai_number: Mapped[str] = mapped_column(String(14))
    fssai_kind: Mapped[FssaiKind] = mapped_column(enum_type(FssaiKind, "fssai_kind"))
    fssai_valid_until: Mapped[date]

    pickup_instructions: Mapped[str] = mapped_column(Text, default="", server_default="")

    status: Mapped[ProviderStatus] = mapped_column(
        enum_type(ProviderStatus, "provider_status"), default=ProviderStatus.pending, index=True
    )
    status_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None]

    # True only for development sample data, so the UI can label it clearly.
    is_sample: Mapped[bool] = mapped_column(default=False, server_default=false())

    members: Mapped[list["ProviderMember"]] = relationship(back_populates="provider", cascade="all, delete-orphan")


class ProviderMember(Base):
    """Which user accounts can act for which kitchen. In the MVP each provider account has one kitchen."""

    __tablename__ = "provider_members"

    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, unique=True
    )
    member_role: Mapped[MemberRole] = mapped_column(enum_type(MemberRole, "member_role"), default=MemberRole.owner)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    provider: Mapped[Provider] = relationship(back_populates="members")
