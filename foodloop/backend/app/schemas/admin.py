import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.auth import ProviderOut
from app.schemas.common import Reason


class ReasonRequest(BaseModel):
    reason: Reason


class AdminProviderOut(ProviderOut):
    owner_name: str | None
    owner_email: str | None
    created_at: datetime
    reviewed_at: datetime | None
    fssai_expired: bool
    active_listings: int


class AuditEntryOut(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    actor_name: str | None
    details: dict
    created_at: datetime
