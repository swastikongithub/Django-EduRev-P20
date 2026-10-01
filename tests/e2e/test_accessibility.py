"""
Accessibility (CES §1.3 WCAG 2.2 AA; §1.5 "axe-core: zero critical violations on
student-facing pages"). axe-core runs inside the real page after it renders, in light and
dark themes. Critical and serious violations fail the test, and the report lists every node.
"""

import os
from pathlib import Path

import pytest

from apps.bookings import services as bookings

from .test_journeys import PASSWORD, sign_in

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

AXE = Path(__file__).parent / "vendor" / "axe.min.js"


@pytest.fixture
def browser_context_args(browser_context_args):
    # Our CSP (script-src 'self') rightly blocks injected scripts; let the audit tool in for this module only.
    return {**browser_context_args, "bypass_csp": True}
BLOCKING = {"critical", "serious"}


def audit(page):
    page.add_script_tag(path=str(AXE))
    result = page.evaluate(
        """async () => await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']}})"""
    )
    return [v for v in result["violations"] if v["impact"] in BLOCKING]


def describe(violations):
    return "\n".join(
        f"{v['impact']}: {v['id']} ({v['help']}) at " + "; ".join(n["target"][0] for n in v["nodes"][:4])
        for v in violations
    )


@pytest.fixture
def booked_pass(student, room):
    from datetime import timedelta

    from django.utils import timezone

    from ..conftest import at

    d = timezone.localdate() + timedelta(days=1)
    if d.weekday() == 6:
        d += timedelta(days=1)
    return bookings.create_booking(requester=student, resource=room, start=at(d, 10), end=at(d, 11), title="Study",
                                   notify=False)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("path", ["/home/", "/find/?q=room", "ROOM", "PASS", "/bookings/", "/calendar/", "/scan/", "/me/",
                                  "/inbox/"])
def test_student_pages_have_no_serious_violations(page, live_server, student, room, booked_pass, path, theme):
    sign_in(page, live_server, student)
    page.evaluate(f"localStorage.setItem('lpr-theme', '{theme}')")
    url = {"ROOM": room.get_absolute_url(), "PASS": booked_pass.get_absolute_url()}.get(path, path)
    page.goto(live_server.url + url)
    page.wait_for_load_state("networkidle")
    violations = audit(page)
    assert not violations, describe(violations)


def test_login_page_has_no_serious_violations(page, live_server):
    page.goto(live_server.url + "/login/")
    violations = audit(page)
    assert not violations, describe(violations)


assert PASSWORD  # shared with the journeys module
