// TypeScript mirrors of the FastAPI response shapes (see backend/app/schemas).

export type Role = "customer" | "provider" | "admin";
export type ProviderStatus = "pending" | "approved" | "rejected" | "suspended";
export type ProviderKind = "college_canteen" | "cafeteria" | "hostel_mess" | "pg_kitchen" | "other";
export type FssaiKind = "registration" | "state_licence" | "central_licence";
export type MealType = "breakfast" | "lunch" | "snacks" | "dinner" | "bakery" | "beverages";
export type Diet = "veg" | "egg" | "non_veg" | "vegan";
export type Storage = "hot_held" | "refrigerated" | "room_temp" | "shelf_stable";
export type ListingStatus = "draft" | "active" | "paused" | "removed";
export type Availability =
  | "available"
  | "sold_out"
  | "closed"
  | "expired"
  | "paused"
  | "draft"
  | "removed"
  | "unavailable";
export type ReservationStatus = "reserved" | "collected" | "cancelled" | "no_show";
export type DisplayStatus = ReservationStatus | "missed";

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: Role;
}

export interface Kitchen {
  id: string;
  name: string;
  slug: string;
  kind: ProviderKind;
  description: string;
  address_line: string;
  area: string;
  city: string;
  pincode: string;
  contact_phone: string;
  fssai_number: string;
  fssai_kind: FssaiKind;
  fssai_valid_until: string;
  pickup_instructions: string;
  status: ProviderStatus;
  status_reason: string | null;
  is_sample: boolean;
}

export interface Me {
  user: User;
  provider: Kitchen | null;
}

export interface Meta {
  labels: {
    provider_kind: Record<ProviderKind, string>;
    fssai_kind: Record<FssaiKind, string>;
    meal_type: Record<MealType, string>;
    diet: Record<Diet, string>;
    storage: Record<Storage, string>;
    allergen: Record<string, string>;
    contact_topic: Record<ContactTopic, string>;
  };
  safety_policy: {
    max_safe_hours: Record<Storage, number>;
    reservation_cutoff_minutes: number;
    max_active_reservations_per_customer: number;
  };
}

export interface ListingProvider {
  id: string;
  name: string;
  slug: string;
  kind: ProviderKind;
  address_line: string;
  area: string;
  city: string;
  fssai_number: string;
  fssai_kind: FssaiKind;
  is_sample: boolean;
}

export interface Listing {
  id: string;
  title: string;
  description: string;
  meal_type: MealType;
  diet: Diet;
  allergens: string[];
  allergen_note: string;
  image_url: string | null;
  image_is_representative: boolean;
  original_price_paise: number;
  price_paise: number;
  discount_percent: number;
  quantity_total: number;
  quantity_available: number;
  max_per_order: number;
  storage: Storage;
  prepared_at: string;
  pickup_start: string;
  pickup_end: string;
  safe_until: string;
  reservations_close_at: string;
  pickup_instructions: string;
  availability: Availability;
  provider: ListingProvider;
}

export interface ProviderListing extends Listing {
  status: ListingStatus;
  removed_reason: string | null;
  reserved_quantity: number;
  collected_quantity: number;
  created_at: string;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ListingBrief {
  id: string;
  title: string;
  image_url: string | null;
  meal_type: MealType;
  diet: Diet;
  pickup_start: string;
  pickup_end: string;
  safe_until: string;
}

interface ReservationBase {
  id: string;
  quantity: number;
  unit_price_paise: number;
  total_paise: number;
  status: ReservationStatus;
  display_status: DisplayStatus;
  pickup_deadline: string;
  payment_method: "pay_at_pickup" | "mock_online";
  payment_status: "unpaid" | "paid" | "refunded";
  cancelled_by: "customer" | "provider" | "admin" | "system" | null;
  cancel_reason: string | null;
  created_at: string;
  collected_at: string | null;
  cancelled_at: string | null;
  listing: ListingBrief;
}

export interface CustomerReservation extends ReservationBase {
  pickup_code: string;
  can_cancel: boolean;
  provider: {
    id: string;
    name: string;
    address_line: string;
    area: string;
    city: string;
    contact_phone: string;
    pickup_instructions: string;
    is_sample: boolean;
  };
}

export interface ProviderReservation extends ReservationBase {
  customer_name: string;
}

export interface Funnel {
  portions_listed: number;
  portions_reserved: number;
  portions_collected: number;
  portions_cancelled: number;
  portions_missed: number;
  revenue_recovered_paise: number;
  sell_through_percent: number | null;
  collection_rate_percent: number | null;
}

export interface ProviderStats {
  live_listings: number;
  open_pickups: number;
  today: Funnel;
  last_7_days: Funnel;
}

export interface AdminKitchen extends Kitchen {
  owner_name: string | null;
  owner_email: string | null;
  created_at: string;
  reviewed_at: string | null;
  fssai_expired: boolean;
  active_listings: number;
}

export interface AuditEntry {
  id: number;
  action: string;
  entity_type: string;
  entity_id: string | null;
  actor_name: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AdminOverview {
  providers: Record<ProviderStatus, number>;
  customers: number;
  live_listings: number;
  portions_reserved_today: Record<ReservationStatus, number>;
  portions_collected_all_time: number;
  open_messages: number;
  recent_activity: AuditEntry[];
}

export interface ListingInput {
  title: string;
  description: string;
  meal_type: MealType;
  diet: Diet;
  allergens: string[];
  allergen_note: string;
  original_price_paise: number;
  price_paise: number;
  quantity_total: number;
  max_per_order: number;
  storage: Storage;
  prepared_at: string;
  pickup_start: string;
  pickup_end: string;
  safe_until: string;
  pickup_instructions: string;
  image_is_representative: boolean;
  safety_confirmed: boolean;
}

export interface KitchenInput {
  name: string;
  kind: ProviderKind;
  description: string;
  address_line: string;
  area: string;
  city: string;
  pincode: string;
  contact_phone: string;
  fssai_number: string;
  fssai_kind: FssaiKind;
  fssai_valid_until: string;
  pickup_instructions: string;
}

export type ContactTopic = "question" | "order" | "kitchen" | "safety" | "feedback";

/** A kitchen as the public sees it, with what it has on offer right now. */
export interface KitchenCard {
  id: string;
  name: string;
  slug: string;
  kind: ProviderKind;
  description: string;
  area: string;
  city: string;
  is_sample: boolean;
  live_meals: number;
  lowest_price_paise: number | null;
  meal_types: MealType[];
}

export interface KitchenDetail extends KitchenCard {
  address_line: string;
  pincode: string;
  pickup_instructions: string;
  fssai_number: string;
  fssai_kind: FssaiKind;
}

export interface ContactMessage {
  id: string;
  name: string;
  email: string;
  topic: ContactTopic;
  message: string;
  created_at: string;
  handled_at: string | null;
}
