"""The public landing page at /: who sees it, what it may show, and that it never claims more than the code does."""

import re
from collections import Counter
from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts.permissions import ROLE_PERMISSIONS
from apps.bookings import availability
from apps.bookings import services as bookings
from apps.catalogue.models import Resource, ResourceStatus
from apps.core import landing

from .conftest import at

pytestmark = pytest.mark.django_db


def next_open_day():
    d = timezone.localdate() + timedelta(days=1)
    return d + timedelta(days=1) if d.weekday() == 6 else d


@pytest.fixture
def booked(student, room):
    d = next_open_day()
    return bookings.create_booking(
        requester=student, resource=room, start=at(d, 10), end=at(d, 11), title="Thesis defence rehearsal", notify=False
    )


def test_anonymous_visitors_get_the_landing_page(client, booked):
    r = client.get("/")
    assert r.status_code == 200
    assert [t.name for t in r.templates][0] == "core/landing.html"
    html = r.content.decode()
    assert "The campus, booked on" in html
    assert 'href="/find/' in html and 'href="/login/"' in html
    assert "Content-Security-Policy" in r.headers


def test_signed_in_people_still_go_straight_home(client, student):
    client.force_login(student)
    r = client.get("/")
    assert r.status_code == 302 and r.url == "/home/"


def test_an_empty_installation_still_goes_to_first_run_setup(client, db):
    r = client.get("/")
    assert r.status_code == 302 and r.url == "/login/"


def test_the_ledger_preview_is_real_and_anonymised(client, booked, student, room):
    html = client.get("/").content.decode()
    assert room.name in html  # the resource and its day come from the ledger
    assert "1 booking" in html
    # but nothing about who booked it or why
    for secret in (booked.title, booked.reference, student.get_full_name(), student.username, student.vid):
        if secret:
            assert secret not in html


def test_the_preview_reads_the_same_ledger_as_the_live_board(booked, room):
    p = landing.ledger_preview()
    row = next(r for r in p["rows"] if r["name"] == room.name)
    assert [s["kind"] for s in row["segments"] if s["kind"] != "closed"] == [availability.BOOKED]
    assert "10:00–11:00 Booked" in [s["label"] for s in row["segments"]]


def test_rare_kinds_of_claim_are_preferred():
    rows = [{"type": f"T{i}", "kinds": ["booked", "class"], "segments": [1] * 8} for i in range(8)] + [
        {"type": "Courts", "kinds": ["maintenance"], "segments": [1]}
    ]
    picked = landing._pick(rows)
    assert len(picked) == landing.ROWS
    assert any("maintenance" in r["kinds"] for r in picked)
    assert len({r["type"] for r in picked}) == len(picked)


def test_day_summary_reads_naturally():
    c = Counter({availability.CLASS: 70, availability.BOOKED: 1, availability.MAINTENANCE: 2})
    assert landing._summary(c) == "70 timetabled classes, 1 booking and 2 maintenance windows"
    assert landing._summary(Counter({availability.BOOKED: 3})) == "3 bookings"
    assert landing._summary(Counter()) == "no claims"


def test_catalogue_counts_only_bookable_active_resources(room, room2):
    Resource.objects.filter(pk=room2.pk).update(status=ResourceStatus.RETIRED)
    data = landing.catalogue()
    assert data["resources"] == 1 and data["buildings"] == 1
    assert [(t["name"], t["count"]) for t in data["types"]] == [("Classrooms", 1)]


def test_role_matrix_is_derived_from_the_permission_code():
    m = landing.role_matrix()
    by_key = {c["key"]: c for c in m["columns"]}
    for key, _label, roles, _scope in landing.ROLE_COLUMNS:
        for role in roles:
            assert by_key[key]["caps"] == ROLE_PERMISSIONS[role]  # faculty and staff really are identical
        assert by_key[key]["mfa"] == all(r in settings.MFA_REQUIRED_ROLES for r in roles)
    codes = {code for code, _ in landing.CAPABILITIES}
    # every capability is shown except those that need the scheduler, and none is invented
    assert codes | landing.NEEDS_SCHEDULER == set().union(*ROLE_PERMISSIONS.values())
    assert not codes & landing.NEEDS_SCHEDULER
    student = by_key["student"]
    assert student["can"] == ["Book rooms, labs, courts and equipment"] and not student["mfa"]


def test_page_has_one_h1_and_no_inline_script(client, booked):
    html = client.get("/").content.decode()
    assert len(re.findall(r"<h1\b", html)) == 1
    for tag in re.findall(r"<script\b[^>]*>", html):
        assert "src=" in tag, tag  # CSP: script-src 'self'
    assert " on" not in " ".join(re.findall(r"<[^>]+\son\w+=", html))


def test_landing_without_resources_still_renders(client, student):
    r = client.get("/")
    assert r.status_code == 200
    assert "their schedules appear here" in r.content.decode()


def test_no_claim_depends_on_the_background_scheduler(client, booked):
    """
    Releasing no-shows, the no-show ladder, reminders, approval expiry and the nightly Insights
    rollup all run on Celery Beat. Production runs no Beat service today, so the public page
    describes only what happens within a request (or on the worker), and must not promise these.
    """
    html = " ".join(client.get("/").content.decode().lower().split())
    for claim in (
        "released",
        "release ",
        "grace period",
        "reminder",
        "expire",
        "nightly",
        "idle capacity",
        "utilisation",
        "on a schedule",
        "pause booking",
        "repeated no-shows",
        "no-show",
    ):
        assert claim not in html, claim
