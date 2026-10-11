"""Fixed lists of allowed values. The database enforces the same lists with CHECK constraints."""

from enum import StrEnum


class UserRole(StrEnum):
    customer = "customer"
    provider = "provider"
    admin = "admin"


class ProviderKind(StrEnum):
    college_canteen = "college_canteen"
    cafeteria = "cafeteria"
    hostel_mess = "hostel_mess"
    pg_kitchen = "pg_kitchen"
    other = "other"


class FssaiKind(StrEnum):
    registration = "registration"
    state_licence = "state_licence"
    central_licence = "central_licence"


class ProviderStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    suspended = "suspended"


class MemberRole(StrEnum):
    owner = "owner"
    staff = "staff"


class MealType(StrEnum):
    breakfast = "breakfast"
    lunch = "lunch"
    snacks = "snacks"
    dinner = "dinner"
    bakery = "bakery"
    beverages = "beverages"


class Diet(StrEnum):
    veg = "veg"
    egg = "egg"
    non_veg = "non_veg"
    vegan = "vegan"


class Storage(StrEnum):
    hot_held = "hot_held"
    refrigerated = "refrigerated"
    room_temp = "room_temp"
    shelf_stable = "shelf_stable"


class ListingStatus(StrEnum):
    draft = "draft"
    active = "active"
    paused = "paused"
    removed = "removed"


class ReservationStatus(StrEnum):
    reserved = "reserved"
    collected = "collected"
    cancelled = "cancelled"
    no_show = "no_show"


class CancelledBy(StrEnum):
    customer = "customer"
    provider = "provider"
    admin = "admin"
    system = "system"


class PaymentMethod(StrEnum):
    pay_at_pickup = "pay_at_pickup"
    mock_online = "mock_online"


class PaymentStatus(StrEnum):
    unpaid = "unpaid"
    paid = "paid"
    refunded = "refunded"


class Allergen(StrEnum):
    gluten = "gluten"
    crustacean = "crustacean"
    egg = "egg"
    fish = "fish"
    peanut = "peanut"
    tree_nut = "tree_nut"
    soy = "soy"
    milk = "milk"
    sulphite = "sulphite"
    sesame = "sesame"
    mustard = "mustard"


# Human-friendly labels, served to the frontend by GET /api/meta so they live in one place.
LABELS: dict[str, dict[str, str]] = {
    "provider_kind": {
        "college_canteen": "College canteen",
        "cafeteria": "Office cafeteria",
        "hostel_mess": "Hostel mess",
        "pg_kitchen": "PG kitchen",
        "other": "Other kitchen",
    },
    "fssai_kind": {
        "registration": "FSSAI basic registration",
        "state_licence": "FSSAI state licence",
        "central_licence": "FSSAI central licence",
    },
    "meal_type": {
        "breakfast": "Breakfast",
        "lunch": "Lunch",
        "snacks": "Snacks",
        "dinner": "Dinner",
        "bakery": "Bakery",
        "beverages": "Beverages",
    },
    "diet": {"veg": "Veg", "egg": "Contains egg", "non_veg": "Non-veg", "vegan": "Vegan"},
    "storage": {
        "hot_held": "Kept hot (60 °C or above)",
        "refrigerated": "Refrigerated (5 °C or below)",
        "room_temp": "Room temperature",
        "shelf_stable": "Shelf-stable (bakery, packaged)",
    },
    "allergen": {
        "gluten": "Gluten (wheat, barley, rye, oats)",
        "crustacean": "Crustaceans (prawn, crab)",
        "egg": "Egg",
        "fish": "Fish",
        "peanut": "Peanuts",
        "tree_nut": "Tree nuts (cashew, almond…)",
        "soy": "Soy",
        "milk": "Milk & dairy (paneer, ghee, curd)",
        "sulphite": "Sulphites",
        "sesame": "Sesame",
        "mustard": "Mustard",
    },
}
