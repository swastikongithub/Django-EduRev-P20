"""Test setup. Tests run against a REAL PostgreSQL database (foodloop_test), because FoodLoop's safety
guarantees (no overselling, no duplicates) are enforced by PostgreSQL itself. SQLite would not test them.
"""

import os
import tempfile
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# --- Point the app at the test database BEFORE importing it -------------------------------------------------
from app.config import Settings, get_settings

_test_url = os.environ.get("TEST_DATABASE_URL") or Settings().test_database_url
_test_url = Settings(database_url=_test_url).database_url  # normalise the driver prefix
if not (make_url(_test_url).database or "").endswith("_test"):
    raise RuntimeError(f"Refusing to run: the test database name must end in '_test' (got {_test_url!r}).")
os.environ["DATABASE_URL"] = _test_url
os.environ["APP_ENV"] = "test"
os.environ["MEDIA_DIR"] = tempfile.mkdtemp(prefix="foodloop-media-")
get_settings.cache_clear()

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from alembic import command  # noqa: E402
from app.clock import utcnow  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Provider, User  # noqa: E402
from app.models.enums import ProviderStatus, UserRole  # noqa: E402
from app.security.passwords import hash_password  # noqa: E402
from app.security.rate_limit import limiter  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
PASSWORD = "correct-horse-battery"
TABLES = "audit_log, contact_messages, reservations, listings, provider_members, providers, sessions, users"


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    """Build the schema from scratch with the real migrations, so the migrations are tested too."""
    admin_engine = create_engine(_test_url)
    with admin_engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    admin_engine.dispose()
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", _test_url.replace("%", "%%"))
    command.upgrade(config, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    yield
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    limiter.reset()


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def new_client() -> TestClient:
    # Same origin as the API, like the production website.
    return TestClient(app, base_url="http://testserver")


@pytest.fixture
def client() -> TestClient:
    return new_client()


# --- Factories ----------------------------------------------------------------------------------------------


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def kitchen_payload(**overrides) -> dict:
    payload = {
        "name": "Test Canteen",
        "kind": "college_canteen",
        "address_line": "Block 12, ground floor",
        "area": "North Campus",
        "city": "Pune",
        "pincode": "411001",
        "contact_phone": "9876543210",
        "fssai_number": "12345678901234",
        "fssai_kind": "registration",
        "fssai_valid_until": (utcnow() + timedelta(days=300)).date().isoformat(),
        "pickup_instructions": "Side counter",
    }
    payload.update(overrides)
    return payload


def customer_client(name: str = "Riya Customer") -> TestClient:
    client = new_client()
    response = client.post(
        "/api/auth/register", json={"email": unique_email("customer"), "password": PASSWORD, "full_name": name}
    )
    assert response.status_code == 201, response.text
    return client


def provider_client(*, approved: bool = True, **kitchen) -> tuple[TestClient, str]:
    client = new_client()
    response = client.post(
        "/api/auth/register-provider",
        json={
            "email": unique_email("kitchen"),
            "password": PASSWORD,
            "full_name": "Kiran Kitchen",
            "kitchen": kitchen_payload(**kitchen),
        },
    )
    assert response.status_code == 201, response.text
    provider_id = response.json()["provider"]["id"]
    if approved:
        set_provider_status(provider_id, ProviderStatus.approved)
    return client, provider_id


def admin_client() -> TestClient:
    email = unique_email("admin")
    with SessionLocal() as session:
        session.add(
            User(email=email, password_hash=hash_password(PASSWORD), full_name="Ada Admin", role=UserRole.admin)
        )
        session.commit()
    client = new_client()
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


def set_provider_status(provider_id: str, status: ProviderStatus) -> None:
    with SessionLocal() as session:
        session.get(Provider, uuid.UUID(provider_id)).status = status
        session.commit()


def listing_payload(**overrides) -> dict:
    now = utcnow()
    payload = {
        "title": "Veg thali",
        "description": "Dal, sabzi, rice and two rotis",
        "meal_type": "lunch",
        "diet": "veg",
        "allergens": ["gluten", "milk"],
        "allergen_note": "",
        "original_price_paise": 8000,
        "price_paise": 4000,
        "quantity_total": 10,
        "max_per_order": 2,
        "storage": "hot_held",
        "prepared_at": (now - timedelta(minutes=30)).isoformat(),
        "pickup_start": (now - timedelta(minutes=5)).isoformat(),
        "pickup_end": (now + timedelta(minutes=60)).isoformat(),
        "safe_until": (now + timedelta(minutes=90)).isoformat(),
        "safety_confirmed": True,
    }
    payload.update(overrides)
    return payload


def create_listing(client: TestClient, **overrides) -> dict:
    response = client.post("/api/provider/listings", json=listing_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def move_listing_to_past(listing_id: str, minutes_ago: int = 5) -> None:
    """Make a listing's pickup window end `minutes_ago` minutes ago (keeping the times in valid order)."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE listings SET prepared_at = now() - interval '3 hours', "
                "pickup_start = now() - interval '2 hours', "
                "pickup_end = now() - make_interval(mins => :m), safe_until = now() - make_interval(mins => :m) "
                "WHERE id = :id"
            ),
            {"m": minutes_ago, "id": listing_id},
        )


def set_listing_times(listing_id: str, *, pickup_end_in_minutes: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE listings SET pickup_end = now() + make_interval(mins => :m), "
                "safe_until = now() + make_interval(mins => :m + 30) WHERE id = :id"
            ),
            {"m": pickup_end_in_minutes, "id": listing_id},
        )
