"""
P20 peak-load scenario: N users log in, then all POST a booking for the SAME slot at once.

Contract under test (booking API, session auth):

    POST /api/v1/bookings/   {"resource": <id>, "start": <iso8601>, "end": <iso8601>, "title": <str>}
      201 Created   -> this user won the slot
      409 Conflict  -> slot already taken (the expected answer for everyone else)

Correct behaviour: exactly ONE 201, every other attempt 409, zero 5xx / other codes.
Both 201 and 409 are recorded as *successes* in Locust's statistics (they are named
separately so you can read the split); anything else is a failure. At exit the scenario
prints an outcome summary and sets a non-zero exit code if the expectation is violated.

Configuration (environment variables):

    LOCUST_PASSWORD            password shared by the demo users               (required)
    LOCUST_RESOURCE_ID         primary key of the resource to fight over       (required)
    LOCUST_SLOT_START          ISO-8601 start, e.g. 2026-10-12T10:00:00+05:30  (default: next Mon-Sat 10:00 IST, >= 2 days out)
    LOCUST_SLOT_END            ISO-8601 end                                     (default: start + LOCUST_SLOT_MINUTES)
    LOCUST_SLOT_MINUTES        slot length when END is not given                (default: 60)
    LOCUST_USERNAMES           comma-separated usernames, used round-robin      (overrides the template)
    LOCUST_USERNAME_TEMPLATE   str.format template with {n}                     (default: student{n})
    LOCUST_USERNAME_START      first n for the template                         (default: 1)
    LOCUST_USERNAME_COUNT      how many template users exist; n wraps around    (default: 0 = never wrap)
    LOCUST_LOGIN_PATH          Django login form URL                            (default: /login/)
    LOCUST_BOOKING_PATH        booking API URL                                  (default: /api/v1/bookings/)
    LOCUST_TITLE               booking title                                    (default: P20 peak load test)
    LOCUST_BARRIER_TIMEOUT     seconds to wait for all users to log in         (default: 120)
    LOCUST_ONE_SHOT            1 = each user books once then stops              (default: 1)
    LOCUST_QUIT_WHEN_DONE      1 = stop the run once every user has attempted   (default: 1)
    LOCUST_DISTINCT_CLIENTS    1 = each virtual user sends its own X-Forwarded-For address (default: 1).
                               The app rate-limits sign-in per client address (20/min); 500 users
                               from one load generator would otherwise share one bucket. The target
                               must trust one proxy hop (TRUSTED_PROXY_HOPS=1), as it does behind
                               the production load balancer.
    LOCUST_FORWARDED_PROTO     "https" = act as the TLS proxy (X-Forwarded-Proto) when the target
                               runs with SECURE_SSL_REDIRECT=1 behind a proxy  (default: unset)

Run it (see loadtest/README.md):

    locust -f loadtest/locustfile.py --headless -u 500 -r 100 --host http://localhost:8000
"""

from __future__ import annotations

import itertools
import logging
import os
import sys
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlparse

import gevent
from gevent.event import Event
from locust import HttpUser, between, events, task
from locust.exception import StopUser
from locust.runners import LocalRunner

log = logging.getLogger("p20.loadtest")

IST = timezone(timedelta(hours=5, minutes=30))


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _flag(name: str, default: str = "1") -> bool:
    return _env(name, default).lower() in {"1", "true", "yes", "on"}


LOGIN_PATH = _env("LOCUST_LOGIN_PATH", "/login/")
BOOKING_PATH = _env("LOCUST_BOOKING_PATH", "/api/v1/bookings/")
TITLE = _env("LOCUST_TITLE", "P20 peak load test")
BARRIER_TIMEOUT = float(_env("LOCUST_BARRIER_TIMEOUT", "120"))
ONE_SHOT = _flag("LOCUST_ONE_SHOT")
QUIT_WHEN_DONE = _flag("LOCUST_QUIT_WHEN_DONE")
SESSION_COOKIE = _env("LOCUST_SESSION_COOKIE", "sessionid")
CSRF_COOKIE = _env("LOCUST_CSRF_COOKIE", "csrftoken")
DISTINCT_CLIENTS = _flag("LOCUST_DISTINCT_CLIENTS")
FORWARDED_PROTO = _env("LOCUST_FORWARDED_PROTO")
_client_numbers = itertools.count(1)


def client_address(n: int) -> str:
    """A distinct private address per virtual user: 10.0.0.1, 10.0.0.2, ... 10.0.1.0, ..."""
    return f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


def default_slot_start(now: datetime | None = None) -> datetime:
    """Next Monday-Saturday at 10:00 IST, at least two days ahead (clears lead-time rules)."""
    day = (now or datetime.now(IST)).astimezone(IST).date() + timedelta(days=2)
    while day.weekday() == 6:  # Sunday: campus closed in the demo availability rules
        day += timedelta(days=1)
    return datetime.combine(day, time(10, 0), tzinfo=IST)


def slot_window() -> tuple[str, str]:
    start = datetime.fromisoformat(_env("LOCUST_SLOT_START")) if _env("LOCUST_SLOT_START") else default_slot_start()
    if start.tzinfo is None:
        start = start.replace(tzinfo=IST)
    if _env("LOCUST_SLOT_END"):
        end = datetime.fromisoformat(_env("LOCUST_SLOT_END"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=IST)
    else:
        end = start + timedelta(minutes=int(_env("LOCUST_SLOT_MINUTES", "60")))
    return start.isoformat(), end.isoformat()


def username_source():
    explicit = [u.strip() for u in _env("LOCUST_USERNAMES").split(",") if u.strip()]
    if explicit:
        return itertools.cycle(explicit)
    template = _env("LOCUST_USERNAME_TEMPLATE", "student{n}")
    first = int(_env("LOCUST_USERNAME_START", "1"))
    count = int(_env("LOCUST_USERNAME_COUNT", "0"))
    numbers = itertools.cycle(range(first, first + count)) if count > 0 else itertools.count(first)
    return (template.format(n=n) for n in numbers)


# ── Shared run state (per Locust process) ────────────────────────────────────
USERNAMES = username_source()
SLOT_START, SLOT_END = slot_window()
GO = Event()  # released once every simulated user has logged in (or the barrier times out)
state = {"logged_in": 0, "login_failed": 0, "attempted": 0}
outcomes: Counter[str] = Counter()
first_unexpected: list[str] = []


def _expected_users(environment) -> int:
    runner = environment.runner
    return int(getattr(runner, "target_user_count", 0) or getattr(environment.parsed_options, "num_users", 0) or 0)


def _maybe_release(environment) -> None:
    expected = _expected_users(environment)
    if expected and state["logged_in"] + state["login_failed"] >= expected and not GO.is_set():
        log.info("all %s users logged in (%s failed) -> firing booking requests", expected, state["login_failed"])
        GO.set()


def _maybe_quit(environment) -> None:
    expected = _expected_users(environment)
    if QUIT_WHEN_DONE and expected and state["attempted"] + state["login_failed"] >= expected:
        if isinstance(environment.runner, LocalRunner):
            gevent.spawn_later(1, environment.runner.quit)


@events.init.add_listener
def _validate(environment, **kwargs):
    missing = [name for name in ("LOCUST_PASSWORD", "LOCUST_RESOURCE_ID") if not _env(name)]
    if missing:
        log.error("missing required environment variables: %s (see loadtest/README.md)", ", ".join(missing))
        sys.exit(2)
    int(_env("LOCUST_RESOURCE_ID"))  # fail fast on a non-numeric id
    log.info("target: resource=%s slot=%s..%s", _env("LOCUST_RESOURCE_ID"), SLOT_START, SLOT_END)


@events.test_start.add_listener
def _arm_barrier_timeout(environment, **kwargs):
    def release_after_timeout():
        if not GO.is_set():
            log.warning("barrier timeout (%ss): firing with %s users logged in", BARRIER_TIMEOUT, state["logged_in"])
            GO.set()

    gevent.spawn_later(BARRIER_TIMEOUT, release_after_timeout)


@events.quitting.add_listener
def _summarise(environment, **kwargs):
    if not isinstance(environment.runner, LocalRunner):
        log.info("distributed run: per-worker outcomes are logged by each worker; use the stats table on the master")
    booked, conflict = outcomes["201"], outcomes["409"]
    other = sum(v for k, v in outcomes.items() if k not in {"201", "409"})
    lines = [
        "",
        "=" * 64,
        f" P20 same-slot stampede  resource={_env('LOCUST_RESOURCE_ID')}  {SLOT_START} .. {SLOT_END}",
        f"   logged in       : {state['logged_in']}   (login failures: {state['login_failed']})",
        f"   201 booked      : {booked}",
        f"   409 conflict    : {conflict}",
        f"   other responses : {other}  {dict((k, v) for k, v in outcomes.items() if k not in {'201', '409'})}",
    ]
    if first_unexpected:
        lines.append(f"   first unexpected: {first_unexpected[0]}")
    ok = booked == 1 and other == 0 and state["login_failed"] == 0 and state["attempted"] > 0
    lines.append(f"   RESULT          : {'PASS - exactly one winner' if ok else 'FAIL'}")
    lines.append("=" * 64)
    print("\n".join(lines), flush=True)
    if not ok and isinstance(environment.runner, LocalRunner):
        environment.process_exit_code = 1


class SameSlotBooker(HttpUser):
    """One student: log in with a Django session, wait for everyone, then try to book the contested slot."""

    wait_time = between(1, 3)  # only used when LOCUST_ONE_SHOT=0

    def on_start(self):
        target = urlparse(self.host or "")
        self.plain_http = target.scheme == "http"
        # Behind the TLS proxy the app sees https, and Django's CSRF check then expects an
        # https Referer for the same host. The CSRF check itself is never relaxed.
        self.origin = f"https://{target.netloc}" if FORWARDED_PROTO == "https" else self.host
        if FORWARDED_PROTO:
            self.client.headers["X-Forwarded-Proto"] = FORWARDED_PROTO
        if DISTINCT_CLIENTS:
            self.client.headers["X-Forwarded-For"] = client_address(next(_client_numbers))
        self.username = next(USERNAMES)
        self.logged_in = self._login()
        state["logged_in" if self.logged_in else "login_failed"] += 1
        _maybe_release(self.environment)
        if not self.logged_in:
            _maybe_quit(self.environment)

    # With DEBUG=0 Django marks session/CSRF cookies Secure; a non-browser client talking
    # plain http to a local stack would then never send them back. Localhost only.
    def _relax_secure_cookies(self):
        if self.plain_http:
            for cookie in self.client.cookies:
                cookie.secure = False

    def _login(self) -> bool:
        with self.client.get(LOGIN_PATH, name="GET login", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"login page returned {resp.status_code}")
                return False
        self._relax_secure_cookies()
        form = {
            "username": self.username,
            "password": _env("LOCUST_PASSWORD"),
            "csrfmiddlewaretoken": self.client.cookies.get(CSRF_COOKIE, ""),
        }
        with self.client.post(
            LOGIN_PATH,
            data=form,
            headers={"Referer": f"{self.origin}{LOGIN_PATH}"},
            allow_redirects=False,
            name="POST login",
            catch_response=True,
        ) as resp:
            self._relax_secure_cookies()
            if resp.status_code in (301, 302, 303) and SESSION_COOKIE in self.client.cookies:
                resp.success()
                return True
            resp.failure(f"login failed for {self.username}: HTTP {resp.status_code}")
            return False

    @task
    def book_contested_slot(self):
        if not self.logged_in:
            raise StopUser()
        if not GO.is_set():
            GO.wait()
        payload = {
            "resource": int(_env("LOCUST_RESOURCE_ID")),
            "start": SLOT_START,
            "end": SLOT_END,
            "title": TITLE,
        }
        headers = {
            "Accept": "application/json",
            "X-CSRFToken": self.client.cookies.get(CSRF_COOKIE, ""),
            "Referer": f"{self.origin}{BOOKING_PATH}",
        }
        with self.client.post(
            BOOKING_PATH, json=payload, headers=headers, name="POST booking", catch_response=True
        ) as resp:
            code = str(resp.status_code)
            outcomes[code] += 1
            if code in {"201", "409"}:
                resp.success()
            else:
                if not first_unexpected:
                    first_unexpected.append(f"HTTP {code} for {self.username}: {resp.text[:300]!r}")
                resp.failure(f"unexpected HTTP {code}")
        # A second, zero-time request entry makes the 201/409 split visible in the stats table.
        events.request.fire(
            request_type="RESULT",
            name={"201": "201 booked (winner)", "409": "409 conflict (expected)"}.get(code, f"{code} unexpected"),
            response_time=0,
            response_length=0,
            exception=None if code in {"201", "409"} else Exception(f"HTTP {code}"),
            context={},
        )
        state["attempted"] += 1
        _maybe_quit(self.environment)
        if ONE_SHOT:
            raise StopUser()
