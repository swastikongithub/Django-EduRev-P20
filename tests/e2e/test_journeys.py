"""
End-to-end journeys in a real browser (Playwright + Chromium) against a live server.

These are the P20 acceptance journeys as a person experiences them: drag to book,
see why a timetabled slot is unavailable, check in by QR on a phone, check out, and
watch an un-checked-in booking get released. Run: `pytest -m e2e` (needs
`playwright install chromium`).
"""

import os
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.bookings import services as bookings
from apps.bookings.models import Booking, BookingSlot, BookingStatus, SlotKind
from apps.checkins.services import sweep_no_shows
from apps.core.timeutil import trange

from ..conftest import at

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")  # Playwright's sync API runs an event loop
pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

PASSWORD = "x-test-password-123"


@pytest.fixture
def day():
    return timezone.localdate() + timedelta(days=1)


def sign_in(page, live_server, user):
    page.goto(f"{live_server.url}/login/")
    page.fill("#id_username", user.username)
    page.fill("#id_password", PASSWORD)
    page.click("button[type=submit]")
    # The DOM is enough: waiting for "load" also waits for fonts and images, which says nothing
    # about whether sign-in worked and was the source of slow-runner timeouts.
    page.wait_for_url(f"{live_server.url}/home/", wait_until="domcontentloaded")
    page.wait_for_selector("main", state="attached")


def live_booking(user, room, minutes_ago=5, length=60):
    """A confirmed booking already under way, written directly (the service refuses past starts)."""
    start = (timezone.now() - timedelta(minutes=minutes_ago)).replace(second=0, microsecond=0)
    end = start + timedelta(minutes=length)
    b = Booking.objects.create(
        institution_id=room.institution_id,
        resource=room,
        requester=user,
        booked_for=user,
        title="Live session",
        period=trange(start, end),
        status=BookingStatus.APPROVED,
        checkin_grace_minutes=15,
    )
    BookingSlot.objects.create(resource=room, period=b.period, kind=SlotKind.BOOKING, booking=b, label=b.title)
    return b


def test_student_drags_on_the_calendar_and_gets_a_qr_pass(page, live_server, student, room, open_all_week, day):
    sign_in(page, live_server, student)
    page.goto(f"{live_server.url}{room.get_absolute_url()}?view=day&date={day.isoformat()}")
    col = page.locator(f'.cal__col[data-day="{day.isoformat()}"]')
    col.locator('.cal__cell[data-hm="11:00"]').scroll_into_view_if_needed()
    first = col.locator('.cal__cell[data-hm="10:00"]').bounding_box()
    last = col.locator('.cal__cell[data-hm="11:00"]').bounding_box()
    page.mouse.move(first["x"] + 10, first["y"] + 5)
    page.mouse.down()
    page.mouse.move(last["x"] + 10, last["y"] + 5, steps=6)
    page.mouse.up()
    assert page.locator("[data-sel-time]").inner_text() == "10:00–11:30"
    page.fill("#b-title", "Group study")
    page.locator("[data-submit-label]").click()
    page.wait_for_url("**/b/*/?new=1")
    assert "Booked. It's yours." in page.content()
    assert page.locator("svg.qr").count() == 1
    assert Booking.objects.get(booked_for=student).duration_minutes == 90


def test_calendar_uses_campus_time_not_the_browsers(browser, live_server, student, room, open_all_week):
    """
    A viewer whose device is 17.5 hours behind campus (UTC-12 vs IST) still sees campus time.
    The browser clock is frozen at 12:00 IST on the campus's today, which that device reads as
    18:30 the day before: the now-line must sit at noon and tomorrow's slot must say "Tomorrow".
    """
    from datetime import datetime
    from datetime import time as dtime

    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    noon_ist = timezone.make_aware(datetime.combine(today, dtime(12, 0)))
    ctx = browser.new_context(timezone_id="Etc/GMT+12", locale="en-IN", viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.clock.set_fixed_time(noon_ist)
    sign_in(page, live_server, student)

    page.goto(f"{live_server.url}{room.get_absolute_url()}?view=day&date={today.isoformat()}")
    cal = page.locator("[data-calendar]")
    assert cal.get_attribute("data-tz") == "Asia/Kolkata"
    first, hours = int(cal.get_attribute("data-first-hour")), int(cal.get_attribute("data-hours"))
    expected = (12 - first) / hours
    now_line = page.locator("[data-now]")
    assert now_line.is_visible()
    top = float(now_line.evaluate("el => el.style.top").rstrip("%")) / 100
    assert abs(top - expected) < 0.01, (top, expected)

    page.goto(f"{live_server.url}{room.get_absolute_url()}?view=day&date={tomorrow.isoformat()}")
    col = page.locator(f'.cal__col[data-day="{tomorrow.isoformat()}"]')
    col.locator('.cal__cell[data-hm="10:00"]').click()
    assert page.locator("[data-sel-day]").inner_text() == "Tomorrow"
    ctx.close()


def test_timetabled_class_is_shown_with_its_reason_and_never_offered(
    page, live_server, student, room, open_all_week, day
):
    bookings.claim_block(
        room,
        at(day, 10),
        at(day, 11),
        kind=SlotKind.CLASS,
        source_type="timetable_entry",
        source_id=1,
        label="CSE326 Lecture K23KF",
    )
    sign_in(page, live_server, student)
    page.goto(f"{live_server.url}{room.get_absolute_url()}?view=day&date={day.isoformat()}")
    col = page.locator(f'.cal__col[data-day="{day.isoformat()}"]')
    assert col.locator('.cal__cell[data-hm="10:00"]').count() == 0
    assert col.locator('.cal__cell[data-hm="10:30"]').count() == 0
    block = col.locator(".cal__block.st-class")
    assert "CSE326" in block.inner_text()
    block.click()
    assert "timetabled class" in page.locator("#why").inner_text()


def test_mobile_door_qr_check_in_then_check_out(browser, live_server, student, room, open_all_week):
    b = live_booking(student, room)
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    sign_in(page, live_server, student)
    page.goto(f"{live_server.url}/here/{room.code}/")  # what the door QR encodes
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    page.get_by_role("button", name="Check in here").click()
    page.wait_for_url(f"**{b.get_absolute_url()}")
    assert "In use until" in page.content()
    page.get_by_role("button", name="Check out").click()
    page.wait_for_load_state()
    b.refresh_from_db()
    assert b.status == BookingStatus.COMPLETED
    assert b.end < b.start + timedelta(minutes=60)  # the unused tail went back to campus
    ctx.close()


def test_unchecked_booking_is_released_after_grace(page, live_server, student, room, open_all_week):
    b = live_booking(student, room, minutes_ago=20)
    released = sweep_no_shows()
    assert [x.pk for x in released] == [b.pk]
    sign_in(page, live_server, student)
    page.goto(f"{live_server.url}{b.get_absolute_url()}")
    assert "Released" in page.content()
    assert not BookingSlot.objects.filter(booking=b).exists()


@pytest.mark.parametrize("path", ["/home/", "/find/", "/bookings/", "/scan/", "/me/"])
def test_no_horizontal_overflow_on_a_phone(browser, live_server, student, room, path):
    ctx = browser.new_context(viewport={"width": 360, "height": 780}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    sign_in(page, live_server, student)
    page.goto(live_server.url + path)
    assert page.evaluate("document.documentElement.scrollWidth") <= 360, path
    ctx.close()
