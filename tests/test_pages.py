"""
Template / page tests (CES §1.5, Path P1): every screen renders for the roles that use it,
forms work end to end through the real views, and unauthorised users are turned away.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bookings import services as bookings
from apps.bookings.models import Booking, BookingStatus
from apps.catalogue.models import Feature, Resource

from .conftest import at

pytestmark = pytest.mark.django_db


@pytest.fixture
def tomorrow():
    return timezone.localdate() + timedelta(days=1)


@pytest.fixture
def booked(student, room, tomorrow):
    # Monday–Saturday hours; push to Monday if tomorrow is Sunday.
    d = tomorrow if tomorrow.weekday() != 6 else tomorrow + timedelta(days=1)
    return bookings.create_booking(
        requester=student, resource=room, start=at(d, 10), end=at(d, 11), title="Study", notify=False
    )


def test_login_page_renders_for_anonymous(client):
    resp = client.get(reverse("accounts:login"))
    assert resp.status_code == 200
    assert b"VID or username" in resp.content


def test_anonymous_is_sent_to_login(client):
    resp = client.get(reverse("core:home"))
    assert resp.status_code == 302 and reverse("accounts:login") in resp["Location"]


def test_login_lockout_after_five_failures(client, student):
    for _ in range(5):
        client.post(reverse("accounts:login"), {"username": student.username, "password": "wrong"})
    student.refresh_from_db()
    assert student.is_locked
    resp = client.post(reverse("accounts:login"), {"username": student.username, "password": "x-test-password-123"})
    assert b"locked" in resp.content


def test_real_login_works(client, student):
    resp = client.post(reverse("accounts:login"), {"username": student.username, "password": "x-test-password-123"})
    assert resp.status_code == 302


def test_demo_login_is_disabled_unless_demo_mode(client, student, settings):
    settings.DEMO_MODE = False
    assert client.post(reverse("accounts:demo_login"), {"username": "student"}).status_code == 404


def test_open_redirect_is_refused(client, student):
    resp = client.post(
        reverse("accounts:login") + "?next=https://evil.example/",
        {"username": student.username, "password": "x-test-password-123", "next": "https://evil.example/"},
    )
    assert resp["Location"] == reverse("core:home")


@pytest.mark.parametrize(
    "name",
    [
        "core:home",
        "catalogue:find",
        "bookings:mine",
        "bookings:calendar",
        "checkins:scan",
        "notifications:inbox",
        "accounts:me",
    ],
)
def test_student_pages_render(client, student, room, name):
    client.force_login(student)
    resp = client.get(reverse(name))
    assert resp.status_code == 200, name


def test_staff_home_shows_desk(client, custodian, room):
    client.force_login(custodian)
    resp = client.get(reverse("core:home"))
    assert resp.status_code == 200
    assert b"requests waiting for you" in resp.content


def test_find_understands_natural_language(client, student, room, lpu):
    Feature.objects.create(institution=lpu, name="Projector")
    client.force_login(student)
    resp = client.get(reverse("catalogue:find"), {"q": "room for 40 block 34 tomorrow at 10am projector"})
    assert resp.status_code == 200
    labels = [label for _, label in resp.context["intent"].understood]
    assert "40+ people" in labels and "Block 34" in labels and "Tomorrow" in labels


def test_find_with_window_hides_busy_resources(client, student, room, room2, booked):
    client.force_login(student)
    d = booked.start.date()
    resp = client.get(reverse("catalogue:find"), {"date": d.isoformat(), "from": "10:00", "to": "11:00"})
    names = [r.name for r, _ in resp.context["rows"]]
    assert room.name not in names and room2.name in names


def test_resource_page_and_partial(client, student, room):
    client.force_login(student)
    resp = client.get(room.get_absolute_url())
    assert resp.status_code == 200 and b"data-calendar" in resp.content
    partial = client.get(room.get_absolute_url() + "?view=day", HTTP_HX_REQUEST="true")
    assert partial.status_code == 200 and b"cal--day" in partial.content


def test_book_through_the_form_then_see_the_pass(client, student, room, tomorrow):
    d = tomorrow if tomorrow.weekday() != 6 else tomorrow + timedelta(days=1)
    client.force_login(student)
    resp = client.post(
        reverse("bookings:create", args=[room.slug]),
        {"date": d.isoformat(), "start": "14:00", "end": "15:30", "title": "Project sync", "attendees": "4"},
    )
    assert resp.status_code == 302
    b = Booking.objects.get(resource=room, booked_for=student)
    assert b.duration_minutes == 90
    page = client.get(resp["Location"])
    assert page.status_code == 200 and b"Booked. It's yours." in page.content and b'class="qr"' in page.content


def test_booking_conflict_is_explained_in_the_panel(client, student, make_user, room, room2, booked):
    other = make_user()
    client.force_login(other)
    d = booked.start.date()
    resp = client.post(
        reverse("bookings:create", args=[room.slug]),
        {"date": d.isoformat(), "start": "10:00", "end": "11:00"},
        HTTP_HX_REQUEST="true",
    )
    assert resp.status_code == 200
    assert b"Already booked 10:00" in resp.content
    assert room2.name.encode() in resp.content  # suggested alternative


def test_other_students_cannot_see_a_pass(client, make_user, booked):
    client.force_login(make_user())
    assert client.get(booked.get_absolute_url()).status_code == 404


def test_cancel_from_the_pass(client, student, booked):
    client.force_login(student)
    client.post(reverse("bookings:cancel", args=[booked.reference]))
    booked.refresh_from_db()
    assert booked.status == BookingStatus.CANCELLED


def test_pass_qr_landing_for_owner_and_stranger(client, student, make_user, booked):
    client.force_login(student)
    assert client.get(reverse("checkins:pass", args=[booked.qr_token])).status_code == 200
    client.force_login(make_user())
    resp = client.get(reverse("checkins:pass", args=[booked.qr_token]))
    assert b"belongs to someone else" in resp.content
    assert booked.booked_for.display_name.encode() not in resp.content


def test_door_qr_page(client, student, room):
    client.force_login(student)
    resp = client.get(reverse("checkins:here", args=[room.code]))
    assert resp.status_code == 200 and b"no booking here right now" in resp.content


def test_ics_export(client, student, booked):
    client.force_login(student)
    resp = client.get(reverse("bookings:ics", args=[booked.reference]))
    assert resp["Content-Type"].startswith("text/calendar") and b"BEGIN:VEVENT" in resp.content


def test_personal_feed_needs_the_token(client, student, booked):
    assert client.get(f"/feed/{student.calendar_token}.ics").status_code == 200
    assert client.get("/feed/00000000-0000-0000-0000-000000000000.ics").status_code == 404


def test_series_page_preview_for_faculty_only(client, faculty, student, room, tomorrow):
    client.force_login(student)
    assert client.get(reverse("bookings:series_new")).status_code == 404
    client.force_login(faculty)
    d = tomorrow if tomorrow.weekday() != 6 else tomorrow + timedelta(days=1)
    resp = client.post(
        reverse("bookings:series_new"),
        {
            "resource": room.slug,
            "weekday": [str(d.weekday())],
            "start": "12:00",
            "end": "13:00",
            "start_date": d.isoformat(),
            "until_date": (d + timedelta(weeks=2)).isoformat(),
            "action": "preview",
        },
    )
    assert resp.status_code == 200 and len(resp.context["plans"]) == 3


def test_breakdown_report_from_resource_page(client, student, custodian, room):
    client.force_login(student)
    resp = client.post(
        reverse("maintenance:report", args=[room.slug]),
        {"summary": "Projector dead", "severity": "critical"},
        follow=True,
    )
    assert b"asked to check it urgently" in resp.content
    room.refresh_from_db()
    assert room.status == "active"  # unconfirmed (SEC-02)

    client.force_login(custodian)
    resp = client.post(
        reverse("maintenance:report", args=[room.slug]),
        {"summary": "Projector dead", "severity": "critical"},
        follow=True,
    )
    assert b"out of service until the repair is done" in resp.content
    room.refresh_from_db()
    assert room.status == "out_of_service"


def test_console_is_staff_only(client, student, custodian):
    client.force_login(student)
    assert client.get(reverse("manage:home")).status_code == 403
    client.force_login(custodian)
    assert client.get(reverse("manage:home")).status_code == 200


def test_404_is_branded(client, student):
    client.force_login(student)
    resp = client.get("/b/LR-NOPE00/")
    assert resp.status_code == 404


def test_saved_resource_toggle(client, student, room):
    client.force_login(student)
    client.post(reverse("catalogue:save", args=[room.slug]))
    assert Resource.objects.filter(pk=room.pk).exists()
    assert student.saved_resources.count() == 1
    client.post(reverse("catalogue:save", args=[room.slug]))
    assert student.saved_resources.count() == 0


def test_data_export_contains_only_my_bookings(client, student, make_user, booked):
    client.force_login(student)
    resp = client.get(reverse("accounts:export"))
    data = resp.json()
    assert data["profile"]["username"] == student.username
    assert [b["reference"] for b in data["bookings"]] == [booked.reference]
    client.force_login(make_user())
    assert client.get(reverse("accounts:export")).json()["bookings"] == []


def test_admin_roles_need_a_second_factor(client, admin_user, settings):
    import pyotp

    from apps.accounts import mfa

    settings.MFA_ENFORCED = True
    resp = client.post(reverse("accounts:login"), {"username": admin_user.username, "password": "x-test-password-123"})
    assert resp["Location"] == reverse("accounts:mfa")
    assert client.get(reverse("core:home")).status_code == 302  # no session yet
    page = client.get(reverse("accounts:mfa"))
    assert page.context["enrolling"] is True
    secret = page.context["secret"]
    assert client.post(reverse("accounts:mfa"), {"code": "000000"}).context["error"]
    resp = client.post(reverse("accounts:mfa"), {"code": pyotp.TOTP(secret).now()})
    assert resp.status_code == 302
    admin_user.refresh_from_db()
    assert admin_user.mfa_enabled and secret not in admin_user.mfa_secret  # stored encrypted
    assert mfa.decrypt(admin_user.mfa_secret) == secret
    assert client.get(reverse("core:home")).status_code == 200


def test_students_are_not_asked_for_mfa(client, student, settings):
    settings.MFA_ENFORCED = True
    resp = client.post(reverse("accounts:login"), {"username": student.username, "password": "x-test-password-123"})
    assert resp["Location"] == reverse("core:home")


def test_untouched_accessory_fields_reserve_nothing(client, student, room, tomorrow, lpu):
    from apps.inventory.models import InventoryItem, Issuance

    item = InventoryItem.objects.create(
        institution=lpu,
        name="HDMI adapter",
        sku="HDMI-1",
        kind="accessory",
        resource=room,
        quantity_total=5,
        quantity_available=5,
    )
    d = tomorrow if tomorrow.weekday() != 6 else tomorrow + timedelta(days=1)
    client.force_login(student)
    client.post(
        reverse("bookings:create", args=[room.slug]),
        {"date": d.isoformat(), "start": "16:00", "end": "17:00", f"item-{item.pk}": "0"},
    )
    assert not Issuance.objects.exists()
    client.post(
        reverse("bookings:create", args=[room.slug]),
        {"date": d.isoformat(), "start": "17:00", "end": "18:00", f"item-{item.pk}": "2"},
    )
    assert Issuance.objects.get().quantity == 2


def test_hindi_and_punjabi_shell(client, student, room):
    client.force_login(student)
    client.post(reverse("set_language"), {"language": "hi", "next": "/home/"})
    resp = client.get(reverse("core:home"))
    assert 'lang="hi"' in resp.content.decode()
    assert "आपको क्या चाहिए, और कब?" in resp.content.decode()
    client.post(reverse("set_language"), {"language": "pa", "next": "/home/"})
    assert "ਤੁਹਾਨੂੰ ਕੀ ਚਾਹੀਦਾ ਹੈ" in client.get(reverse("core:home")).content.decode()
