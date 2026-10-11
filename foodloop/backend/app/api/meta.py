from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.enums import LABELS, Storage

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Used by hosting platforms and by you, to check the API and database are both up."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any database failure means "not healthy"
        return JSONResponse(status_code=503, content={"status": "error", "database": "unreachable"})
    return {"status": "ok", "database": "ok"}


@router.get("/meta")
def meta():
    """Labels and policy values, so the website never hard-codes them."""
    settings = get_settings()
    return {
        "labels": LABELS,
        "safety_policy": {
            "max_safe_hours": {storage.value: settings.max_safe_hours(storage) for storage in Storage},
            "reservation_cutoff_minutes": settings.reservation_cutoff_minutes,
            "max_active_reservations_per_customer": settings.max_active_reservations_per_customer,
        },
    }
