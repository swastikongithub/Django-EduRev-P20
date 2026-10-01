# Load test report: 500 simultaneous attempts on one slot

**Scope of this report.** One run of the P20 peak scenario against a production-like stack on a
single development machine, plus unloaded per-request timings on the same stack. It verifies
**correctness under the P20 peak** and explains the latency it observed. It is **not** a
measurement of a deployed environment, and it does not verify the CES capacity targets (2,000
sustained / 5,000 peak users, p95 under 400 ms reads and 800 ms writes); those remain open
(OPS-8 in [known-issues.md](known-issues.md)).

## Result

| Question | Answer |
|---|---|
| Do 500 simultaneous booking attempts on one slot produce exactly one booking? | **Yes.** 500 users signed in (0 failures); 1 × `201 Created`, 499 × `409 Conflict`, 0 other responses. The database holds exactly one booking (`LR-RJSVYY`) and one ledger row for the slot |
| Any server errors or rejected sign-ins? | None |

The same guarantee is proven in-process on every CI run by `tests/test_concurrency.py`
(500 threads, and again with every application safeguard removed).

## Method

**Scenario** (`loadtest/locustfile.py`, P20 §8): 500 virtual students sign in through the real
sign-in form (session cookie, CSRF), wait at a barrier until every sign-in has finished, then
all `POST /api/v1/bookings/` for the same resource and hour at once. Expected: exactly one
`201`, every other attempt `409`, nothing else.

**Target**: the production image, started by `scripts/ci/stack.sh` exactly as CI's smoke test
and ZAP scan run it: gunicorn with 3 sync workers (`WEB_CONCURRENCY=3`, the image default),
`DEBUG=0`, PostgreSQL 16, Redis 7, `SECURE_SSL_REDIRECT=1` behind a simulated TLS proxy, plus
`TRUSTED_PROXY_HOPS=1` as on a platform load balancer. Demo campus seeded with a local-only
password for the 120 demo students (`s001`–`s120`, reused round-robin by the 500 virtual users).

**Client addresses.** Sign-in is rate-limited to 20 per minute per client address. Every
virtual user sends its own `X-Forwarded-For` (10.0.x.y), as 500 students on their own devices
behind the platform proxy would. Without this, one load generator is one address and the
scenario cannot pass; earlier versions of the scenario did not account for it.

**Command**

```bash
IMAGE=lpu-reserve:local EXTRA_WEB_ENV="TRUSTED_PROXY_HOPS=1" scripts/ci/stack.sh up
DEMO_PASSWORD='<local-only>' scripts/ci/stack.sh seed
LOCUST_PASSWORD='<local-only>' LOCUST_RESOURCE_ID=7 \
LOCUST_SLOT_START=2026-10-03T18:00:00+05:30 LOCUST_SLOT_END=2026-10-03T19:00:00+05:30 \
LOCUST_USERNAME_TEMPLATE='s{n:03d}' LOCUST_USERNAME_COUNT=120 \
LOCUST_FORWARDED_PROTO=https LOCUST_BARRIER_TIMEOUT=240 \
locust -f loadtest/locustfile.py --headless -u 500 -r 100 --host http://127.0.0.1:8000
```

**Environment**: one VM, 4 vCPU (Intel Xeon @ 2.80 GHz), 15 GB RAM, shared by Locust, the app,
PostgreSQL and Redis (Docker). Django 5.2.17, Python 3.12.14, gunicorn 26.2.0, PostgreSQL 16.15,
Redis 7.4.11, Locust 2.46.6. Run on 2026-10-01 (17:04–17:06 UTC), Phase 3 branch code.

## Latency observed

**Under the synchronised burst** (all 500 requests released together; times include queueing):

| Request | Count | Failures | Median | p95 | Max |
|---|---|---|---|---|---|
| `POST /api/v1/bookings/` (the contested attempt) | 500 | 0 | 3.0 s | 5.0 s | 5.3 s |
| `POST /login/` | 500 | 0 | 28 s | 69 s | 73 s |
| `GET /login/` | 500 | 0 | 16 s | 17 s | 17 s |

**Unloaded** (20 sequential requests on the same stack, nothing else running):

| Request | Median | p95 |
|---|---|---|
| `GET /login/` | 5 ms | 7 ms |
| `POST /login/` | 545 ms | 597 ms |
| `GET /home/` (signed in) | 119 ms | 154 ms |
| `POST /api/v1/bookings/` (slot taken, `409`) | 30 ms | 37 ms |

## Interpretation

- The burst figures are **queueing at three workers**, not slow requests. A sign-in costs about
  0.55 s of CPU, almost all of it Django's PBKDF2 password hashing (1,000,000 iterations, a
  deliberate defence against password cracking). 500 sign-ins × 0.55 s ÷ 3 workers ≈ 90 s,
  which matches the observed tail. 500 booking attempts × ~30 ms ÷ 3 workers ≈ 5 s, matching
  the booking p95.
- In the real P20 peak (a lab slot is released), students are mostly signed in already, so the
  relevant figure is the booking burst: on this deliberately small stack the last of 500
  simultaneous attempts is answered within about 5 s, and correctly.
- Burst latency falls roughly in proportion to the number of web workers. Size `WEB_CONCURRENCY`
  and instance count from these per-request costs (Phase 6), and keep the database connection
  budget in mind ([runbook.md](runbook.md#topology)).

## Not measured

- Sustained load (2,000 concurrent users) and the 5,000-user peak.
- p95 latency under steady load, and dashboard generation time under load.
- A deployed environment with its real network, TLS termination and managed database.

These require the staging environment (Phase 6) and stay **Partial** in
[traceability.md](traceability.md).
