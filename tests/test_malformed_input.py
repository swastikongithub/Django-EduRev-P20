"""
SEC-13 regression sweep: hostile query strings and form values never produce a 5xx.

Every page, console screen and API list is requested by each kind of user with dates at the
edges of the calendar, non-numeric and out-of-range ids, and junk in every common parameter;
the console forms are posted the same junk for each action they dispatch on. A 4xx, a redirect
or a page that ignores the junk are all fine. A 500 is not.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role

pytestmark = pytest.mark.django_db

DATE_KEYS = (
    "date",
    "day",
    "start",
    "end",
    "since",
    "until",
    "from",
    "to",
    "start_date",
    "until_date",
    "starts",
    "ends",
)
NUMBER_KEYS = (
    "page",
    "people",
    "attendees",
    "minutes",
    "days",
    "resource",
    "series",
    "user",
    "term",
    "pub",
    "pk",
    "download",
    "draft",
    "published",
    "report",
    "week",
    "weekday",
    "capacity",
    "type",
    "building",
    "department",
)

VARIANTS = {
    "calendar_start": {"date_value": "0001-01-01", "number_value": "abc"},
    "calendar_end": {"date_value": "9999-12-31", "number_value": "99999999999999999999"},
    "nonsense": {"date_value": "2026-13-45", "number_value": "-1"},
    # str.isdigit() is True for "²" and full-width digits, but int() rejects "²".
    "unicode_digits": {"date_value": "２０２６-10-01", "number_value": "²"},
}

PAGES = [
    "/home/",
    "/find/",
    "/r/{slug}/",
    "/bookings/",
    "/bookings/repeat/",
    "/calendar/",
    "/inbox/",
    "/me/",
    "/scan/",
    "/insights/",
    "/manage/",
    "/manage/approvals/",
    "/manage/board/",
    "/manage/no-shows/",
    "/manage/maintenance/",
    "/manage/inventory/",
    "/manage/resources/",
    "/manage/setup/",
    "/manage/policies/",
    "/manage/workflows/",
    "/manage/timetable/",
    "/manage/users/",
    "/manage/audit/",
    "/manage/ops/",
    "/api/v1/me/",
    "/api/v1/resources/",
    "/api/v1/resources/{slug}/",
    "/api/v1/resources/{slug}/availability/",
    "/api/v1/bookings/",
    "/api/v1/series/",
    "/api/v1/approvals/",
    "/api/v1/maintenance/",
    "/api/v1/notifications/",
    "/api/v1/analytics/utilisation/",
]

CONSOLE_POSTS = {
    "/manage/users/": ["role", "activate", "deactivate"],
    "/manage/workflows/": ["save", "toggle", "delete"],
    "/manage/policies/": [
        "policy.save",
        "policy.delete",
        "hours.add",
        "hours.remove",
        "blackout.save",
        "blackout.delete",
        "quota.save",
        "quota.delete",
        "quota.toggle",
        "tier.save",
        "tier.delete",
    ],
    "/manage/timetable/": ["import_preview", "import_confirm", "publish", "discard", "add_term"],
    "/manage/resources/": ["import_preview", "import_confirm"],
    "/manage/maintenance/schedule/": ["save"],
}


def _junk(variant: str) -> dict[str, str]:
    v = VARIANTS[variant]
    data = {k: v["date_value"] for k in DATE_KEYS}
    data.update({k: v["number_value"] for k in NUMBER_KEYS})
    data.update({"view": "week", "period": "custom", "tab": "x", "q": "lab for 99999 at 99:99 on 0001-01-01"})
    return data


@pytest.fixture
def people(make_user, student, faculty, custodian, admin_user):
    return {
        Role.STUDENT: student,
        Role.FACULTY: faculty,
        Role.CUSTODIAN: custodian,
        Role.ADMIN: admin_user,
        Role.DEPT_HEAD: make_user(Role.DEPT_HEAD),
    }


@pytest.mark.parametrize("variant", list(VARIANTS))
@pytest.mark.parametrize("role", [Role.STUDENT, Role.FACULTY, Role.CUSTODIAN, Role.DEPT_HEAD, Role.ADMIN])
def test_get_with_hostile_parameters_is_never_a_server_error(client, people, room, role, variant):
    client.raise_request_exception = False
    client.force_login(people[role])
    junk = _junk(variant)
    failures = []
    for page in PAGES:
        path = page.format(slug=room.slug)
        status = client.get(path, junk).status_code
        if status >= 500:
            failures.append(f"{status} GET {path}")
    assert not failures, failures


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_console_posts_with_hostile_values_are_never_a_server_error(client, admin_user, room, variant):
    client.raise_request_exception = False
    client.force_login(admin_user)
    failures = []
    for path, actions in CONSOLE_POSTS.items():
        for action in actions:
            data = {**_junk(variant), "action": action}
            status = client.post(path, data).status_code
            if status >= 500:
                failures.append(f"{status} POST {path} action={action}")
    assert not failures, failures
