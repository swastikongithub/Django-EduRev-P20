# Load test: 500 users, one slot

P20 §8 sets the peak scenario: *"500 concurrent booking attempts at a peak – a lab slot
release – with zero double-booking."* `locustfile.py` reproduces it over HTTP, against the
running app (gunicorn, sessions, CSRF, the real API), complementing the in-process proof in
`tests/test_concurrency.py`.

## Prepare

1. Start the stack (`docker compose up --build`, or `runserver` against `scripts/devdb.sh`).
2. Seed demo data **with a password** so the load users can sign in through the real login
   form (the seeder never stores a password unless you provide one):

   ```bash
   DEMO_PASSWORD='choose-a-local-password' python manage.py seed_demo
   ```

3. Pick the resource to fight over and note its id (any bookable room the students may book):

   ```bash
   python manage.py shell -c "from apps.catalogue.models import Resource as R; print(R.objects.filter(type__code='classroom').values_list('id','code')[:3])"
   ```

## Run

```bash
pip install -r requirements-dev.txt
LOCUST_PASSWORD='choose-a-local-password' \
LOCUST_RESOURCE_ID=12 \
LOCUST_USERNAME_TEMPLATE='student{n}' LOCUST_USERNAME_START=1 LOCUST_USERNAME_COUNT=120 \
locust -f loadtest/locustfile.py --headless -u 500 -r 100 --host http://localhost:8000
```

Users log in first; a barrier then releases every booking POST together.

## Reading the result

| Outcome | Expected | Meaning |
|---|---|---|
| `201 Created` | **exactly 1** | the single winner |
| `409 Conflict` | 499 | the slot was taken — the message says by whom/what |
| anything else | **0** | a bug (5xx) or misconfiguration (403 = login/CSRF, 422 = rules, e.g. lead time) |

The run prints an outcome summary and exits non-zero if the expectation is violated.
Afterwards, confirm in the database that one row holds the slot:

```sql
SELECT count(*) FROM bookings_booking
WHERE resource_id = 12 AND status IN ('pending','approved','checked_in');
```

If you reuse demo usernames (`LOCUST_USERNAME_COUNT` wraps), several virtual users act as the
same person; their requests are serialised by the per-user row lock for quota accounting,
which is realistic (one student double-clicking) and still yields exactly one booking.
