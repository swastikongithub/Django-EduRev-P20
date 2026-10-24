import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, enum_type
from app.models.enums import ContactTopic


class ContactMessage(Base):
    """A message sent through the website's contact form. Admins read and close them in the dashboard."""

    __tablename__ = "contact_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))
    topic: Mapped[ContactTopic] = mapped_column(enum_type(ContactTopic, "contact_topic"))
    message: Mapped[str] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    handled_at: Mapped[datetime | None]
    handled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
