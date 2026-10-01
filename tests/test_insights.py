"""
M9 — the Insights dashboard (/insights/) and its CSV exports.

Scenario: three resource types across two departments, ten days of snapshots ending yesterday.
CSE owns two classrooms and a basketball court; ECE owns a ₹40 lakh spectrometer that nobody books.
"""

import csv
import io
import xml.etree.ElementTree as ET
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Department, Role
from apps.analytics import charts, services
from apps.analytics.models import UtilisationSnapshot
from apps.catalogue.models import Resource, ResourceType
from apps.rules.models import Quota, QuotaPeriod

pytestmark = pytest.mark.django_db

SVG = "{http://www.w3.org/2000/svg}"


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def ece(lpu):
    return Department.objects.create(institution=lpu, code="ECE", name="Electronics & Communication")


@pytest.fixture
def court_type(lpu):
    return ResourceType.objects.create(
        institution=lpu, code="court", name="Basketball Court", plural="Basketball courts", category="sports"
    )


@pytest.fixture
def campus(lpu, room, room2, lab_type, court_type, block34, cse, ece):
    spectrometer = Resource.objects.create(
        institution=lpu,
        type=lab_type,
        code="SPEC-1",
        name="Raman Spectrometer",
        capacity=4,
        building=block34,
        department=ece,
        acquisition_cost=Decimal("4000000.00"),
    )
    court = Resource.objects.create(
        institution=lpu,
        type=court_type,
        code="BB-1",
        name="Basketball Court 1",
        capacity=10,
        building=block34,
        department=cse,
    )
    yesterday = timezone.localdate() - timedelta(days=1)
    rows = []
    for i in range(10):
        d = yesterday - timedelta(days=i)
        hourly = [0] * 24
        hourly[10] = 60
        hourly[11] = 45 + i
        for r, booked, used, denied in (
            (room, 300, 240, 0),
            (room2, 120, 60, 1),
            (court, 400, 380, 4),
            (spectrometer, 0, 0, 0),
        ):
            rows.append(
                UtilisationSnapshot(
                    resource=r,
                    date=d,
                    open_minutes=600,
                    class_minutes=60 if r == room else 0,
                    booked_minutes=booked,
                    used_minutes=used,
                    bookings=booked // 60,
                    no_shows=1 if r == room2 else 0,
                    denied_attempts=denied,
                    maintenance_minutes=30 if r == court and i == 0 else 0,
                    hourly_booked=hourly,
                )
            )
    UtilisationSnapshot.objects.bulk_create(rows)
    Quota.objects.create(
        institution=lpu,
        name="Weekly courts",
        department=cse,
        period=QuotaPeriod.WEEK,
        max_hours=Decimal("20"),
    )
    return {"spectrometer": spectrometer, "court": court}


@pytest.fixture
def dept_head(make_user):
    return make_user(Role.DEPT_HEAD)


def url(**params):
    from urllib.parse import urlencode

    return reverse("analytics:dashboard") + ("?" + urlencode(params) if params else "")


# ── Access ──────────────────────────────────────────────────────────────────


def test_facility_manager_sees_the_campus(client, facility_manager, campus):
    client.force_login(facility_manager)
    resp = client.get(url())
    assert resp.status_code == 200
    body = resp.content.decode()
    # The money report names the expensive idle asset, and three resource types appear.
    assert "Raman Spectrometer" in body
    assert "₹40,00,000" in body
    for label in ("Classrooms", "Computer Labs", "Basketball courts"):
        assert label in body
    assert resp.context["f"].scope.department_id is None
    assert len(resp.context["by_type"]["bars"]) >= 3
    assert "Download CSV" in body


def test_dept_head_is_locked_to_their_department(client, dept_head, campus, cse):
    client.force_login(dept_head)
    resp = client.get(url(department="ECE"))
    assert resp.status_code == 200
    f = resp.context["f"]
    assert f.scope.department_id == cse.pk
    body = resp.content.decode()
    assert "Raman Spectrometer" not in body  # ECE's kit stays invisible
    assert 'name="department"' not in body  # no department picker for a scoped analyst

    export = client.get(reverse("analytics:export", args=["idle"]) + "?department=ECE")
    assert export.status_code == 200
    assert "Raman Spectrometer" not in export.content.decode("utf-8-sig")


def test_dept_head_without_department_gets_an_explanation(client, make_user, campus):
    head = make_user(Role.DEPT_HEAD, department=None)
    client.force_login(head)
    resp = client.get(url())
    assert resp.status_code == 200
    assert "linked to a department" in resp.content.decode()


@pytest.mark.parametrize("role", [Role.STUDENT, Role.CUSTODIAN])
def test_non_analysts_are_refused(client, make_user, campus, role):
    client.force_login(make_user(role))
    assert client.get(url()).status_code == 403
    assert client.get(reverse("analytics:export", args=["types"])).status_code == 403


def test_anonymous_is_sent_to_login(client):
    resp = client.get(url())
    assert resp.status_code == 302


def test_campus_manager_can_filter_by_department_and_type(client, facility_manager, campus, ece, lab_type):
    client.force_login(facility_manager)
    resp = client.get(url(department="ECE", type="lab"))
    assert resp.status_code == 200
    scope = resp.context["f"].scope
    assert (scope.department_id, scope.resource_type_id) == (ece.pk, lab_type.pk)


# ── Periods ─────────────────────────────────────────────────────────────────


def test_periods(client, facility_manager, campus):
    client.force_login(facility_manager)
    yesterday = timezone.localdate() - timedelta(days=1)
    for period, days in (("7", 7), ("30", 30), ("90", 90)):
        scope = client.get(url(period=period)).context["f"].scope
        assert (scope.end, scope.days) == (yesterday, days)
    custom = client.get(url(start=(yesterday - timedelta(days=4)).isoformat(), end=yesterday.isoformat()))
    assert custom.context["f"].period == "custom" and custom.context["f"].scope.days == 5
    bad = client.get(url(start=yesterday.isoformat(), end=(yesterday - timedelta(days=3)).isoformat()))
    assert bad.context["f"].period == "30" and bad.context["f"].errors
    term = client.get(url(period="term")).context["f"].scope
    assert term.end == yesterday and term.start <= yesterday


def test_kpis_compare_with_the_previous_period(client, facility_manager, campus):
    client.force_login(facility_manager)
    kpis = client.get(url(period="7")).context["kpis"]
    assert [k["label"] for k in kpis][:2] == ["Utilisation", "Realised utilisation"]
    # Days 8–10 of the snapshots sit in the previous 7-day window, so there is something to compare.
    assert all(k["delta"]["text"] for k in kpis)


# ── CSV ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("report", sorted(__import__("apps.analytics.views", fromlist=["EXPORTS"]).EXPORTS))
def test_csv_exports_have_a_header_row(client, facility_manager, campus, report):
    client.force_login(facility_manager)
    resp = client.get(reverse("analytics:export", args=[report]))
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    assert "attachment" in resp["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
    assert rows and all(rows[0])


def test_unknown_export_is_404(client, facility_manager):
    client.force_login(facility_manager)
    assert client.get(reverse("analytics:export", args=["nope"])).status_code == 404


def test_csv_neutralises_formulas():
    from apps.analytics.views import _safe

    assert _safe("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _safe("Room 1") == "Room 1"
    assert _safe(None) == ""


# ── Charts ──────────────────────────────────────────────────────────────────


def _series(lpu):
    yesterday = timezone.localdate() - timedelta(days=1)
    return services.daily_series(lpu.pk, yesterday - timedelta(days=9), yesterday)


def test_chart_helpers_return_valid_svg(lpu, campus):
    days = _series(lpu)
    for svg in (charts.svg_hours(days, "t1"), charts.svg_utilisation(days, "t2", average=40.0)):
        root = ET.fromstring(str(svg))
        assert root.tag == SVG + "svg"
        assert root.get("role") == "img"
        title = root.find(SVG + "title")
        assert title is not None and title.text
        assert root.find(SVG + "desc") is not None
        # one hover target per day, each with its own title
        hits = root.findall(f"{SVG}g[@class='vz__hits']/{SVG}rect")
        assert len(hits) == len(days) and all(h.find(SVG + "title") is not None for h in hits)


def test_chart_helpers_survive_empty_and_zero_data():
    assert ET.fromstring(str(charts.svg_hours([], "e1"))).tag == SVG + "svg"
    assert ET.fromstring(str(charts.svg_utilisation([], "e2"))).tag == SVG + "svg"
    assert charts.nice_scale(0) == (4.0, [0.0, 1.0, 2.0, 3.0, 4.0])
    assert charts.nice_scale(87)[0] == 100


# ── Performance ─────────────────────────────────────────────────────────────


def test_dashboard_query_count_is_bounded(client, facility_manager, campus, django_assert_max_num_queries):
    client.force_login(facility_manager)
    with django_assert_max_num_queries(45):
        assert client.get(url()).status_code == 200
    # A second view of the same scope is served from the five-minute cache.
    with django_assert_max_num_queries(12):
        assert client.get(url()).status_code == 200


def test_empty_campus_renders_empty_states(client, facility_manager):
    client.force_login(facility_manager)
    resp = client.get(url())
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "No activity in this period" in body
    assert "No idle capacity to rank" in body
