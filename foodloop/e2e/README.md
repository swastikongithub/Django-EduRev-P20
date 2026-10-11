# Browser journey test

`journey.py` drives a real Chromium browser through the whole MVP and saves screenshots in
`e2e/screenshots/`. It is a *smoke test*: it proves the main paths work end to end. The detailed rules are
covered by the backend tests (`backend/tests`).

```bash
# one-time setup (any Python 3.12+ environment)
pip install playwright
playwright install chromium

# with the backend (:8000) and frontend (:5173) running, from the foodloop folder:
python e2e/journey.py
```

It needs the sample data (`python -m app.cli seed-sample`) with a “Veg thali” that is still open for
reservations, and an admin account (defaults: `admin@example.com` / `admin-pass-2024`; override with the
`ADMIN_EMAIL` and `ADMIN_PASSWORD` environment variables). Sample listings close about an hour after
seeding. If the journey says the meal is closed, reset the sample data as described in the main README.
