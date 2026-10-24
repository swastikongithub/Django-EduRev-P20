"""Kitchen pages, the contact form, and editing your own account."""

from tests.conftest import (
    PASSWORD,
    admin_client,
    create_listing,
    customer_client,
    new_client,
    provider_client,
    unique_email,
)


def test_kitchen_pages_show_only_approved_kitchens_with_live_food():
    kitchen, _ = provider_client(name="Annapurna Canteen")
    create_listing(kitchen, price_paise=3000)
    create_listing(kitchen, price_paise=2000, title="Lemon rice")
    provider_client(approved=False, name="Waiting Kitchen")

    public = new_client()
    kitchens = public.get("/api/kitchens").json()
    assert [k["name"] for k in kitchens] == ["Annapurna Canteen"]
    card = kitchens[0]
    assert card["live_meals"] == 2 and card["lowest_price_paise"] == 2000

    detail = public.get(f"/api/kitchens/{card['slug']}")
    assert detail.status_code == 200 and detail.json()["fssai_number"]
    assert public.get("/api/kitchens/does-not-exist").status_code == 404

    meals = public.get("/api/listings", params={"kitchen": card["slug"]}).json()
    assert meals["total"] == 2
    assert public.get("/api/listings", params={"kitchen": "someone-else"}).json()["total"] == 0


def test_contact_form_reaches_the_admin_inbox():
    public = new_client()
    message = {"name": "Meera", "email": "Meera@Example.com", "topic": "kitchen", "message": "How do I list my mess?"}
    assert public.post("/api/contact", json=message).status_code == 201

    admin = admin_client()
    inbox = admin.get("/api/admin/messages").json()
    assert len(inbox) == 1 and inbox[0]["email"] == "meera@example.com"
    assert admin.get("/api/admin/overview").json()["open_messages"] == 1
    assert admin.post(f"/api/admin/messages/{inbox[0]['id']}/handled").json()["handled_at"]
    assert admin.get("/api/admin/messages").json() == []
    assert len(admin.get("/api/admin/messages", params={"status": "all"}).json()) == 1
    assert customer_client().get("/api/admin/messages").status_code == 403


def test_contact_form_validates_and_drops_bot_messages():
    public = new_client()
    short = public.post("/api/contact", json={"name": "A", "email": "x@example.com", "topic": "other", "message": "hi"})
    assert short.status_code == 422
    assert {e["field"] for e in short.json()["errors"]} >= {"name", "topic", "message"}
    bot = {"name": "Spam Bot", "email": "bot@example.com", "topic": "question", "message": "Buy cheap things now!!"}
    assert public.post("/api/contact", json={**bot, "website": "http://spam.example"}).status_code == 201
    assert admin_client().get("/api/admin/messages").json() == []


def test_edit_profile():
    customer = customer_client()
    me = customer.put("/api/auth/me", json={"full_name": "Riya Sharma", "phone": "+91 98765 43210"}).json()
    assert me["user"]["full_name"] == "Riya Sharma" and me["user"]["phone"] == "9876543210"
    assert customer.put("/api/auth/me", json={"full_name": "Riya Sharma", "phone": ""}).json()["user"]["phone"] is None
    assert customer.put("/api/auth/me", json={"full_name": "Riya", "phone": "12345"}).status_code == 422
    assert new_client().put("/api/auth/me", json={"full_name": "Nobody"}).status_code == 401


def test_change_password_logs_out_other_browsers():
    email = unique_email("riya")
    first = new_client()
    first.post("/api/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Riya"})
    second = new_client()
    assert second.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200

    wrong = first.post("/api/auth/change-password", json={"current_password": "nope", "new_password": "new-lunch-2026"})
    assert wrong.status_code == 400 and wrong.json()["errors"][0]["field"] == "current_password"
    weak = first.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "password"})
    assert weak.status_code == 422

    ok = first.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "new-lunch-2026"})
    assert ok.status_code == 204
    assert first.get("/api/auth/me").json() is not None  # this browser stays logged in
    assert second.get("/api/auth/me").json() is None  # the other one is logged out
    assert new_client().post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    assert new_client().post("/api/auth/login", json={"email": email, "password": "new-lunch-2026"}).status_code == 200
