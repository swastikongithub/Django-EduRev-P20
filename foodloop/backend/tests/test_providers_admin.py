import uuid
from datetime import timedelta

from app.clock import today_ist
from app.db import SessionLocal
from app.models import Provider
from tests.conftest import (
    PASSWORD,
    admin_client,
    create_listing,
    customer_client,
    kitchen_payload,
    new_client,
    provider_client,
    unique_email,
)


def test_new_kitchen_is_pending_and_cannot_list_food():
    client, _ = provider_client(approved=False)
    me = client.get("/api/auth/me").json()
    assert me["user"]["role"] == "provider"
    assert me["provider"]["status"] == "pending"
    response = client.post("/api/provider/listings", json={})
    assert response.status_code == 403
    assert "waiting for approval" in response.json()["detail"]


def test_kitchen_registration_validates_fssai_and_pincode():
    client = new_client()
    base = {"email": unique_email(), "password": PASSWORD, "full_name": "Kiran"}
    bad_fssai = client.post(
        "/api/auth/register-provider", json={**base, "kitchen": kitchen_payload(fssai_number="123")}
    )
    assert bad_fssai.status_code == 422
    assert bad_fssai.json()["errors"][0]["field"] == "kitchen.fssai_number"

    expired = (today_ist() - timedelta(days=1)).isoformat()
    response = client.post(
        "/api/auth/register-provider", json={**base, "kitchen": kitchen_payload(fssai_valid_until=expired)}
    )
    assert response.status_code == 422
    assert (
        client.post(
            "/api/auth/register-provider", json={**base, "kitchen": kitchen_payload(pincode="012345")}
        ).status_code
        == 422
    )


def test_role_boundaries():
    anonymous = new_client()
    customer = customer_client()
    kitchen, _ = provider_client()
    assert anonymous.get("/api/provider/listings").status_code == 401
    assert customer.get("/api/provider/listings").status_code == 403
    assert customer.get("/api/admin/overview").status_code == 403
    assert kitchen.get("/api/admin/overview").status_code == 403
    assert kitchen.post("/api/reservations", json={"listing_id": str(uuid.uuid4()), "quantity": 1}).status_code == 403


def test_admin_approves_rejects_and_lists_pending_first():
    admin = admin_client()
    _, approved_id = provider_client(approved=False, name="Alpha Canteen")
    _, rejected_id = provider_client(approved=False, name="Beta Mess")

    rows = admin.get("/api/admin/providers").json()
    assert {row["status"] for row in rows} == {"pending"}
    assert rows[0]["owner_email"].startswith("kitchen-")

    assert admin.post(f"/api/admin/providers/{approved_id}/approve").json()["status"] == "approved"
    assert admin.post(f"/api/admin/providers/{rejected_id}/reject", json={"reason": ""}).status_code == 422
    rejected = admin.post(f"/api/admin/providers/{rejected_id}/reject", json={"reason": "FSSAI number not found"})
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["status_reason"] == "FSSAI number not found"

    activity = admin.get("/api/admin/overview").json()["recent_activity"]
    assert {entry["action"] for entry in activity} >= {"provider.approved", "provider.rejected"}


def test_cannot_approve_with_expired_fssai():
    admin = admin_client()
    _, provider_id = provider_client(approved=False)
    with SessionLocal() as session:
        session.get(Provider, uuid.UUID(provider_id)).fssai_valid_until = today_ist() - timedelta(days=1)
        session.commit()
    response = admin.post(f"/api/admin/providers/{provider_id}/approve")
    assert response.status_code == 409


def test_changing_fssai_details_sends_kitchen_back_for_review():
    kitchen, _ = provider_client()
    response = kitchen.put("/api/provider/me", json=kitchen_payload(pickup_instructions="Back door"))
    assert response.json()["status"] == "approved"  # harmless change
    response = kitchen.put("/api/provider/me", json=kitchen_payload(fssai_number="99999999999999"))
    assert response.json()["status"] == "pending"


def test_suspension_hides_listings_and_cancels_open_reservations():
    admin = admin_client()
    kitchen, provider_id = provider_client()
    listing = create_listing(kitchen)
    customer = customer_client()
    reservation = customer.post("/api/reservations", json={"listing_id": listing["id"], "quantity": 1}).json()

    response = admin.post(f"/api/admin/providers/{provider_id}/suspend", json={"reason": "Hygiene complaint"})
    assert response.json()["status"] == "suspended"

    assert customer.get("/api/listings").json()["total"] == 0
    assert customer.get(f"/api/listings/{listing['id']}").status_code == 404
    mine = customer.get(f"/api/reservations/{reservation['id']}").json()
    assert mine["status"] == "cancelled"
    assert mine["cancelled_by"] == "admin"
    assert "Hygiene complaint" in mine["cancel_reason"]
    assert kitchen.post("/api/provider/listings", json={}).status_code == 403


def test_admin_removes_listing_and_overview_counts():
    admin = admin_client()
    kitchen, _ = provider_client()
    listing = create_listing(kitchen)
    customer = customer_client()
    customer.post("/api/reservations", json={"listing_id": listing["id"], "quantity": 2})

    overview = admin.get("/api/admin/overview").json()
    assert overview["live_listings"] == 1
    assert overview["portions_reserved_today"]["reserved"] == 2
    assert overview["customers"] == 1

    live = admin.get("/api/admin/listings", params={"status": "live"}).json()
    assert live["total"] == 1
    removed = admin.post(f"/api/admin/listings/{listing['id']}/remove", json={"reason": "Wrong allergen info"})
    assert removed.json()["status"] == "removed"
    assert customer.get("/api/reservations/mine").json()[0]["status"] == "cancelled"
    assert customer.get("/api/listings").json()["total"] == 0
    assert admin.post(f"/api/admin/listings/{listing['id']}/remove", json={"reason": "again"}).status_code == 409
