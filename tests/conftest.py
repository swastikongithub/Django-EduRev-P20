"""
Shared fixtures. Times are pinned to a known future Monday so tests never depend on
the wall clock; services accept `now=` for the same reason.
"""

from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Department, Role, User
from apps.catalogue.models import Building, Custodian, Resource, ResourceType
from apps.core.models import Institution, reset_default_institution_cache
from apps.rules.models import AvailabilityRule, BookingPolicy, RestrictionTier, Scope

TZ = timezone.get_fixed_timezone(330)  # IST


def at(d: date, hh: int, mm: int = 0) -> datetime:
    return timezone.make_aware(datetime.combine(d, time(hh, mm)), timezone.get_current_timezone())


@pytest.fixture(autouse=True)
def _plain_static_storage(settings):
    """Tests don't need hashed filenames; avoid depending on a collectstatic manifest."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture(autouse=True)
def _force_login_includes_mfa(monkeypatch):
    """
    `client.force_login(user)` stands for a completed sign-in. For a user who needs MFA that
    includes the second factor, so stamp the session exactly as `accounts.views.mfa_view` does;
    otherwise `MFASessionMiddleware` would end it. A user promoted *after* signing in keeps an
    unstamped session (that is SEC-12's proof).
    """
    from django.test import Client

    from apps.accounts import mfa

    original = Client.force_login

    def force_login(self, user, backend=None):
        original(self, user, backend)
        if mfa.needs_mfa(user):
            session = self.session
            session[mfa.SESSION_KEY] = user.pk
            session.save()

    monkeypatch.setattr(Client, "force_login", force_login)


@pytest.fixture(autouse=True)
def _reset_tenant_cache():
    reset_default_institution_cache()
    yield
    reset_default_institution_cache()


@pytest.fixture(autouse=True)
def _empty_cache(settings):
    """
    Every test starts with an empty cache, as it starts with an empty database. The cache holds
    the sign-in rate-limit counters (20 per minute per address); shared across tests, a fast run
    of the browser suite signs in 21 times within a minute and the 21st is refused. The cache is
    a private in-memory one, so clearing it never flushes a developer's Redis (REDIS_URL).
    """
    from django.core.cache import cache

    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tests"}}
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def monday():
    """A Monday comfortably in the future."""
    today = timezone.localdate()
    d = today + timedelta(days=(7 - today.weekday()) % 7 + 7)
    return d


@pytest.fixture
def now(monday):
    """'Now' = the Friday before `monday`, 09:00."""
    return at(monday - timedelta(days=3), 9)


@pytest.fixture
def lpu(db):
    inst, _ = Institution.objects.get_or_create(code="LPU", defaults={"name": "Lovely Professional University"})
    return inst


@pytest.fixture
def cse(lpu):
    return Department.objects.create(institution=lpu, code="CSE", name="Computer Science & Engineering")


@pytest.fixture
def make_user(lpu, cse):
    counter = {"n": 0}

    def _make(role=Role.STUDENT, department=cse, **kw):
        counter["n"] += 1
        n = counter["n"]
        return User.objects.create_user(
            username=kw.pop("username", f"{role}{n}"),
            password="x-test-password-123",
            institution=lpu,
            role=role,
            department=department,
            first_name=kw.pop("first_name", role.title()),
            last_name=kw.pop("last_name", str(n)),
            email=kw.pop("email", f"{role}{n}@example.test"),
            **kw,
        )

    return _make


@pytest.fixture
def student(make_user):
    return make_user(Role.STUDENT)


@pytest.fixture
def faculty(make_user):
    return make_user(Role.FACULTY)


@pytest.fixture
def custodian(make_user):
    return make_user(Role.CUSTODIAN)


@pytest.fixture
def facility_manager(make_user):
    return make_user(Role.FACILITY_MANAGER, department=None)


@pytest.fixture
def admin_user(make_user):
    return make_user(Role.ADMIN, department=None)


@pytest.fixture
def block34(lpu):
    return Building.objects.create(institution=lpu, code="34", name="Block 34")


@pytest.fixture
def room_type(lpu):
    t = ResourceType.objects.create(
        institution=lpu, code="classroom", name="Classroom", plural="Classrooms", category="space"
    )
    BookingPolicy.objects.create(
        institution=lpu,
        scope=Scope.TYPE,
        resource_type=t,
        slot_minutes=30,
        min_duration_minutes=30,
        max_duration_minutes=180,
        lead_time_minutes=0,
        max_advance_days=60,
        checkin_grace_minutes=15,
    )
    for wd in range(6):
        AvailabilityRule.objects.create(
            institution=lpu, scope=Scope.TYPE, resource_type=t, weekday=wd, opens=time(8, 0), closes=time(20, 0)
        )
    return t


@pytest.fixture
def lab_type(lpu):
    t = ResourceType.objects.create(
        institution=lpu, code="lab", name="Computer Lab", plural="Computer Labs", category="lab"
    )
    for wd in range(6):
        AvailabilityRule.objects.create(
            institution=lpu, scope=Scope.TYPE, resource_type=t, weekday=wd, opens=time(8, 0), closes=time(20, 0)
        )
    return t


@pytest.fixture
def room(lpu, room_type, block34, cse, custodian):
    r = Resource.objects.create(
        institution=lpu,
        type=room_type,
        code="34-301",
        name="Room 34-301",
        capacity=60,
        building=block34,
        department=cse,
    )
    Custodian.objects.create(resource=r, user=custodian)
    return r


@pytest.fixture
def room2(lpu, room_type, block34, cse):
    return Resource.objects.create(
        institution=lpu,
        type=room_type,
        code="34-302",
        name="Room 34-302",
        capacity=60,
        building=block34,
        department=cse,
    )


@pytest.fixture
def ladder(lpu):
    RestrictionTier.objects.create(institution=lpu, no_shows=2, window_days=30, restrict_days=0, label="Warning")
    RestrictionTier.objects.create(institution=lpu, no_shows=3, window_days=30, restrict_days=7, label="7-day pause")
    RestrictionTier.objects.create(institution=lpu, no_shows=5, window_days=60, restrict_days=30, label="30-day pause")
