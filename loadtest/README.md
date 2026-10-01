# Load test: 500 users, one slot

P20 §8 sets the peak scenario: *"500 concurrent booking attempts at a peak – a lab slot
release – with zero double-booking."* `locustfile.py` reproduces it over HTTP, against the
running app (gunicorn, sessions, CSRF, the real API), complementing the in-process proof in
`tests/test_concurrency.py`.

## Prepare

1. Start a production-like stack. The simplest is the one CI uses, with one trusted proxy hop
   (as behind a platform load balancer):

   ```bash
   docker build -t lpu-reserve:local .
   IMAGE=lpu-reserve:local EXTRA_WEB_ENV="TRUSTED_PROXY_HOPS=1" scripts/ci/stack.sh up
   ```

2. Seed demo data **with a password** so the load users can sign in through the real login
   form (the seeder never stores a password unless you provide one):

   ```bash
   DEMO_PASSWORD='choose-a-local-password' scripts/ci/stack.sh seed
   ```

3. Pick a bookable room and an hour that is free (no class, maintenance or booking), at least
   two days ahead, and note the resource id.

## Why each virtual user has its own address

Sign-in is rate-limited to 20 attempts per minute **per client address** (and per account
lockout). One load generator is one address, so 500 users from it would be stopped by the rate
limit, not by anything the scenario is meant to test. By default (`LOCUST_DISTINCT_CLIENTS=1`)
each virtual user sends its own `X-Forwarded-For` address, as 500 students on their own devices
reach the app through the platform proxy. The target must trust one proxy hop
(`TRUSTED_PROXY_HOPS=1`); never set that on a server that clients reach directly.

## Run

```bash
pip install -r requirements-dev.txt
LOCUST_PASSWORD='choose-a-local-password' \
LOCUST_RESOURCE_ID=7 \
LOCUST_SLOT_START=2026-10-03T18:00:00+05:30 LOCUST_SLOT_END=2026-10-03T19:00:00+05:30 \
LOCUST_USERNAME_TEMPLATE='s{n:03d}' LOCUST_USERNAME_START=1 LOCUST_USERNAME_COUNT=120 \
LOCUST_FORWARDED_PROTO=https LOCUST_BARRIER_TIMEOUT=240 \
locust -f loadtest/locustfile.py --headless -u 500 -r 100 --host http://127.0.0.1:8000
```

`LOCUST_FORWARDED_PROTO=https` makes the client act as the TLS proxy, because the stack runs
with `SECURE_SSL_REDIRECT=1`. Users sign in first; a barrier then releases every booking POST
together. Sign-in is deliberately expensive (password hashing, about 0.5 s each), so allow a
generous barrier timeout on small machines.

The latest measured run and its interpretation are in
[docs/load-test-report.md](../docs/load-test-report.md).

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
WHERE resource_id = 7 AND status IN ('pending','approved','checked_in');
```

If you reuse demo usernames (`LOCUST_USERNAME_COUNT` wraps), several virtual users act as the
same person; their requests are serialised by the per-user row lock for quota accounting,
which is realistic (one student double-clicking) and still yields exactly one booking.
