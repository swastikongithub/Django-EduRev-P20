"""
The administrator setup screens in a real browser: catalogue (types, blocks, departments) and
Add a person, audited with axe-core (WCAG 2.2 AA, light and dark), plus creating a resource type
and a person through the actual forms.
"""

import os

import pytest
from django.conf import settings
from django.test import Client

from apps.accounts.models import Role, User
from apps.catalogue.models import ResourceType

from .test_accessibility import audit, describe

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def browser_context_args(browser_context_args):
    return {**browser_context_args, "bypass_csp": True}  # lets axe in; the app's CSP is unchanged


def signed_in_as(page, live_server, user):
    """An MFA-verified session (conftest stamps force_login) handed to the browser as its cookie."""
    c = Client()
    c.force_login(user)
    page.context.add_cookies(
        [{"name": settings.SESSION_COOKIE_NAME, "value": c.cookies[settings.SESSION_COOKIE_NAME].value,
          "url": live_server.url}]
    )  # fmt: skip


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(
    "path",
    ["/manage/catalogue/?tab=types", "/manage/catalogue/?tab=types&new=1", "/manage/catalogue/?tab=buildings",
     "/manage/catalogue/?tab=departments", "/manage/users/new/"],
)  # fmt: skip
def test_setup_pages_have_no_serious_violations(page, live_server, admin_user, room, path, theme):
    signed_in_as(page, live_server, admin_user)
    page.goto(live_server.url + "/home/")
    page.evaluate(f"localStorage.setItem('lpr-theme', '{theme}')")
    page.goto(live_server.url + path, wait_until="load")
    assert page.evaluate("document.documentElement.dataset.theme") == theme
    violations = audit(page)
    assert not violations, describe(violations)


def test_create_a_type_then_a_person_through_the_forms(page, live_server, admin_user, cse):
    signed_in_as(page, live_server, admin_user)
    page.goto(live_server.url + "/manage/catalogue/?tab=types")
    page.get_by_role("button", name="New resource type").click()
    sheet = page.locator("#new-sheet")
    sheet.get_by_label("Name", exact=True).fill("Computer Lab")
    sheet.get_by_label("Category").select_option("lab")
    sheet.get_by_label("Icon").select_option("monitor")
    sheet.get_by_role("button", name="Add type").click()
    page.wait_for_url("**/manage/catalogue/?tab=types")
    assert "Resource type Computer Lab added." in page.content()
    assert ResourceType.objects.get(name="Computer Lab").code == "computer-lab"

    page.goto(live_server.url + "/manage/users/")
    page.get_by_role("link", name="Add a person").click()
    page.get_by_label("First name").fill("Arjun")
    page.get_by_label("Email").fill("arjun@example.test")
    page.get_by_label("Role").select_option(Role.FACULTY)
    page.get_by_label("Department").select_option(str(cse.pk))
    page.get_by_label("Username").fill("arjun.f")
    page.get_by_label("Initial password").fill("Lab-Session-2026!")
    page.get_by_label("Repeat the password").fill("Lab-Session-2026!")
    page.get_by_role("button", name="Add person").click()
    page.wait_for_url("**/manage/users/?q=arjun.f")
    assert "can now sign in as arjun.f" in page.content()
    u = User.objects.get(username="arjun.f")
    assert (u.role, u.department_id, u.is_active) == (Role.FACULTY, cse.pk, True)
