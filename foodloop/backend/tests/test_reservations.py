import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db import SessionLocal
from app.errors import DomainError
from app.models import Listing, Reservation, User
from app.models.enums import UserRole
from app.schemas.reservation import ReservationCreate
from app.security.passwords import hash_password
from app.services import reservations as reservation_service
from tests.conftest import (
    create_listing,
    customer_client,
    move_listing_to_past,
    provider_client,
    set_listing_times,
    unique_email,
)


def reserve(client, listing_id: str, quantity: int = 1, **extra):
    return client.post("/api/reservations", json={"listing_id": listing_id, "quantity": quantity, **extra})


def available(listing_id: str) -> int:
    with SessionLocal() as session:
        return session.get(Listing, uuid.UUID(listing_id)).quantity_available


def test_reserve_takes_stock_and_returns_pickup_details():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen, quantity_total=5)
    customer = customer_client()
    response = reserve(customer, listing["id"], 2)
    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body["pickup_code"]) == 6
    assert body["total_paise"] == 2 * 4000
    assert body["status"] == "reserved" and body["can_cancel"] is True
    assert body["payment_method"] == "pay_at_pickup" and body["payment_status"] == "unpaid"
    assert body["provider"]["pickup_instructions"] == "Side counter"
    assert available(listing["id"]) == 3


def test_quantity_limits():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen, quantity_total=3, max_per_order=2)
    first = customer_client()
    assert reserve(first, listing["id"], 3).status_code == 422  # over the per-order limit
    assert reserve(first, listing["id"], 2).status_code == 201
    response = reserve(customer_client(), listing["id"], 2)
    assert response.status_code == 409
    assert response.json()["detail"] == "Only 1 left. Lower the quantity and try again."
    assert reserve(customer_client(), listing["id"], 1).status_code == 201
    sold_out = reserve(customer_client(), listing["id"], 1)
    assert sold_out.status_code == 409 and "sold out" in sold_out.json()["detail"]


def test_duplicate_active_reservation_is_refused():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen)
    customer = customer_client()
    assert reserve(customer, listing["id"]).status_code == 201
    assert reserve(customer, listing["id"]).status_code == 409


def test_same_click_twice_creates_one_reservation():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen, quantity_total=5)
    customer = customer_client()
    key = str(uuid.uuid4())
    first = reserve(customer, listing["id"], 1, idempotency_key=key)
    second = reserve(customer, listing["id"], 1, idempotency_key=key)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert available(listing["id"]) == 4


def test_expired_and_closing_listings_cannot_be_reserved():
    kitchen, _ = provider_client()
    expired = create_listing(kitchen, title="Old")
    move_listing_to_past(expired["id"])
    assert reserve(customer_client(), expired["id"]).status_code == 409

    closing = create_listing(kitchen, title="Closing")
    set_listing_times(closing["id"], pickup_end_in_minutes=5)  # inside the 10-minute cutoff
    response = reserve(customer_client(), closing["id"])
    assert response.status_code == 409
    assert response.json()["detail"] == "Reservations for this meal have closed."


def test_paused_listing_cannot_be_reserved():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen)
    kitchen.post(f"/api/provider/listings/{listing['id']}/status", json={"status": "paused"})
    assert reserve(customer_client(), listing["id"]).status_code == 404


def test_active_reservation_limit_per_customer():
    kitchen, _ = provider_client()
    customer = customer_client()
    limit = get_settings().max_active_reservations_per_customer
    for index in range(limit):
        assert reserve(customer, create_listing(kitchen, title=f"Meal {index}")["id"]).status_code == 201
    response = reserve(customer, create_listing(kitchen, title="One too many")["id"])
    assert response.status_code == 409


def test_customer_cancel_returns_portions():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen, quantity_total=4)
    customer = customer_client()
    reservation = reserve(customer, listing["id"], 2).json()
    assert available(listing["id"]) == 2
    cancelled = customer.post(f"/api/reservations/{reservation['id']}/cancel", json={"reason": "Plans changed"})
    assert cancelled.json()["status"] == "cancelled"
    assert available(listing["id"]) == 4
    assert customer.post(f"/api/reservations/{reservation['id']}/cancel", json={}).status_code == 409
    # After cancelling, the customer may reserve the same meal again.
    assert reserve(customer, listing["id"], 1).status_code == 201


def test_customers_only_see_their_own_reservations():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen)
    owner = customer_client()
    other = customer_client()
    reservation = reserve(owner, listing["id"]).json()
    assert other.get(f"/api/reservations/{reservation['id']}").status_code == 404
    assert other.post(f"/api/reservations/{reservation['id']}/cancel", json={}).status_code == 404
    assert other.get("/api/reservations/mine").json() == []


def test_collection_requires_the_right_code_at_the_right_kitchen():
    kitchen, _ = provider_client(name="Kitchen A")
    other_kitchen, _ = provider_client(name="Kitchen B")
    listing = create_listing(kitchen)
    customer = customer_client("Meera Iyer")
    reservation = reserve(customer, listing["id"]).json()

    pickups = kitchen.get("/api/provider/reservations").json()
    assert pickups[0]["customer_name"] == "Meera Iyer"
    assert "pickup_code" not in pickups[0]  # the kitchen must ask the customer for it

    code = reservation["pickup_code"]
    assert other_kitchen.post("/api/provider/reservations/collect", json={"pickup_code": code}).status_code == 404
    assert kitchen.post("/api/provider/reservations/collect", json={"pickup_code": "ZZZZZZ"}).status_code == 404
    collected = kitchen.post("/api/provider/reservations/collect", json={"pickup_code": code.lower()})
    assert collected.status_code == 200
    assert collected.json()["status"] == "collected"
    assert collected.json()["payment_status"] == "paid"
    again = kitchen.post("/api/provider/reservations/collect", json={"pickup_code": code})
    assert again.status_code == 409
    assert customer.get("/api/reservations/mine").json()[0]["status"] == "collected"

    stats = kitchen.get("/api/provider/stats").json()
    assert stats["today"]["portions_collected"] == 1
    assert stats["today"]["revenue_recovered_paise"] == 4000


def test_provider_cancel_needs_a_reason_and_keeps_portions_off_sale():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen, quantity_total=3)
    customer = customer_client()
    reservation = reserve(customer, listing["id"]).json()
    url = f"/api/provider/reservations/{reservation['id']}/cancel"
    assert kitchen.post(url, json={"reason": ""}).status_code == 422
    assert kitchen.post(url, json={"reason": "Food spilled"}).json()["status"] == "cancelled"
    assert available(listing["id"]) == 2
    assert customer.get("/api/reservations/mine").json()[0]["cancel_reason"] == "Food spilled"


def test_missed_pickups_show_as_missed_and_sweep_marks_no_show():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen)
    customer = customer_client()
    reserve(customer, listing["id"])
    move_listing_to_past(listing["id"])
    with SessionLocal() as session:
        session.execute(
            Reservation.__table__.update().values(pickup_deadline=func.now() - func.make_interval(0, 0, 0, 0, 0, 5))
        )
        session.commit()
    mine = customer.get("/api/reservations/mine").json()[0]
    assert mine["display_status"] == "missed" and mine["can_cancel"] is False
    with SessionLocal() as session:
        assert reservation_service.sweep_no_shows(session) == 1
    assert customer.get("/api/reservations/mine").json()[0]["status"] == "no_show"


# --- The overselling guarantee under real concurrency ------------------------------------------------------


def _make_customers(count: int) -> list[User]:
    with SessionLocal() as session:
        users = [
            User(
                email=unique_email("race"),
                password_hash=hash_password("x" * 12),
                full_name=f"Racer {index}",
                role=UserRole.customer,
            )
            for index in range(count)
        ]
        session.add_all(users)
        session.commit()
        return users


def _race(listing_id: str, customers: list[User], quantity: int = 1) -> list[str]:
    """Fire every reservation at the same instant from separate database connections."""
    race_engine = create_engine(get_settings().database_url, pool_size=len(customers), max_overflow=0)
    make_session = sessionmaker(bind=race_engine, expire_on_commit=False)
    barrier = Barrier(len(customers))

    def attempt(customer: User) -> str:
        with make_session() as session:
            barrier.wait()
            try:
                reservation_service.create(
                    session, customer, ReservationCreate(listing_id=uuid.UUID(listing_id), quantity=quantity)
                )
                return "ok"
            except DomainError as error:
                return error.detail

    try:
        with ThreadPoolExecutor(max_workers=len(customers)) as pool:
            return list(pool.map(attempt, customers))
    finally:
        race_engine.dispose()


@pytest.mark.parametrize("portions", [1, 5])
def test_many_simultaneous_customers_never_oversell(portions):
    kitchen, _ = provider_client()
    listing = create_listing(kitchen, quantity_total=portions, max_per_order=1)
    results = _race(listing["id"], _make_customers(30))

    assert results.count("ok") == portions
    with SessionLocal() as session:
        reserved = session.scalar(
            select(func.sum(Reservation.quantity)).where(Reservation.listing_id == uuid.UUID(listing["id"]))
        )
    assert reserved == portions
    assert available(listing["id"]) == 0


def test_one_customer_tapping_many_times_at_once_gets_one_reservation():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen, quantity_total=10)
    customer = _make_customers(1)[0]
    results = _race(listing["id"], [customer] * 12)
    assert results.count("ok") == 1
    assert available(listing["id"]) == 9
