import io
from datetime import timedelta

from PIL import Image

from app.clock import utcnow
from app.config import get_settings
from app.models.enums import ProviderStatus
from tests.conftest import (
    create_listing,
    customer_client,
    listing_payload,
    move_listing_to_past,
    new_client,
    provider_client,
    set_provider_status,
)


def fields(response) -> set[str]:
    return {error["field"] for error in response.json().get("errors", [])}


def test_published_listing_is_public_with_computed_fields():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen)
    assert listing["status"] == "active"
    assert listing["discount_percent"] == 50
    assert listing["availability"] == "available"

    public = new_client().get("/api/listings").json()
    assert public["total"] == 1
    item = public["items"][0]
    assert item["provider"]["name"] == "Test Canteen"
    assert item["pickup_instructions"] == "Side counter"  # falls back to the kitchen's default
    assert "status" not in item  # internal fields stay private


def test_listing_validation_collects_all_problems():
    kitchen, _ = provider_client()
    now = utcnow()
    response = kitchen.post(
        "/api/provider/listings",
        json=listing_payload(
            price_paise=9000,  # more than the original 8000
            quantity_total=3,
            max_per_order=5,  # more than the quantity of 3
            pickup_end=(now - timedelta(minutes=10)).isoformat(),  # before pickup_start
        ),
    )
    assert response.status_code == 422
    assert {"price_paise", "max_per_order", "pickup_end"} <= fields(response)


def test_food_safety_window_is_enforced_per_storage_type():
    kitchen, _ = provider_client()
    now = utcnow()
    # Room-temperature food: at most 2 hours from preparation to eat-by (pilot policy default).
    response = kitchen.post(
        "/api/provider/listings",
        json=listing_payload(
            storage="room_temp",
            prepared_at=(now - timedelta(hours=2)).isoformat(),
            pickup_start=(now - timedelta(minutes=5)).isoformat(),
            pickup_end=(now + timedelta(minutes=40)).isoformat(),
            safe_until=(now + timedelta(minutes=50)).isoformat(),
        ),
    )
    assert response.status_code == 422
    assert "safe_until" in fields(response)
    # The same timing is fine when the food is kept hot (4 hours).
    response = kitchen.post(
        "/api/provider/listings",
        json=listing_payload(
            storage="hot_held",
            prepared_at=(now - timedelta(hours=2)).isoformat(),
            pickup_start=(now - timedelta(minutes=5)).isoformat(),
            pickup_end=(now + timedelta(minutes=40)).isoformat(),
            safe_until=(now + timedelta(minutes=50)).isoformat(),
        ),
    )
    assert response.status_code == 201, response.text


def test_safety_checklist_and_allergen_choice_are_required():
    kitchen, _ = provider_client()
    unconfirmed = kitchen.post("/api/provider/listings", json=listing_payload(safety_confirmed=False))
    assert unconfirmed.status_code == 422 and "safety_confirmed" in fields(unconfirmed)

    payload = listing_payload()
    del payload["allergens"]
    missing = kitchen.post("/api/provider/listings", json=payload)
    assert missing.status_code == 422 and "allergens" in fields(missing)

    unknown = kitchen.post("/api/provider/listings", json=listing_payload(allergens=["chocolate"]))
    assert unknown.status_code == 422

    none_declared = kitchen.post("/api/provider/listings", json=listing_payload(allergens=[]))
    assert none_declared.status_code == 201


def test_cannot_publish_a_window_that_is_about_to_close():
    kitchen, _ = provider_client()
    now = utcnow()
    response = kitchen.post(
        "/api/provider/listings",
        json=listing_payload(
            pickup_end=(now + timedelta(minutes=8)).isoformat(), safe_until=(now + timedelta(minutes=30)).isoformat()
        ),
    )
    assert response.status_code == 422
    assert "pickup_end" in fields(response)


def test_drafts_and_paused_listings_are_hidden_until_published():
    kitchen, _ = provider_client()
    draft = create_listing(kitchen, publish=False)
    assert draft["status"] == "draft"
    assert new_client().get("/api/listings").json()["total"] == 0
    assert new_client().get(f"/api/listings/{draft['id']}").status_code == 404

    kitchen.post(f"/api/provider/listings/{draft['id']}/status", json={"status": "active"})
    assert new_client().get("/api/listings").json()["total"] == 1
    kitchen.post(f"/api/provider/listings/{draft['id']}/status", json={"status": "paused"})
    assert new_client().get("/api/listings").json()["total"] == 0


def test_listings_of_unapproved_kitchens_are_hidden():
    kitchen, provider_id = provider_client()
    create_listing(kitchen)
    set_provider_status(provider_id, ProviderStatus.pending)
    assert new_client().get("/api/listings").json()["total"] == 0


def test_expired_listings_are_never_listed():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen)
    move_listing_to_past(listing["id"])
    for availability in ("available", "all"):
        assert new_client().get("/api/listings", params={"availability": availability}).json()["total"] == 0
    assert new_client().get(f"/api/listings/{listing['id']}").json()["availability"] == "expired"


def test_search_and_filters():
    kitchen, _ = provider_client()
    create_listing(kitchen, title="Paneer roll", meal_type="snacks", price_paise=3000, original_price_paise=6000)
    create_listing(kitchen, title="Egg curry rice", meal_type="dinner", diet="egg", allergens=["egg"], price_paise=5000)
    create_listing(
        kitchen,
        title="Peanut chikki",
        meal_type="snacks",
        allergens=["peanut"],
        price_paise=1000,
        original_price_paise=2000,
    )
    browse = new_client()

    def titles(**params):
        return sorted(item["title"] for item in browse.get("/api/listings", params=params).json()["items"])

    assert titles(meal_type="snacks") == ["Paneer roll", "Peanut chikki"]
    assert titles(meal_type=["snacks", "dinner"]) == ["Egg curry rice", "Paneer roll", "Peanut chikki"]
    assert titles(diet="egg") == ["Egg curry rice"]
    assert titles(max_price_paise=3000) == ["Paneer roll", "Peanut chikki"]
    assert titles(min_price_paise=4000) == ["Egg curry rice"]
    assert titles(exclude_allergen="peanut") == ["Egg curry rice", "Paneer roll"]
    assert titles(q="paneer") == ["Paneer roll"]
    assert titles(q="test canteen") == ["Egg curry rice", "Paneer roll", "Peanut chikki"]  # kitchen name
    assert titles(q="100%_") == []  # wildcards are treated as plain text
    cheapest = browse.get("/api/listings", params={"sort": "price_low"}).json()["items"][0]
    assert cheapest["title"] == "Peanut chikki"


def test_sold_out_listings_show_only_when_asked():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen, quantity_total=1, max_per_order=1)
    customer_client().post("/api/reservations", json={"listing_id": listing["id"], "quantity": 1})
    assert new_client().get("/api/listings").json()["total"] == 0
    everything = new_client().get("/api/listings", params={"availability": "all"}).json()
    assert everything["items"][0]["availability"] == "sold_out"


def test_kitchens_cannot_touch_each_others_listings():
    kitchen_a, _ = provider_client(name="Kitchen A")
    kitchen_b, _ = provider_client(name="Kitchen B")
    listing = create_listing(kitchen_a)
    assert kitchen_b.get(f"/api/provider/listings/{listing['id']}").status_code == 404
    assert kitchen_b.put(f"/api/provider/listings/{listing['id']}", json=listing_payload()).status_code == 404
    assert kitchen_b.post(f"/api/provider/listings/{listing['id']}/remove", json={}).status_code == 404
    assert kitchen_b.get("/api/provider/listings").json() == []


def test_edit_cannot_drop_quantity_below_what_is_reserved():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen, quantity_total=5)
    customer_client().post("/api/reservations", json={"listing_id": listing["id"], "quantity": 2})

    too_low = kitchen.put(
        f"/api/provider/listings/{listing['id']}", json=listing_payload(quantity_total=1, max_per_order=1)
    )
    assert too_low.status_code == 422
    updated = kitchen.put(f"/api/provider/listings/{listing['id']}", json=listing_payload(quantity_total=8))
    assert updated.status_code == 200
    assert updated.json()["quantity_available"] == 6
    assert updated.json()["reserved_quantity"] == 2


def test_provider_removing_listing_cancels_reservations():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen)
    customer = customer_client()
    customer.post("/api/reservations", json={"listing_id": listing["id"], "quantity": 1})
    response = kitchen.post(f"/api/provider/listings/{listing['id']}/remove", json={"reason": "Dropped the tray"})
    assert response.json()["status"] == "removed"
    reservation = customer.get("/api/reservations/mine").json()[0]
    assert reservation["status"] == "cancelled"
    assert reservation["cancelled_by"] == "provider"
    assert kitchen.put(f"/api/provider/listings/{listing['id']}", json=listing_payload()).status_code == 409


def _photo_bytes(fmt: str = "JPEG") -> bytes:
    image = Image.new("RGB", (2400, 1600), (200, 120, 40))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # camera make: should be stripped
    buffer = io.BytesIO()
    image.save(buffer, fmt, exif=exif)
    return buffer.getvalue()


def test_image_upload_is_validated_resized_and_stripped():
    kitchen, _ = provider_client()
    listing = create_listing(kitchen)
    response = kitchen.post(
        f"/api/provider/listings/{listing['id']}/image",
        files={"image": ("meal.jpg", _photo_bytes(), "image/jpeg")},
        data={"is_representative": "true"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["image_url"].startswith("/media/listings/") and body["image_url"].endswith(".webp")
    assert body["image_is_representative"] is True

    saved = get_settings().media_dir / body["image_url"].removeprefix("/media/")
    with Image.open(saved) as stored:
        assert max(stored.size) == 1200
        assert not stored.getexif()

    fake = kitchen.post(
        f"/api/provider/listings/{listing['id']}/image",
        files={"image": ("evil.jpg", b"<script>alert(1)</script>", "image/jpeg")},
    )
    assert fake.status_code == 422
    assert new_client().get(body["image_url"]).status_code == 200
