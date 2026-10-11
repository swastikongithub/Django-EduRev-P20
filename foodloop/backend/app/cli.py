"""Command-line tasks. Run from the backend folder, for example:

python -m app.cli create-admin --email admin@example.com --name "Asha Admin"
python -m app.cli seed-sample        # development only: clearly labelled SAMPLE data
python -m app.cli sweep              # mark missed pickups as no-shows (run every few minutes)
"""

import argparse
import getpass
import sys
from datetime import timedelta

from sqlalchemy import select

from app.clock import today_ist, utcnow
from app.config import get_settings
from app.db import SessionLocal
from app.models import Listing, Provider, ProviderMember, User
from app.models.enums import (
    Diet,
    FssaiKind,
    ListingStatus,
    MealType,
    MemberRole,
    ProviderKind,
    ProviderStatus,
    Storage,
    UserRole,
)
from app.schemas.auth import RegisterRequest
from app.security.passwords import hash_password
from app.services.accounts import unique_slug
from app.services.reservations import sweep_no_shows

# Development-only sample accounts. Printed after seeding; never used in production.
SAMPLE_PASSWORD = "sample-pass-2024"
SAMPLE_PREFIX = "[SAMPLE] "


def create_admin(email: str, name: str, password: str | None) -> None:
    password = password or getpass.getpass("Admin password (min 8 characters): ")
    # Reuse the same validation as public sign-up (length, common passwords, email format).
    data = RegisterRequest(email=email, password=password, full_name=name)
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == data.email))
        if existing:
            existing.role = UserRole.admin
            existing.password_hash = hash_password(data.password)
            print(f"Updated existing user {data.email} to admin.")
        else:
            db.add(
                User(
                    email=data.email,
                    password_hash=hash_password(data.password),
                    full_name=data.full_name,
                    role=UserRole.admin,
                )
            )
            print(f"Created admin {data.email}.")
        db.commit()


def _sample_user(db, email: str, name: str, role: UserRole) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash=hash_password(SAMPLE_PASSWORD), full_name=name, role=role)
        db.add(user)
        db.flush()
    return user


def _sample_kitchen(
    db, owner: User, name: str, kind: ProviderKind, area: str, status: ProviderStatus, instructions: str
) -> Provider:
    full_name = SAMPLE_PREFIX + name
    provider = db.scalar(select(Provider).where(Provider.name == full_name))
    if provider is None:
        provider = Provider(
            name=full_name,
            slug=unique_slug(db, name + " sample"),
            kind=kind,
            description="Sample kitchen for development and demos. Not a real business.",
            address_line="Sample block, ground floor",
            area=area,
            city="Sample City",
            pincode="110001",
            contact_phone="9000000000",
            fssai_number="10000000000000",
            fssai_kind=FssaiKind.registration,
            fssai_valid_until=today_ist() + timedelta(days=365),
            pickup_instructions=instructions,
            status=status,
            is_sample=True,
        )
        db.add(provider)
        db.flush()
        db.add(ProviderMember(provider_id=provider.id, user_id=owner.id, member_role=MemberRole.owner))
    return provider


def seed_sample() -> None:
    if get_settings().app_env == "production":
        sys.exit("Refusing to create sample data in production.")
    now = utcnow()
    with SessionLocal() as db:
        _sample_user(db, "customer@example.com", "Sample Customer", UserRole.customer)
        green_owner = _sample_user(db, "kitchen@example.com", "Sample Canteen Manager", UserRole.provider)
        pending_owner = _sample_user(db, "pending-kitchen@example.com", "Sample PG Owner", UserRole.provider)

        green = _sample_kitchen(
            db,
            green_owner,
            "Green Leaf Canteen",
            ProviderKind.college_canteen,
            "North Campus",
            ProviderStatus.approved,
            "Collect from the side counter next to the billing desk. Show your pickup code.",
        )
        _sample_kitchen(
            db,
            pending_owner,
            "Sunrise PG Kitchen",
            ProviderKind.pg_kitchen,
            "Sector 4",
            ProviderStatus.pending,
            "Ring the bell at the kitchen door.",
        )

        # (title, meal, diet, allergens, original ₹, price ₹, qty, storage, prepared mins ago, pickup starts in,
        #  pickup lasts mins, eat-by after pickup ends mins)
        samples = [
            (
                "Veg thali: dal, sabzi, rice, 2 rotis",
                MealType.lunch,
                Diet.veg,
                ["gluten", "milk"],
                80,
                40,
                12,
                Storage.hot_held,
                60,
                -10,
                75,
                30,
            ),
            (
                "Chicken biryani with raita",
                MealType.lunch,
                Diet.non_veg,
                ["milk"],
                120,
                60,
                6,
                Storage.hot_held,
                50,
                0,
                80,
                30,
            ),
            (
                "Samosa (2 pcs) with green chutney",
                MealType.snacks,
                Diet.veg,
                ["gluten"],
                30,
                15,
                20,
                Storage.room_temp,
                30,
                -5,
                60,
                15,
            ),
            ("Idli sambar (3 idlis)", MealType.breakfast, Diet.vegan, [], 50, 25, 8, Storage.hot_held, 45, 0, 90, 20),
            (
                "Assorted buns and cake slices",
                MealType.bakery,
                Diet.egg,
                ["gluten", "egg", "milk"],
                60,
                25,
                15,
                Storage.shelf_stable,
                120,
                0,
                180,
                120,
            ),
            (
                "Masala chai (flask, 2 cups)",
                MealType.beverages,
                Diet.veg,
                ["milk"],
                30,
                15,
                10,
                Storage.hot_held,
                20,
                15,
                60,
                20,
            ),
        ]
        created = 0
        for (
            title,
            meal,
            diet,
            allergens,
            original,
            price,
            qty,
            storage,
            prepared_ago,
            start_in,
            lasts,
            eat_buffer,
        ) in samples:
            if db.scalar(
                select(Listing.id).where(
                    Listing.provider_id == green.id, Listing.title == title, Listing.pickup_end > now
                )
            ):
                continue
            pickup_start = now + timedelta(minutes=start_in)
            prepared_at = min(now - timedelta(minutes=prepared_ago), pickup_start)
            pickup_end = pickup_start + timedelta(minutes=lasts)
            db.add(
                Listing(
                    provider_id=green.id,
                    title=title,
                    description="Sample listing for development. Not real food.",
                    meal_type=meal,
                    diet=diet,
                    allergens=allergens,
                    allergen_note="Prepared in a kitchen that also handles peanuts and dairy.",
                    original_price_paise=original * 100,
                    price_paise=price * 100,
                    quantity_total=qty,
                    quantity_available=qty,
                    max_per_order=2,
                    storage=storage,
                    prepared_at=prepared_at,
                    pickup_start=pickup_start,
                    pickup_end=pickup_end,
                    safe_until=pickup_end + timedelta(minutes=eat_buffer),
                    status=ListingStatus.active,
                    safety_declared_by=green_owner.id,
                    safety_declared_at=now,
                )
            )
            created += 1
        db.commit()
    print(f"Sample data ready ({created} new listings). Every sample kitchen is labelled {SAMPLE_PREFIX!r}.")
    print(f"Log in with any of these (password: {SAMPLE_PASSWORD}):")
    print("  customer@example.com         customer")
    print("  kitchen@example.com          approved kitchen")
    print("  pending-kitchen@example.com  kitchen waiting for approval")
    print("Create an admin with: python -m app.cli create-admin --email you@example.com --name 'Your Name'")


def sweep() -> None:
    with SessionLocal() as db:
        count = sweep_no_shows(db)
    print(f"Marked {count} missed pickup(s) as no-show.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="FoodLoop admin tasks")
    commands = parser.add_subparsers(dest="command", required=True)

    admin = commands.add_parser("create-admin", help="create (or promote) an admin account")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    admin.add_argument("--password", help="omit to be asked securely")

    commands.add_parser("seed-sample", help="add clearly labelled sample data (development only)")
    commands.add_parser("sweep", help="mark reservations whose pickup window ended as no-shows")

    args = parser.parse_args(argv)
    if args.command == "create-admin":
        create_admin(args.email, args.name, args.password)
    elif args.command == "seed-sample":
        seed_sample()
    elif args.command == "sweep":
        sweep()


if __name__ == "__main__":
    main()
