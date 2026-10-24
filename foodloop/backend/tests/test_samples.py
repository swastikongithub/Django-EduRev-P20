"""Sample data: a full, valid menu from clearly labelled sample kitchens, kept fresh only for sample kitchens."""

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Listing, Provider
from app.services.samples import KITCHENS, MENU, refresh_sample_menu, seed_samples
from tests.conftest import create_listing, move_listing_to_past, new_client, provider_client


def test_seed_lists_the_whole_menu_publicly(db):
    created = seed_samples(db)
    assert created == len(MENU) >= 30
    page = new_client().get("/api/listings", params={"limit": 60}).json()
    assert page["total"] == len(MENU)
    assert all(item["provider"]["is_sample"] for item in page["items"])
    assert all(item["provider"]["name"].startswith("[SAMPLE] ") for item in page["items"])
    assert {item["meal_type"] for item in page["items"]} == {
        "breakfast",
        "lunch",
        "snacks",
        "dinner",
        "bakery",
        "beverages",
    }
    assert all(
        item["availability"] == "available" and item["price_paise"] < item["original_price_paise"]
        for item in page["items"]
    )
    # The kitchen that's waiting for approval has nothing on sale.
    pending = [kitchen.name for kitchen in KITCHENS if kitchen.status.value == "pending"]
    assert not [item for item in page["items"] if item["provider"]["name"].endswith(pending[0])]


def test_seed_is_idempotent(db):
    seed_samples(db)
    assert seed_samples(db) == 0
    assert db.scalar(select(Listing.id).where(Listing.title == MENU[0].title).limit(1))


def test_refresh_relists_only_ended_sample_dishes(db):
    seed_samples(db)
    dish = db.scalars(select(Listing).where(Listing.title == MENU[0].title)).first()
    move_listing_to_past(str(dish.id))
    assert refresh_sample_menu(db) == 1


def test_refresh_never_touches_real_kitchens(db):
    seed_samples(db)
    kitchen, _ = provider_client()
    real = create_listing(kitchen, title=MENU[0].title)
    move_listing_to_past(real["id"])
    before = db.scalar(select(Provider.id).where(Provider.is_sample.is_(False)))
    refresh_sample_menu(db)
    real_titles = db.scalars(select(Listing.title).where(Listing.provider_id == before)).all()
    assert real_titles == [MENU[0].title]  # still just the one, ended listing


def test_refuses_in_production(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    with pytest.raises(RuntimeError):
        seed_samples(db)
