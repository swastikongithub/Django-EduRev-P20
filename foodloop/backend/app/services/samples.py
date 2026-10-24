"""Sample data for development and demos: five clearly labelled sample kitchens and a full menu.

Every sample kitchen is named "[SAMPLE] ..." and flagged is_sample, so the website shows a "Sample data" badge.
Every dish goes through the same safety validation as a real kitchen's listing, so sample food never breaks
FoodLoop's rules (storage time limits, pickup before eat-by, and so on).

In development, `start_sample_refresher` re-lists sample dishes whose pickup window has ended, so a local
copy of the site always has food on it. It only ever touches sample kitchens and never runs in production.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import today_ist, utcnow
from app.config import get_settings
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
from app.security.passwords import hash_password
from app.services.accounts import unique_slug
from app.services.listings import validate_listing

log = logging.getLogger("foodloop.samples")

SAMPLE_PASSWORD = "sample-pass-2024"  # noqa: S105 - development-only sample logins, shown to the developer
SAMPLE_PREFIX = "[SAMPLE] "
REFRESH_EVERY_SECONDS = 300


@dataclass(frozen=True)
class SampleKitchen:
    key: str
    name: str
    kind: ProviderKind
    area: str
    owner_email: str
    owner_name: str
    description: str
    instructions: str
    status: ProviderStatus = ProviderStatus.approved


# fmt: off
KITCHENS = [
    SampleKitchen(
        "green", "Green Leaf Canteen", ProviderKind.college_canteen, "North Campus",
        "kitchen@example.com", "Sample Canteen Manager",
        "North Indian lunches and evening snacks, cooked fresh every day in the campus canteen.",
        "Collect from the side counter next to the billing desk. Show your pickup code.",
    ),
    SampleKitchen(
        "tiffin", "Dakshin Tiffin Corner", ProviderKind.cafeteria, "Tech Park, Block B",
        "tiffin@example.com", "Sample Tiffin Owner",
        "South Indian breakfast all morning: idli, dosa, vada and strong filter coffee.",
        "Ground floor food court, counter 3. Show your pickup code.",
    ),
    SampleKitchen(
        "bakery", "Crumbs Bakery Café", ProviderKind.other, "City Centre",
        "bakery@example.com", "Sample Bakery Owner",
        "Breads, puffs, brownies and cold coffee from a small neighbourhood bakery.",
        "Ask at the cash counter. Show your pickup code.",
    ),
    SampleKitchen(
        "mess", "Hostel 7 Mess", ProviderKind.hostel_mess, "South Campus",
        "mess@example.com", "Sample Mess Manager",
        "Hearty dinners for hostel residents: biryani, curries and thalis.",
        "Mess hall side door, 7 to 10 pm. Show your pickup code.",
    ),
    SampleKitchen(
        "chai", "Chai Adda", ProviderKind.cafeteria, "Metro Station Road",
        "chai@example.com", "Sample Café Owner",
        "Street-style snacks and chai: vada pav, pav bhaji, momos and lassi.",
        "Pickup window at the front. Show your pickup code.",
    ),
    SampleKitchen(
        "pending", "Sunrise PG Kitchen", ProviderKind.pg_kitchen, "Sector 4",
        "pending-kitchen@example.com", "Sample PG Owner",
        "Home-style meals for PG residents. Waiting for FoodLoop's approval.",
        "Ring the bell at the kitchen door.",
        ProviderStatus.pending,
    ),
]
# fmt: on

# When a sample dish is cooked and picked up, relative to "now", in minutes:
# (prepared ago, pickup starts in, pickup lasts, eat-by after pickup ends). Each one is within the storage
# limit for its kind of food (hot 4 h, room temperature 2 h, refrigerated 24 h, shelf-stable 48 h).
# fmt: off
TIMING = {
    "hot": (40, -10, 150, 30),        # pickup open now, about 2.5 hours left
    "hot_soon": (90, -60, 95, 20),    # closing soon: reservations close in about 25 minutes
    "hot_later": (15, 45, 120, 30),   # pickup opens in 45 minutes
    "room": (20, -5, 70, 20),         # room temperature: about an hour left
    "room_soon": (50, -30, 60, 15),   # room temperature, closing soon
    "cold": (120, -30, 360, 120),     # refrigerated: open for about 5.5 hours
    "shelf": (180, -60, 600, 600),    # bakery and packaged: open for about 9 hours
}
STORAGE_FOR = {
    "hot": Storage.hot_held, "hot_soon": Storage.hot_held, "hot_later": Storage.hot_held,
    "room": Storage.room_temp, "room_soon": Storage.room_temp,
    "cold": Storage.refrigerated, "shelf": Storage.shelf_stable,
}
# fmt: on


@dataclass(frozen=True)
class SampleDish:
    kitchen: str
    title: str
    description: str
    meal_type: MealType
    diet: Diet
    allergens: tuple[str, ...]
    original: int  # ₹
    price: int  # ₹
    quantity: int
    timing: str


# fmt: off
B, L, S, D = MealType.breakfast, MealType.lunch, MealType.snacks, MealType.dinner
K, V = MealType.bakery, MealType.beverages
VEG, VEGAN, EGG, NONVEG = Diet.veg, Diet.vegan, Diet.egg, Diet.non_veg
# fmt: on

# fmt: off
MENU = [
    # Green Leaf Canteen: lunch and snacks
    SampleDish("green", "Veg thali: dal, sabzi, rice, 2 rotis",
               "Dal tadka, seasonal sabzi, jeera rice, two rotis and salad.",
               L, VEG, ("gluten", "milk"), 80, 40, 12, "hot"),
    SampleDish("green", "Rajma chawal",
               "Slow-cooked kidney bean curry with steamed basmati rice and onion salad.",
               L, VEG, (), 70, 35, 10, "hot"),
    SampleDish("green", "Chole bhature (2 bhature)",
               "Spicy chickpea curry with two fluffy bhature, pickle and onions.",
               L, VEG, ("gluten", "milk"), 90, 45, 8, "hot_soon"),
    SampleDish("green", "Paneer butter masala with 2 rotis",
               "Paneer in a creamy tomato gravy, with two butter rotis.",
               L, VEG, ("gluten", "milk", "tree_nut"), 110, 55, 8, "hot"),
    SampleDish("green", "Samosa (2 pcs) with green chutney",
               "Crisp potato-and-pea samosas with mint chutney.",
               S, VEG, ("gluten",), 30, 15, 20, "room"),
    SampleDish("green", "Veg hakka noodles",
               "Wok-tossed noodles with cabbage, carrot, capsicum and spring onion.",
               S, VEG, ("gluten", "soy"), 70, 35, 10, "hot"),
    SampleDish("green", "Masala chai (flask, 2 cups)",
               "Ginger and cardamom chai, enough for two cups.",
               V, VEG, ("milk",), 30, 15, 10, "hot"),
    # Dakshin Tiffin Corner: South Indian breakfast
    SampleDish("tiffin", "Idli sambar (3 idlis)",
               "Three soft idlis with sambar and coconut chutney.",
               B, VEGAN, (), 50, 25, 10, "hot"),
    SampleDish("tiffin", "Masala dosa with chutney",
               "Crisp dosa with spiced potato filling, sambar and two chutneys.",
               B, VEGAN, (), 70, 35, 8, "hot_soon"),
    SampleDish("tiffin", "Medu vada (2 pcs) with sambar",
               "Crunchy lentil vadas, dunked in sambar.",
               B, VEGAN, (), 45, 22, 10, "hot"),
    SampleDish("tiffin", "Poha with sev",
               "Flattened rice with onion, peanuts, curry leaves and a squeeze of lemon.",
               B, VEGAN, ("peanut",), 35, 18, 12, "hot"),
    SampleDish("tiffin", "Rava upma",
               "Semolina cooked with vegetables, mustard seeds and ghee.",
               B, VEG, ("gluten", "milk"), 40, 20, 10, "hot_later"),
    SampleDish("tiffin", "Filter coffee",
               "Strong South Indian filter coffee with frothy milk.",
               V, VEG, ("milk",), 35, 18, 15, "hot"),
    SampleDish("tiffin", "Curd rice",
               "Cool curd rice tempered with mustard seeds and curry leaves.",
               L, VEG, ("milk",), 60, 30, 8, "cold"),
    # Crumbs Bakery Café: bakery and cold drinks
    SampleDish("bakery", "Chocolate brownie (2 pcs)",
               "Fudgy chocolate brownies, baked this morning.",
               K, EGG, ("gluten", "egg", "milk"), 90, 45, 12, "shelf"),
    SampleDish("bakery", "Butter croissant",
               "Flaky all-butter croissant.",
               K, EGG, ("gluten", "egg", "milk"), 70, 35, 10, "shelf"),
    SampleDish("bakery", "Veg puff (2 pcs)",
               "Puff pastry filled with spiced mixed vegetables.",
               K, VEG, ("gluten", "milk"), 40, 20, 15, "shelf"),
    SampleDish("bakery", "Assorted buns and cake slices",
               "A mixed box of today's soft buns and sponge cake slices.",
               K, EGG, ("gluten", "egg", "milk"), 60, 25, 15, "shelf"),
    SampleDish("bakery", "Paneer tikka sandwich",
               "Grilled sandwich with paneer tikka, onion and mint mayo.",
               S, VEG, ("gluten", "milk"), 80, 40, 8, "cold"),
    SampleDish("bakery", "Cold coffee",
               "Chilled blended coffee with milk.",
               V, VEG, ("milk",), 90, 45, 10, "cold"),
    SampleDish("bakery", "Fresh fruit bowl",
               "Seasonal cut fruit: papaya, pineapple, apple and pomegranate.",
               B, VEGAN, (), 80, 40, 8, "cold"),
    # Hostel 7 Mess: dinner
    SampleDish("mess", "Chicken biryani with raita",
               "Fragrant dum biryani with tender chicken, served with raita.",
               D, NONVEG, ("milk",), 120, 60, 10, "hot"),
    SampleDish("mess", "Veg biryani with raita",
               "Basmati rice layered with vegetables and whole spices, with raita.",
               D, VEG, ("milk",), 100, 50, 10, "hot_later"),
    SampleDish("mess", "Dinner thali: dal makhani, jeera rice, 2 rotis",
               "Dal makhani, jeera rice, two rotis, sabzi and salad.",
               D, VEG, ("gluten", "milk"), 90, 45, 12, "hot"),
    SampleDish("mess", "Egg curry with rice",
               "Two boiled eggs in a spicy onion-tomato curry, with steamed rice.",
               D, EGG, ("egg",), 80, 40, 8, "hot"),
    SampleDish("mess", "Chicken curry with 2 rotis",
               "Home-style chicken curry with two rotis.",
               D, NONVEG, ("gluten", "milk"), 120, 60, 8, "hot_soon"),
    SampleDish("mess", "Aloo paratha with curd (2 pcs)",
               "Two stuffed potato parathas with curd and pickle.",
               B, VEG, ("gluten", "milk"), 60, 30, 10, "hot"),
    SampleDish("mess", "Gulab jamun (2 pcs)",
               "Soft gulab jamuns in warm sugar syrup.",
               S, VEG, ("milk", "gluten"), 40, 20, 15, "room"),
    # Chai Adda: street snacks and drinks
    SampleDish("chai", "Vada pav (2 pcs)",
               "Spiced potato vada in a soft pav with garlic and green chutneys.",
               S, VEG, ("gluten",), 40, 20, 15, "room"),
    SampleDish("chai", "Pav bhaji",
               "Buttery mashed-vegetable bhaji with two toasted pavs.",
               S, VEG, ("gluten", "milk"), 90, 45, 10, "hot"),
    SampleDish("chai", "Veg momos (8 pcs)",
               "Steamed vegetable momos with spicy red chutney.",
               S, VEG, ("gluten", "soy"), 80, 40, 10, "hot_soon"),
    SampleDish("chai", "Sweet lassi",
               "Thick, chilled sweet lassi.",
               V, VEG, ("milk",), 50, 25, 12, "cold"),
    SampleDish("chai", "Fresh lime soda",
               "Sweet-and-salty fresh lime soda.",
               V, VEGAN, (), 40, 20, 15, "cold"),
    SampleDish("chai", "Bread pakora (2 pcs)",
               "Bread slices stuffed with spiced potato, fried in gram-flour batter.",
               S, VEG, ("gluten",), 40, 20, 12, "room_soon"),
]
# fmt: on


# ----------------------------------------------------------------------------------------------- seeding


def _user(db: Session, email: str, name: str, role: UserRole) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash=hash_password(SAMPLE_PASSWORD), full_name=name, role=role)
        db.add(user)
        db.flush()
    return user


def _kitchen(db: Session, sample: SampleKitchen) -> Provider:
    owner = _user(db, sample.owner_email, sample.owner_name, UserRole.provider)
    provider = db.scalar(select(Provider).where(Provider.name == SAMPLE_PREFIX + sample.name))
    if provider is None:
        provider = Provider(
            name=SAMPLE_PREFIX + sample.name,
            slug=unique_slug(db, sample.name + " sample"),
            kind=sample.kind,
            description=sample.description,
            address_line="Sample block, ground floor",
            area=sample.area,
            city="Sample City",
            pincode="110001",
            contact_phone="9000000000",
            fssai_number="10000000000000",
            fssai_kind=FssaiKind.registration,
            fssai_valid_until=today_ist() + timedelta(days=365),
            pickup_instructions=sample.instructions,
            status=sample.status,
            is_sample=True,
        )
        db.add(provider)
        db.flush()
        db.add(ProviderMember(provider_id=provider.id, user_id=owner.id, member_role=MemberRole.owner))
    else:
        provider.description = sample.description
    return provider


def _sample_kitchens(db: Session) -> dict[str, Provider]:
    names = {SAMPLE_PREFIX + sample.name: sample.key for sample in KITCHENS}
    providers = db.scalars(select(Provider).where(Provider.is_sample.is_(True), Provider.name.in_(names))).all()
    return {names[provider.name]: provider for provider in providers}


def _owner_id(db: Session, provider: Provider):
    return db.scalar(select(ProviderMember.user_id).where(ProviderMember.provider_id == provider.id))


def refresh_sample_menu(db: Session, now: datetime | None = None) -> int:
    """List every sample dish that can no longer be reserved. Returns how many listings were created.

    Only approved sample kitchens are touched. A dish that is still on offer (even if sold out) is left alone.
    """
    now = now or utcnow()
    kitchens = _sample_kitchens(db)
    # A dish is re-listed only once its last listing stops taking reservations, so it never shows up twice.
    still_open_after = now + timedelta(minutes=get_settings().reservation_cutoff_minutes)
    created = 0
    for dish in MENU:
        provider = kitchens.get(dish.kitchen)
        if provider is None or provider.status != ProviderStatus.approved:
            continue
        open_listing = db.scalar(
            select(Listing.id).where(
                Listing.provider_id == provider.id,
                Listing.title == dish.title,
                Listing.status == ListingStatus.active,
                Listing.pickup_end > still_open_after,
            )
        )
        if open_listing:
            continue
        prepared_ago, start_in, lasts, eat_buffer = TIMING[dish.timing]
        pickup_start = now + timedelta(minutes=start_in)
        pickup_end = pickup_start + timedelta(minutes=lasts)
        listing = Listing(
            provider_id=provider.id,
            title=dish.title,
            description=dish.description,
            meal_type=dish.meal_type,
            diet=dish.diet,
            allergens=list(dish.allergens),
            allergen_note="Prepared in a kitchen that also handles peanuts, gluten and dairy.",
            original_price_paise=dish.original * 100,
            price_paise=dish.price * 100,
            quantity_total=dish.quantity,
            quantity_available=dish.quantity,
            max_per_order=min(3, dish.quantity),
            storage=STORAGE_FOR[dish.timing],
            prepared_at=now - timedelta(minutes=prepared_ago),
            pickup_start=pickup_start,
            pickup_end=pickup_end,
            safe_until=pickup_end + timedelta(minutes=eat_buffer),
            status=ListingStatus.active,
            safety_declared_by=_owner_id(db, provider),
            safety_declared_at=now,
        )
        validate_listing(listing, now, publishing=True)  # same rules as a real kitchen; raises if broken
        db.add(listing)
        created += 1
    db.commit()
    return created


def seed_samples(db: Session) -> int:
    """Create the sample accounts and kitchens if they're missing, then list the menu."""
    if get_settings().app_env == "production":
        raise RuntimeError("Refusing to create sample data in production.")
    _user(db, "customer@example.com", "Sample Customer", UserRole.customer)
    for sample in KITCHENS:
        _kitchen(db, sample)
    db.commit()
    return refresh_sample_menu(db)


# ---------------------------------------------------------------------------------- development refresher


def start_sample_refresher(session_factory) -> threading.Event:
    """Development only: keep sample dishes listed. Returns an Event; set it to stop the thread."""
    stop = threading.Event()

    def loop() -> None:
        delay = 5  # first check shortly after start-up, then every few minutes
        while not stop.wait(delay):
            delay = REFRESH_EVERY_SECONDS
            try:
                with session_factory() as db:
                    if _sample_kitchens(db):  # only after `seed-sample` has been run once
                        created = refresh_sample_menu(db)
                        if created:
                            log.info("Re-listed %d sample dish(es) so the local site always has food.", created)
            except Exception:  # noqa: BLE001 - the database may be down; try again next round
                log.debug("Sample refresh skipped this round.", exc_info=True)

    threading.Thread(target=loop, name="sample-refresher", daemon=True).start()
    return stop
