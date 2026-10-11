# FoodLoop database

PostgreSQL 16. The tables are defined as Python classes in `backend/app/models/`, and every change to them is
a **migration** in `backend/alembic/versions/`. A migration is a small script that moves the database from
one version to the next, like Git commits for your tables.

## Tables

```
users ──< sessions                     a login can be open in several browsers
users ──< provider_members >── providers   which user runs which kitchen (one kitchen per account in the MVP)
providers ──< listings                 a kitchen offers many batches of surplus food
listings ──< reservations >── users    a customer reserves portions of a listing
audit_log                              who did what, when (approvals, suspensions, removals…)
```

| Table | Important columns | Notes |
|---|---|---|
| `users` | `email` (unique, lower-case), `password_hash` (argon2), `role` (`customer` / `provider` / `admin`) | Admins are created only with `python -m app.cli create-admin` |
| `sessions` | `token_hash`, `expires_at` | The cookie holds a random token. Only its SHA-256 hash is stored. |
| `providers` | `status` (`pending` / `approved` / `rejected` / `suspended`), `fssai_number` (14 digits), `fssai_valid_until`, `is_sample` | New kitchens are always `pending` |
| `listings` | prices in **paise**, `quantity_total`, `quantity_available`, `max_per_order`, `storage`, `prepared_at`, `pickup_start`, `pickup_end`, `safe_until`, `allergens[]`, `status` (`draft` / `active` / `paused` / `removed`), `safety_declared_by/at` | “Sold out” and “expired” are **calculated**, never stored |
| `reservations` | `pickup_code` (unique), `quantity`, frozen `unit_price_paise` / `total_paise`, `status` (`reserved` / `collected` / `cancelled` / `no_show`), `pickup_deadline`, `idempotency_key`, `payment_method` / `payment_status` | |
| `audit_log` | `action`, `entity_type`, `entity_id`, `details` (JSON) | |

Why money is in **paise as whole numbers**: `0.1 + 0.2` is not exactly `0.3` in floating point. Whole paise
never round wrongly. ₹45.50 is stored as `4550`.

Why times are `timestamptz`: they are stored in UTC and shown in India Standard Time by the website.

## Rules the database itself enforces

```sql
CHECK (price_paise > 0 AND price_paise <= original_price_paise)
CHECK (quantity_available >= 0 AND quantity_available <= quantity_total)
CHECK (prepared_at <= pickup_start AND pickup_start < pickup_end AND pickup_end <= safe_until)
CHECK (allergens <@ ARRAY['gluten', 'crustacean', 'egg', …])   -- only known allergen codes
CHECK (fssai_number ~ '^[0-9]{14}$')
CHECK (total_paise = unit_price_paise * quantity)
UNIQUE (customer_id, listing_id) WHERE status = 'reserved'      -- no duplicate active orders
UNIQUE (customer_id, idempotency_key)                           -- a double-tap creates one order
```

Even if a bug slipped into the Python code, PostgreSQL would refuse data that breaks these rules.

## The no-overselling statement

`backend/app/services/reservations.py` takes portions with **one** statement:

```sql
UPDATE listings SET quantity_available = quantity_available - :qty
FROM providers
WHERE listings.id = :listing_id
  AND providers.id = listings.provider_id
  AND providers.status = 'approved'
  AND providers.fssai_valid_until >= :today
  AND listings.status = 'active'
  AND listings.pickup_end > :now + interval '10 minutes'
  AND listings.safe_until > :now
  AND listings.max_per_order >= :qty
  AND listings.quantity_available >= :qty
RETURNING price_paise, pickup_end, provider_id;
```

When two people reserve the last portion at the same moment, PostgreSQL locks the row for the first
`UPDATE`. The second waits, then re-checks `quantity_available >= :qty` against the new value, finds it
false and updates nothing. The API then explains why (“sold out”, “only 1 left”, “closed”). There's no gap
between *checking* and *taking* for anyone to slip through.

`tests/test_reservations.py::test_many_simultaneous_customers_never_oversell` proves it: 30 customers on
separate database connections reserve at the same instant, and exactly as many succeed as there are
portions.

## Working with migrations

```bash
cd backend
alembic upgrade head                 # apply all migrations (run after every git pull)
alembic downgrade -1                 # undo the last one
alembic check                        # are the models and the database in sync?

# after changing a model in app/models/:
alembic revision --autogenerate -m "add phone_verified to users"
# ALWAYS read the generated file before applying it, then:
alembic upgrade head
```

**Gotcha to watch for:** for enum columns, autogenerate writes the CHECK constraint twice (once as
`sa.Enum(..., create_constraint=True)` and once as `sa.CheckConstraint`). In the generated file, set
`create_constraint=False` on the `sa.Enum` and keep the `op.f("ck_…")` constraint, as done in `0001`.
`alembic check` must then report *No new upgrade operations detected*.
