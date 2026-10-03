"""
A brand-new installation in a real browser, from an empty database to a checked-out booking, done
only through the product's own screens (no fixtures, no seed data), in light and dark themes:

    sign-in page offers first-run setup -> create the first administrator (with a validation
    error first) -> setup disappears -> sign in, enrol TOTP -> Setup checklist -> department,
    block, resource type -> a student and a facility manager -> a Classroom approval workflow ->
    a classroom with a photo -> the student books (pending) -> the facility manager signs in,
    enrols TOTP and approves -> the student sees Confirmed with a QR pass -> check in, check out.

axe-core audits the first-run pages and the checklist (WCAG 2.2 AA, no serious violations).
"""

import io
import os
from datetime import timedelta

import pyotp
import pytest
from django.utils import timezone
from PIL import Image

from apps.accounts.models import Role, User
from apps.approvals.models import ApprovalWorkflow
from apps.bookings.models import Booking, BookingSlot, BookingStatus
from apps.catalogue.models import Resource
from apps.core.timeutil import trange

from .test_accessibility import audit, describe

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

ADMIN_PW = "x-test-password-admin"
STUDENT_PW = "x-test-password-student"
FM_PW = "x-test-password-manager"


def new_page(browser, browser_context_args, theme):
    ctx = browser.new_context(**{**browser_context_args, "bypass_csp": True})  # lets axe in; CSP unchanged
    ctx.add_init_script(f"try {{ localStorage.setItem('lpr-theme', '{theme}') }} catch (e) {{}}")
    return ctx, ctx.new_page()


def assert_accessible(page, theme):
    assert page.evaluate("document.documentElement.dataset.theme") == theme
    violations = audit(page)
    assert not violations, describe(violations)


def sign_in_with_new_authenticator(page, base, username, password, *, on_login_page=False):
    """Password, then first-run TOTP enrolment, as the person would with Google Authenticator."""
    if not on_login_page:
        page.goto(f"{base}/login/")
    page.fill("#id_username", username)
    page.fill("#id_password", password)
    page.click("button[type=submit]")
    page.wait_for_url("**/login/verify/", wait_until="domcontentloaded")
    assert "Set up two-step sign-in" in page.content()
    key = page.locator("code.mfa-key").text_content().strip()
    page.fill("#code", pyotp.TOTP(key).now())
    page.click("button[type=submit]")


def sign_in(page, base, username, password):
    page.goto(f"{base}/login/")
    page.fill("#id_username", username)
    page.fill("#id_password", password)
    page.click("button[type=submit]")
    page.wait_for_url(f"{base}/home/", wait_until="domcontentloaded")


def add_in_sheet(page, base, path, fields, button):
    page.goto(base + path)
    sheet = page.locator("#new-sheet")
    for label, value in fields:
        target = sheet.get_by_label(label, exact=True)
        if target.evaluate("el => el.tagName") == "SELECT":
            target.select_option(value)
        else:
            target.fill(value)
    sheet.get_by_role("button", name=button).click()
    page.wait_for_load_state("domcontentloaded")


def add_person(page, base, first, last, email, username, role, password, department=None):
    page.goto(f"{base}/manage/users/new/")
    page.get_by_label("First name").fill(first)
    page.get_by_label("Last name").fill(last)
    page.get_by_label("Email").fill(email)
    page.get_by_label("Role").select_option(role)
    if department:
        page.get_by_label("Department").select_option(label=department)
    page.get_by_label("Username").fill(username)
    page.get_by_label("Initial password").fill(password)
    page.get_by_label("Repeat the password").fill(password)
    page.get_by_role("button", name="Add person").click()
    page.wait_for_url(f"**/manage/users/?q={username}")


def photo(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (640, 400), (246, 129, 33)).save(buf, "PNG")
    path = tmp_path / "room.png"
    path.write_bytes(buf.getvalue())
    return str(path)


def next_bookable_day():
    """Tomorrow or later, Monday to Saturday: the built-in opening hours when none are configured."""
    d = timezone.localdate() + timedelta(days=1)
    return d if d.weekday() < 6 else d + timedelta(days=1)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_empty_installation_to_a_checked_out_booking(browser, browser_context_args, live_server, tmp_path, theme):
    base = live_server.url
    assert not User.objects.exists()  # a genuinely empty installation
    a_ctx, a = new_page(browser, browser_context_args, theme)

    # ── First-run setup ────────────────────────────────────────────────
    a.goto(f"{base}/")
    a.wait_for_url("**/login/**")
    assert_accessible(a, theme)
    assert "This installation has no accounts yet" in a.content()
    assert a.get_by_role("link", name="Sign up").count() == 0
    a.get_by_role("link", name="Set up the first administrator").click()
    a.wait_for_url(f"{base}/setup/bootstrap/")
    assert_accessible(a, theme)

    a.get_by_label("Full name").fill("Asha Verma")
    a.get_by_label("Email").fill("asha.verma@example.test")
    a.get_by_label("Username").fill("asha.admin")
    a.get_by_label("Password", exact=True).fill(ADMIN_PW)
    a.get_by_label("Repeat the password").fill(ADMIN_PW + "x")
    a.get_by_role("button", name="Create administrator").click()
    summary = a.locator(".cfg-errsum")
    summary.wait_for()
    assert "No account was created" in summary.inner_text() and "don't match" in summary.inner_text()
    assert not User.objects.exists()
    assert_accessible(a, theme)  # the error summary and invalid fields too

    a.get_by_label("Password", exact=True).fill(ADMIN_PW)
    a.get_by_label("Repeat the password").fill(ADMIN_PW)
    a.get_by_role("button", name="Create administrator").click()
    a.wait_for_url(f"{base}/login/?next=/manage/setup/")
    assert "Administrator account created" in a.content()
    assert "no accounts yet" not in a.content()
    admin = User.objects.get()
    assert admin.role == Role.ADMIN and not admin.is_superuser and not admin.is_staff
    assert a.request.get(f"{base}/setup/bootstrap/").status == 404  # gone for good

    # ── Sign in, enrol MFA, land on the checklist ──────────────────────
    sign_in_with_new_authenticator(a, base, "asha.admin", ADMIN_PW, on_login_page=True)
    a.wait_for_url(f"{base}/manage/setup/", wait_until="domcontentloaded")
    assert "Getting started" in a.content() and "3 essential steps left" in a.content()
    assert_accessible(a, theme)

    # ── Catalogue, from the checklist's own links ──────────────────────
    a.get_by_role("link", name="Add a department").click()
    a.wait_for_url("**/manage/catalogue/?tab=departments&new=1")
    sheet = a.locator("#new-sheet")
    sheet.get_by_label("Department code").fill("CSE")
    sheet.get_by_label("Name", exact=True).fill("Computer Science and Engineering")
    sheet.get_by_role("button", name="Add department").click()
    a.wait_for_url("**/manage/catalogue/?tab=departments")
    add_in_sheet(
        a, base, "/manage/catalogue/?tab=buildings&new=1",
        [("Block code", "34"), ("Name", "Block 34")], "Add block",
    )  # fmt: skip
    add_in_sheet(
        a, base, "/manage/catalogue/?tab=types&new=1",
        [("Name", "Classroom"), ("Category", "space"), ("Icon", "door-open")], "Add type",
    )  # fmt: skip

    # ── People ─────────────────────────────────────────────────────────
    add_person(
        a, base, "Ravi", "Kumar", "ravi.kumar@example.test", "ravi.k", Role.STUDENT, STUDENT_PW,
        department="Computer Science and Engineering",
    )  # fmt: skip
    add_person(a, base, "Meera", "Nair", "meera.nair@example.test", "meera.fm", Role.FACILITY_MANAGER, FM_PW)

    # ── Classroom approval workflow: one step, a facility manager ──────
    a.goto(f"{base}/manage/workflows/?new=1")
    a.get_by_label("Name", exact=True).fill("Classroom approval")
    a.get_by_label("Type", exact=True).select_option(label="Classroom")
    a.locator("select[name=step_role]").first.select_option("facility_manager")
    a.get_by_role("button", name="Add workflow").click()
    a.wait_for_url("**/manage/workflows/#wf-*")
    assert ApprovalWorkflow.objects.get().steps.get().approver_role == "facility_manager"

    # ── The classroom, with a photo ────────────────────────────────────
    a.goto(f"{base}/manage/resources/new/")
    a.get_by_label("Name", exact=True).fill("Room 34-101")
    a.get_by_label("Code", exact=True).fill("34-101")
    a.get_by_label("Type", exact=True).select_option(label="Classroom")
    a.get_by_label("Capacity").fill("60")
    a.get_by_label("Block").select_option(label="Block 34")
    a.get_by_label("Department").select_option(label="Computer Science and Engineering")
    a.set_input_files("input[name=photo]", photo(tmp_path))
    a.get_by_role("button", name="Add resource").click()
    a.wait_for_load_state("domcontentloaded")
    room = Resource.objects.get(code="34-101")
    assert room.image and room.building.code == "34" and room.department.code == "CSE"

    a.goto(f"{base}/manage/setup/")
    assert "Everything people need to book is in place. 7 of 7 steps done" in a.content()
    assert_accessible(a, theme)

    # ── The student books: it needs approval ───────────────────────────
    s_ctx, s = new_page(browser, browser_context_args, theme)
    sign_in(s, base, "ravi.k", STUDENT_PW)  # students sign in without a second factor
    day = next_bookable_day()
    s.goto(f"{base}{room.get_absolute_url()}?view=day&date={day.isoformat()}")
    assert "Needs approval" in s.content()
    s.select_option("#b-start", "10:00")
    s.select_option("#b-end", "11:00")
    s.fill("#b-title", "Project review")
    s.locator("[data-submit-label]").click()
    s.wait_for_url("**/b/*/?new=1")
    assert "Requested. The slot is held for you." in s.content()
    booking = Booking.objects.get(booked_for__username="ravi.k")
    assert booking.status == BookingStatus.PENDING

    # ── The facility manager's first sign-in: MFA, then approve ────────
    f_ctx, f = new_page(browser, browser_context_args, theme)
    sign_in_with_new_authenticator(f, base, "meera.fm", FM_PW)
    f.wait_for_url(f"{base}/home/", wait_until="domcontentloaded")
    f.goto(f"{base}/manage/approvals/")
    assert "Project review" in f.content()
    f.get_by_role("button", name="Approve").first.click()
    f.wait_for_load_state("networkidle")
    booking.refresh_from_db()
    assert booking.status == BookingStatus.APPROVED

    # ── Confirmed, with a QR pass ──────────────────────────────────────
    s.goto(f"{base}{booking.get_absolute_url()}")
    assert "Confirmed" in s.content() and s.locator("svg.qr").count() == 1

    # ── Check in at the door and check out ─────────────────────────────
    # The booking is for a later day; move it to now so the door check-in is open (time travel,
    # not a shortcut: the rest of the flow is the real one).
    start = (timezone.now() - timedelta(minutes=5)).replace(second=0, microsecond=0)
    period = trange(start, start + timedelta(minutes=60))
    Booking.objects.filter(pk=booking.pk).update(period=period)
    BookingSlot.objects.filter(booking=booking).update(period=period)
    s.goto(f"{base}/here/{room.code}/")
    s.get_by_role("button", name="Check in here").click()
    s.wait_for_url(f"**{booking.get_absolute_url()}")
    assert "In use until" in s.content()
    s.get_by_role("button", name="Check out").click()
    s.wait_for_load_state()
    booking.refresh_from_db()
    assert booking.status == BookingStatus.COMPLETED

    for ctx in (a_ctx, s_ctx, f_ctx):
        ctx.close()
