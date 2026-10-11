import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_customer
from app.clock import utcnow
from app.db import get_db
from app.models import User
from app.schemas.reservation import CustomerCancel, CustomerReservationOut, ReservationCreate
from app.services import reservations as reservation_service

router = APIRouter(prefix="/api/reservations", tags=["reservations"])


@router.post("", response_model=CustomerReservationOut, status_code=201)
def reserve(data: ReservationCreate, customer: User = Depends(require_customer), db: Session = Depends(get_db)):
    reservation = reservation_service.create(db, customer, data)
    reservation = reservation_service.get_for_customer(db, customer, reservation.id)
    return reservation_service.customer_out(reservation, utcnow())


@router.get("/mine", response_model=list[CustomerReservationOut])
def my_reservations(customer: User = Depends(require_customer), db: Session = Depends(get_db)):
    now = utcnow()
    return [reservation_service.customer_out(item, now) for item in reservation_service.for_customer(db, customer)]


@router.get("/{reservation_id}", response_model=CustomerReservationOut)
def get_reservation(
    reservation_id: uuid.UUID, customer: User = Depends(require_customer), db: Session = Depends(get_db)
):
    reservation = reservation_service.get_for_customer(db, customer, reservation_id)
    return reservation_service.customer_out(reservation, utcnow())


@router.post("/{reservation_id}/cancel", response_model=CustomerReservationOut)
def cancel(
    reservation_id: uuid.UUID,
    data: CustomerCancel,
    customer: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    reservation_service.cancel_by_customer(db, customer, reservation_id, data.reason)
    reservation = reservation_service.get_for_customer(db, customer, reservation_id)
    return reservation_service.customer_out(reservation, utcnow())
