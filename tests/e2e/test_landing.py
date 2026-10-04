"""
The public landing page in a real browser: accessible in both themes with and without motion,
no console errors, the motion layer runs, and its calls to action lead into the product.
"""

import os
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.bookings import services as bookings

from ..conftest import at
from .test_accessibility import AXE, BLOCKING, describe

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def campus(student, room):
    d = timezone.localdate() + timedelta(days=1)
    if d.weekday() == 6:
        d += timedelta(days=1)
    bookings.create_booking(
        requester=student, resource=room, start=at(d, 10), end=at(d, 11), title="Study", notify=False
    )
    return room


def open_landing(browser, browser_context_args, live_server, *, theme, motion):
    ctx = browser.new_context(
        **{**browser_context_args, "bypass_csp": True, "reduced_motion": "no-preference" if motion else "reduce"}
    )
    ctx.add_init_script(f"try {{ localStorage.setItem('lpr-theme', '{theme}') }} catch (e) {{}}")
    page = ctx.new_page()
    problems = []
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(str(e)))
    page.goto(live_server.url + "/", wait_until="load")
    return ctx, page, problems


def settle(page):
    """Scroll through once so every scroll-triggered reveal has run, then wait for the last one."""
    height = page.evaluate("document.documentElement.scrollHeight")
    for y in range(0, height, 400):
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(40)
    page.wait_for_timeout(2800)


@pytest.mark.parametrize("motion", [False, True], ids=["reduced-motion", "motion"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_landing_page_is_accessible(browser, browser_context_args, live_server, campus, theme, motion):
    ctx, page, problems = open_landing(browser, browser_context_args, live_server, theme=theme, motion=motion)
    assert page.evaluate("document.documentElement.dataset.theme") == theme
    if motion:
        assert page.evaluate("!!window.gsap && !!window.ScrollTrigger && !!window.Lenis")
    settle(page)
    page.add_script_tag(path=str(AXE))
    result = page.evaluate(
        """async () => await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']}})"""
    )
    violations = [v for v in result["violations"] if v["impact"] in BLOCKING]
    assert not violations, describe(violations)
    assert not problems, problems
    ctx.close()


def test_landing_calls_to_action_lead_into_the_product(page, live_server, campus):
    page.goto(live_server.url + "/")
    assert page.get_by_role("heading", level=1).inner_text().replace("\n", " ").startswith("The campus, booked on")
    # the real day from the ledger, one row per resource
    assert page.locator("[data-row]").count() >= 1
    assert campus.name in page.locator("[data-board]").inner_text()

    # the state legend is a set of toggle buttons
    maintenance = page.get_by_role("button", name="Maintenance")
    maintenance.focus()
    page.keyboard.press("Enter")
    assert maintenance.get_attribute("aria-pressed") == "true"
    assert page.locator(".lp-anatomy .lp-seg.is-on").count() == 1

    page.get_by_role("link", name="Explore resources").first.click()
    page.wait_for_url("**/login/?next=/find/")
    page.go_back()
    page.get_by_role("navigation", name="Sections").get_by_role(
        "link", name="How it works"
    )  # in-page navigation exists
    page.locator(".lp-nav").get_by_role("link", name="Sign in").click()
    page.wait_for_url(f"{live_server.url}/login/")


def test_landing_works_on_a_phone_without_sideways_scrolling(browser, browser_context_args, live_server, campus):
    ctx = browser.new_context(
        **{**browser_context_args, "viewport": {"width": 360, "height": 780}, "is_mobile": True, "has_touch": True}
    )
    page = ctx.new_page()
    page.goto(live_server.url + "/")
    assert page.evaluate("document.documentElement.scrollWidth") <= 360
    assert page.locator(".lp-rolelist").is_visible() and not page.locator(".lp-matrix").is_visible()
    ctx.close()
