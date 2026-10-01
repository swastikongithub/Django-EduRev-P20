"""Shared fixtures for browser journeys."""

import re
from datetime import time

import pytest

from apps.rules.models import AvailabilityRule, BookingPolicy

# Only the live server is reachable from the browser. Pages once linked a Google Fonts stylesheet
# and `load` waited for it: when the CDN was slow from a CI runner, sign-in timed out (the axe
# suite's intermittent 30 s timeout). Fonts are self-hosted now, and every other request is still
# aborted at once, in every context (including those tests open with `browser.new_context`), so
# a future third-party reference cannot make journeys depend on the network again.
LIVE_SERVER = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?(/|$)")


def _block_external(context):
    context.route(lambda url: not LIVE_SERVER.match(url), lambda route: route.abort("internetdisconnected"))
    return context


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """
    The same browser everywhere: campus locale and timezone, a fixed desktop viewport and
    reduced motion, so screenshots, axe colour checks and anything time-of-day dependent do
    not vary with the CI runner. Tests that need another zone or a phone open their own context.
    """
    return {
        **browser_context_args,
        "locale": "en-IN",
        "timezone_id": "Asia/Kolkata",
        "viewport": {"width": 1280, "height": 800},
        "reduced_motion": "reduce",
    }


@pytest.fixture(scope="session", autouse=True)
def _hermetic_browser_contexts():
    from playwright.sync_api import Browser

    original = Browser.new_context

    def new_context(self, *args, **kwargs):
        return _block_external(original(self, *args, **kwargs))

    Browser.new_context = new_context
    yield
    Browser.new_context = original


@pytest.fixture
def open_all_week(room_type, lpu):
    """Make the classroom type open every day 07:00–23:00 so journeys run at any hour."""
    AvailabilityRule.objects.filter(resource_type=room_type).delete()
    for wd in range(7):
        AvailabilityRule.objects.create(
            institution=lpu, scope="type", resource_type=room_type, weekday=wd, opens=time(7, 0), closes=time(23, 0)
        )
    BookingPolicy.objects.filter(resource_type=room_type).update(checkin_opens_minutes=120)
