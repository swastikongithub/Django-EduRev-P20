# FoodLoop · *Good food. Less waste.*

FoodLoop connects canteens, college cafeterias, hostel messes and PG kitchens that have **safe, unsold food**
with students and employees who want an **affordable meal**. Kitchens list surplus after service, customers
reserve it and collect it at the counter with a pickup code before the deadline.

This folder contains **Phase 1 (the MVP)**: a working web app with a React frontend, a FastAPI backend and a
PostgreSQL database. It also includes several Phase 2 safety features and a kit for validating the idea in a
real pilot.

| Home page | Today's menu |
|---|---|
| ![Home page](docs/screenshots/landing.webp) | ![Today's menu](docs/screenshots/menu.webp) |

| A kitchen's page | Meal page | My reservations |
|---|---|---|
| ![Kitchen page](docs/screenshots/kitchen-page.webp) | ![Meal detail](docs/screenshots/meal-detail.webp) | ![My reservations](docs/screenshots/my-reservations.webp) |

| Kitchen dashboard | Admin dashboard |
|---|---|
| ![Kitchen dashboard](docs/screenshots/kitchen-dashboard.webp) | ![Admin dashboard](docs/screenshots/admin.webp) |

| Menu on a phone | Browse on a phone |
|---|---|
| ![Menu on mobile](docs/screenshots/menu-mobile.webp) | ![Browse on mobile](docs/screenshots/browse-mobile.webp) |

> Everything in the screenshots is **sample data**, labelled “Sample data” in the app. The food photos are
> licensed stock photos used as **representative images**, and the app labels them that way, so nobody
> mistakes them for the actual batch. A kitchen's own upload always replaces them.
>
> **About the photos:** they are licensed from Adobe Stock and are **not stored in this public repository**
> (the licence doesn't allow redistributing them on their own). Without them the app still works and shows
> FoodLoop's own meal illustrations instead. See [docs/image-credits.md](docs/image-credits.md) and
> `frontend/public/photos/README.md`.

---

## What works today

**Customers**
- Browse meals that can be reserved right now: search, meal-type chips, diet (veg / vegan / egg / non-veg),
  max price, “pickup open now”, “avoid allergens”, and four sort orders. Filters live in the URL, so a view
  can be shared.
- Meal page: the kitchen's photo or a labelled representative photo, price and saving, pickup window with
  countdown, eat-by time, storage method, allergens, kitchen address, pickup instructions and FSSAI number.
  On phones a bottom bar keeps the price and **Reserve** in reach.
- Reserve 1–N portions (within the kitchen's per-order limit) and get a 6-character **pickup code**.
- “My reservations”: code, countdown, call-the-kitchen link, and **cancel** (the portions go back on sale).
- **Today's menu**: every dish on offer right now, grouped like a restaurant menu with prices, search, a
  veg / non-veg filter and jump links. **Kitchens**: a page per approved kitchen with its address, FSSAI
  number and everything it has on offer.
- **Live everywhere**: meals, portions and prices refresh by themselves every 30 seconds, countdowns tick
  every second in the last hour, and the home page shows live counts and a ticker of current deals.
- **About**, **FAQ** and **Contact** pages. The contact form saves messages for the admins (with spam
  protection). **My account**: change your name and mobile number, or your password (which logs out your
  other browsers).
- If the server or database goes down, the site says exactly which one, keeps checking, and reloads the
  data by itself when it's back.

**Kitchens (providers)**
- Register the kitchen with FSSAI details. It starts as **awaiting approval** and nothing it creates is
  visible until an admin approves it.
- Dashboard: waiting pickups, today's listed / reserved / collected numbers, money recovered over the last 7
  days, and a **“Last 7 days” chart** (listed → reserved → collected) drawn from the kitchen's real data.
- Create, edit, pause, publish and remove listings, with a photo upload, a **food-safety checklist**, an
  **explicit allergen declaration** and storage-based time limits.
- **Hand over** a meal by typing the customer's pickup code, or cancel a reservation with a reason (e.g.
  “food spilled”).

**Admins**
- Overview numbers, a queue of kitchens awaiting approval (with a link to verify on FSSAI's FoSCoS portal),
  approve / reject / suspend with a reason, listing moderation, a **Messages** inbox for the contact form,
  and an **activity log** of every important action.

### Safety guarantees (enforced by the server and the database, not the browser)

| Promise | How it's enforced |
|---|---|
| Never sell more portions than exist | One SQL `UPDATE … WHERE quantity_available >= qty`, plus a `CHECK (quantity_available >= 0)`. Proven by a test where 30 people try to reserve at the same instant. |
| Expired food can never be bought | The reservation statement checks the clock at the moment of buying. “Expired” and “sold out” are never stored, so a missed background job can't break this. |
| Only approved kitchens with valid FSSAI can sell | The same statement requires `status = 'approved'` and `fssai_valid_until >= today`. |
| No duplicate orders | A partial unique index (one active reservation per customer per meal), plus an idempotency key so a double-tap creates one reservation. |
| Suspending a kitchen stops everything at once | Its listings disappear and its open reservations are cancelled, with the reason shown to customers. |
| Removing a listing tells the customers | Its open reservations are cancelled with the reason. |
| Food stays inside a safe window | Per-storage limits (room temperature 2 h, kept hot 4 h, refrigerated 24 h, shelf-stable 48 h from preparation to eat-by). These are **configurable pilot defaults, not legal limits**. |
| Logins can't be stolen by scripts | Server-side sessions in an `httpOnly` cookie, argon2 password hashing, CSRF protection (Origin check), login rate limiting, strict security headers and Content Security Policy. |
| Uploaded photos are safe | Re-encoded with Pillow (rejects fake images, strips GPS/EXIF data, resizes, blocks decompression bombs). |

---

## How it fits together

```
 Browser (phone / laptop)
      │  /api/…  (JSON + httpOnly session cookie)
      ▼
 React app (Vite, TypeScript, Tailwind)  ── dev: :5173, forwards /api to :8000
      │
      ▼
 FastAPI (Python)  ── routes in app/api, business rules in app/services
      │  SQLAlchemy 2 + Alembic migrations
      ▼
 PostgreSQL 16  ── constraints do the final safety checks
```

In production, FastAPI also serves the built React files (`FRONTEND_DIST`), so the whole app runs as **one
service on one domain**, with no CORS setup and no cookie problems.

```
foodloop/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, security middleware, serves the built frontend in production
│   │   ├── config.py          # every setting, read from environment variables / .env
│   │   ├── models/            # database tables (SQLAlchemy)
│   │   ├── schemas/           # request/response validation (Pydantic)
│   │   ├── api/               # HTTP routes + permission checks (deps.py)
│   │   ├── services/          # business rules: reservations, listings, providers, stats
│   │   ├── security/          # password hashing, sessions, rate limiting
│   │   ├── storage/images.py  # safe photo uploads
│   │   └── cli.py             # create-admin, seed-sample, sweep
│   ├── alembic/versions/      # database migrations
│   └── tests/                 # 46 tests against real PostgreSQL
├── frontend/
│   └── src/
│       ├── api/               # fetch wrapper, types, data hooks (TanStack Query)
│       ├── components/        # Layout, ListingCard, KitchenCard, MenuRow, Live (countdowns, ticker),
│       │                      #   ConnectionBanner, Photo, Toast, UI states, forms
│       ├── pages/             # Landing, Browse, Meal, Menu, Kitchens, About/FAQ/Contact, Account,
│       │                      #   Auth, Reservations, kitchen/, admin/
│       ├── lib/               # ₹ and IST formatting (with unit tests), photos, illustrations
│       └── index.css          # brand design tokens
├── e2e/journey.py             # browser test of the whole journey
├── docs/                      # database, food safety & compliance, pilot kit
└── docker-compose.yml         # local PostgreSQL
```

More detail: [docs/database.md](docs/database.md) · [docs/food-safety-and-compliance.md](docs/food-safety-and-compliance.md) · [docs/design-system.md](docs/design-system.md) · [docs/pilot/](docs/pilot/README.md)

---

## Run it on your computer

You need **Python 3.12+**, **Node.js 20+** (22 recommended) and **PostgreSQL 16**, either through
[Docker Desktop](https://www.docker.com/products/docker-desktop/) or a normal PostgreSQL install.

### Quickest way: one command

```bash
python run.py          # Windows: just double-click "Start FoodLoop.bat"
```

It checks the database (and starts it with Docker if needed), creates `backend/.env`, installs the Python
and JavaScript packages, updates the database tables, adds labelled sample meals, starts the backend and
the website together, and opens <http://localhost:5173>. Press **Ctrl+C** to stop everything. The first run
takes a few minutes; after that it starts in seconds. Create your admin once with step 2's `create-admin`.

The steps below do the same by hand.

### 1. Start PostgreSQL

**Option A, Docker** (from the `foodloop` folder):

```bash
docker compose up -d
```

This creates the user `foodloop` (password `foodloop`), the database `foodloop`, and a separate
`foodloop_test` database for the automated tests.

**Option B, a normal PostgreSQL install.** Open `psql` as the `postgres` superuser (on Windows: *SQL Shell
(psql)* from the Start menu) and run:

```sql
CREATE ROLE foodloop LOGIN PASSWORD 'foodloop' CREATEDB;
CREATE DATABASE foodloop OWNER foodloop;
CREATE DATABASE foodloop_test OWNER foodloop;
```

### 2. Start the backend (API)

```bash
cd foodloop/backend
python -m venv .venv
# Windows PowerShell:   .venv\Scripts\Activate.ps1
# macOS / Linux:        source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env          # Windows: copy .env.example .env
alembic upgrade head          # creates the tables

python -m app.cli create-admin --email admin@example.com --name "Your Name"   # asks for a password
python -m app.cli seed-sample                                                  # optional: labelled sample data

uvicorn app.main:app --reload
```

Check: <http://localhost:8000/api/health> shows `{"status":"ok","database":"ok"}`, and
<http://localhost:8000/docs> lists every API endpoint, where you can try them.

### 3. Start the frontend (website)

In a **second terminal**:

```bash
cd foodloop/frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

### Sample accounts (only after `seed-sample`, development only)

| Email | Password | What it is |
|---|---|---|
| `customer@example.com` | `sample-pass-2024` | a customer |
| `kitchen@example.com` | `sample-pass-2024` | **Green Leaf Canteen**: lunches and snacks |
| `tiffin@example.com` | `sample-pass-2024` | **Dakshin Tiffin Corner**: South Indian breakfast |
| `bakery@example.com` | `sample-pass-2024` | **Crumbs Bakery Café**: bakes and cold drinks |
| `mess@example.com` | `sample-pass-2024` | **Hostel 7 Mess**: dinners |
| `chai@example.com` | `sample-pass-2024` | **Chai Adda**: street snacks and chai |
| `pending-kitchen@example.com` | `sample-pass-2024` | a kitchen **awaiting approval** |
| your admin | the password you chose | admin dashboard |

The five sample kitchens list a full menu of 34 dishes (₹15–₹60) across every meal type, each within the
food-safety time limits for how it's stored. In development the backend re-lists a sample dish when its
pickup window ends, so your local site always has food (turn off with `SAMPLE_AUTO_REFRESH=false`). It never
touches real kitchens. `seed-sample` refuses to run when `APP_ENV=production`.

---

## Environment variables (`backend/.env`)

| Variable | Default | What it does |
|---|---|---|
| `APP_ENV` | `development` | `production` hides `/docs` and blocks sample data |
| `DATABASE_URL` | `postgresql://foodloop:foodloop@localhost:5432/foodloop` | main database |
| `TEST_DATABASE_URL` | `…/foodloop_test` | used **only** by pytest, which wipes it. The name must end in `_test`. |
| `ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | websites allowed to send POST/PUT requests |
| `COOKIE_SECURE` | `false` | set `true` when served over HTTPS (always in production) |
| `FRONTEND_DIST` | *(empty)* | path to `frontend/dist`, so FastAPI serves the website too |
| `MEDIA_DIR` | `backend/media` | where listing photos are stored |
| `RESERVATION_CUTOFF_MINUTES` | `10` | reservations close this long before pickup ends |
| `SAMPLE_AUTO_REFRESH` | `true` | development only: re-list the sample kitchens' dishes when their pickup window ends, so a local copy always has food. Ignored in production. |
| `MAX_SAFE_HOURS_ROOM_TEMP` / `_HOT_HELD` / `_REFRIGERATED` / `_SHELF_STABLE` | `2` / `4` / `24` / `48` | food-safety window per storage type |

Secrets never go in code. `.env` is ignored by Git, and only `.env.example` is committed.

---

## Test it

**Automated**

```bash
# backend (needs PostgreSQL running): lint + 57 tests incl. the concurrency proof
cd foodloop/backend
ruff check . && pytest

# frontend: type-check, unit tests, production build
cd foodloop/frontend
npm run typecheck && npm test && npm run build

# whole journey in a real browser (see e2e/README.md)
python e2e/journey.py
```

The same checks run on GitHub Actions for every push that touches `foodloop/`
(`.github/workflows/foodloop-ci.yml`).

**By hand, in about 10 minutes**

1. Log in as `customer@example.com` → **Explore Meals** → tap *Lunch* → open the Veg thali → reserve 2 →
   note the pickup code. Look at **Menu** and **Kitchens** too.
2. Open **My reservations**: the code and countdown are shown. Try **Cancel** on another reservation and
   watch “left” go back up on the meal page.
3. Log out, then log in as `kitchen@example.com` → **Pickups** → type the code → “Handed over to …”. Typing
   the same code again is refused.
4. **Listings** → *List surplus food*. Try a room-temperature meal prepared 3 hours ago: the form refuses it
   with the safety-policy message. Fix the times, tick the checklist and publish.
5. In a private window, **Register your kitchen**. The new kitchen can't list food (“Waiting for approval”).
6. Send a message from **Contact**. Log in as admin → approve the kitchen (or reject/suspend with a reason)
   → read the message under **Messages** → check the **Activity log**.
7. Shrink the browser to phone width: every page works without sideways scrolling.

---

## Production build (one service)

```bash
cd foodloop/frontend && npm run build
cd ../backend
APP_ENV=production COOKIE_SECURE=true FRONTEND_DIST=../frontend/dist uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Before a real public launch you still need HTTPS hosting, managed PostgreSQL backups, object storage for
photos, and a scheduled `python -m app.cli sweep`. That deployment step is deliberately left until the
pilot shows the idea works ([docs/pilot](docs/pilot/README.md)).

---

## Troubleshooting

| You see | Fix |
|---|---|
| `connection refused … port 5432` | PostgreSQL isn't running. Run `docker compose up -d`, or start your PostgreSQL service. |
| `password authentication failed for user "foodloop"` | The user/password in `DATABASE_URL` doesn't match what you created in step 1. |
| Docker: `port is already allocated` | Another PostgreSQL uses 5432. Change the compose port to `"5433:5432"` and use `:5433` in both URLs in `.env`. |
| `Refusing to run: the test database name must end in '_test'` | A safety check: point `TEST_DATABASE_URL` at `foodloop_test`, never your real database. |
| Banner: “Can't connect to the FoodLoop server” | The backend isn't running on port 8000. Start it (step 2, or `python run.py`). The page reconnects by itself. |
| Banner: “FoodLoop's database isn't reachable” | PostgreSQL isn't running. Open Docker Desktop and run `docker compose up -d`. The page reconnects by itself. |
| “Too many attempts. Please wait 15 minutes” | The login protection counts logins per email. Wait, or restart the backend to reset it. |
| `403 Cross-site request blocked` | Open the site at `http://localhost:5173`. To test on your phone, run `npm run dev -- --host`, open `http://<your-PC-IP>:5173`, and add that address to `ALLOWED_ORIGINS`. |
| PowerShell won't activate the venv | Run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| “Reservations for this meal have closed” on sample meals | Sample windows are short; new ones are listed within 5 minutes in development, or run `python -m app.cli seed-sample`. |

---

## Known limitations (honest list)

- **Payment** is “pay at the counter” only: no online payment and no mock gateway yet (Phase 2).
- **No password reset or email notifications** yet. Customers can't reset a forgotten password (Phase 2).
- **No customer “report a problem”** flow yet. Admins can suspend kitchens and remove listings (Phase 2).
- **One login per kitchen**: no staff accounts yet.
- The **login rate limit** lives in memory, so it resets on restart and isn't shared across several server
  processes.
- **Photos are stored on the local disk.** A hosted deployment needs object storage.
- The **no-show sweep** (`python -m app.cli sweep`) must be scheduled. Until it runs, an uncollected
  reservation still shows correctly as “Pickup missed”.
- **FSSAI checks are manual** (the admin looks the number up on FoSCoS). FoodLoop can't verify it
  automatically.
- All times are shown in **India Standard Time**.
- Not load-tested beyond the reservation concurrency tests.

## What's next

- **Phase 2 (business):** customer issue/safety reports, password reset and email confirmations, a mock
  online-payment flow behind a `PaymentProvider` interface (no card data ever stored), staff accounts,
  CSV reports for kitchens, a scheduled sweep, and a staging deployment with HTTPS and backups.
- **Phase 3 (data science):** an `analytics/` package (pandas, scikit-learn) that reads the pilot log and the
  app's data. It will cover demand by weekday, meal and time, surplus trends, conversion funnels, a seasonal
  baseline versus ML forecasts with time-ordered backtests, and **defensible** waste-avoided estimates. Any
  synthetic data will be clearly labelled as such.
