"""Command-line tasks. Run from the backend folder, for example:

python -m app.cli create-admin --email admin@example.com --name "Asha Admin"
python -m app.cli seed-sample        # development only: clearly labelled SAMPLE data
python -m app.cli sweep              # mark missed pickups as no-shows (run every few minutes)
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import User
from app.models.enums import ProviderStatus, UserRole
from app.schemas.auth import RegisterRequest
from app.security.passwords import hash_password
from app.services.reservations import sweep_no_shows
from app.services.samples import KITCHENS, SAMPLE_PASSWORD, SAMPLE_PREFIX, seed_samples


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


def seed_sample(quiet: bool = False) -> None:
    if get_settings().app_env == "production":
        sys.exit("Refusing to create sample data in production.")
    with SessionLocal() as db:
        created = seed_samples(db)
    if quiet:
        print(f"    {created} sample dish(es) listed; the rest were already on offer.")
        return
    print(f"Sample data ready ({created} new listings). Every sample kitchen is labelled {SAMPLE_PREFIX!r}.")
    print(f"Log in with any of these (password: {SAMPLE_PASSWORD}):")
    print("  customer@example.com         customer")
    for kitchen in KITCHENS:
        state = "approved kitchen" if kitchen.status == ProviderStatus.approved else "kitchen waiting for approval"
        print(f"  {kitchen.owner_email:<28} {state}: {kitchen.name}")
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

    seed = commands.add_parser("seed-sample", help="add clearly labelled sample data (development only)")
    seed.add_argument("--quiet", action="store_true", help="print one line instead of the account list")
    commands.add_parser("sweep", help="mark reservations whose pickup window ended as no-shows")

    args = parser.parse_args(argv)
    if args.command == "create-admin":
        create_admin(args.email, args.name, args.password)
    elif args.command == "seed-sample":
        seed_sample(args.quiet)
    elif args.command == "sweep":
        sweep()


if __name__ == "__main__":
    main()
