"""Public pages beyond meals: kitchen profiles and the contact form."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.auth import _check_rate, _client_ip
from app.api.deps import current_user_optional
from app.db import get_db
from app.models import ContactMessage, User
from app.schemas.public import ContactRequest, KitchenCard, KitchenDetail
from app.services import kitchens as kitchen_service

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/kitchens", response_model=list[KitchenCard])
def kitchens(db: Session = Depends(get_db)):
    """Approved kitchens, the ones with the most food on offer first."""
    return kitchen_service.list_kitchens(db)


@router.get("/kitchens/{slug}", response_model=KitchenDetail)
def kitchen(slug: str, db: Session = Depends(get_db)):
    return kitchen_service.get_kitchen(db, slug)


@router.post("/contact", status_code=201)
def contact(
    data: ContactRequest,
    request: Request,
    user: User | None = Depends(current_user_optional),
    db: Session = Depends(get_db),
) -> dict:
    """Save a message for the FoodLoop team. Admins see it in their dashboard."""
    _check_rate(f"contact:{_client_ip(request)}", 5, 60)
    if not data.website:  # bots fill the hidden field; quietly accept and drop their message
        db.add(
            ContactMessage(
                name=data.name,
                email=data.email,
                topic=data.topic,
                message=data.message,
                user_id=user.id if user else None,
            )
        )
        db.commit()
    return {"detail": "Thanks! We've got your message and will reply by email."}
