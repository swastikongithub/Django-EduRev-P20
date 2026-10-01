"""
Browser journeys for two more P20 acceptance criteria:
  * "Approval workflows configurable per resource type without deployment": a workflow row
    created at runtime makes a student's request pending; the custodian approves it in the
    console; the student's pass flips to confirmed.
  * "Recurring bookings created with correct per-occurrence conflict handling": faculty
    preview a weekly series, see the clashing date explained, and book the rest.
"""

import os
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.approvals.models import ApprovalStep, ApprovalWorkflow
from apps.bookings import services as bookings
from apps.bookings.models import Booking, BookingStatus

from ..conftest import at
from .test_journeys import sign_in

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def next_weekday(d):
    return d if d.weekday() < 6 else d + timedelta(days=1)


def test_runtime_workflow_then_custodian_approves_in_console(
    browser, live_server, student, custodian, room, open_all_week, lpu
):
    wf = ApprovalWorkflow.objects.create(
        institution=lpu, name="Students need a custodian", resource_type=room.type, requester_roles=["student"]
    )
    ApprovalStep.objects.create(workflow=wf, order=1, approver_role="custodian", sla_hours=12)
    day = next_weekday(timezone.localdate() + timedelta(days=1))

    s_ctx = browser.new_context()
    s = s_ctx.new_page()
    sign_in(s, live_server, student)
    s.goto(f"{live_server.url}{room.get_absolute_url()}?view=day&date={day.isoformat()}")
    assert "Needs approval" in s.content()
    s.select_option("#b-start", "15:00")
    s.select_option("#b-end", "16:00")
    s.fill("#b-title", "Society meeting")
    s.locator("[data-submit-label]").click()
    s.wait_for_url("**/b/*/?new=1")
    assert "Requested. The slot is held for you." in s.content()
    booking = Booking.objects.get(booked_for=student)
    assert booking.status == BookingStatus.PENDING

    c_ctx = browser.new_context()
    c = c_ctx.new_page()
    sign_in(c, live_server, custodian)
    c.goto(f"{live_server.url}/manage/approvals/")
    assert "Society meeting" in c.content()
    c.get_by_role("button", name="Approve").first.click()
    c.wait_for_load_state("networkidle")
    booking.refresh_from_db()
    assert booking.status == BookingStatus.APPROVED

    s.goto(f"{live_server.url}{booking.get_absolute_url()}")
    assert "Confirmed" in s.content() and s.locator("svg.qr").count() == 1
    s_ctx.close()
    c_ctx.close()


def test_faculty_weekly_series_skips_the_clash(page, live_server, faculty, student, room, open_all_week):
    first = next_weekday(timezone.localdate() + timedelta(days=2))
    # A student already holds the second week's slot.
    bookings.create_booking(
        requester=student,
        resource=room,
        start=at(first + timedelta(weeks=1), 12),
        end=at(first + timedelta(weeks=1), 13),
        title="Held",
        notify=False,
    )
    sign_in(page, live_server, faculty)
    page.goto(f"{live_server.url}/bookings/repeat/?resource={room.slug}&date={first.isoformat()}&from=12:00&to=13:00")
    page.fill("#s-ud", (first + timedelta(weeks=2)).isoformat())
    page.fill("#s-title", "CSE326 extra lab")
    page.get_by_role("button", name="Check every date").click()
    page.wait_for_load_state()
    assert "2 of 3 can be booked" in page.content()
    assert "Already booked" in page.content()
    page.get_by_role("button", name="Book 2 sessions").click()
    page.wait_for_load_state()
    assert "2 sessions booked" in page.content()
    assert Booking.objects.filter(booked_for=faculty, series__isnull=False).count() == 2
