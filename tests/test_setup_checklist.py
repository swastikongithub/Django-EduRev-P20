"""
The Setup checklist (apps.core.onboarding) and the empty-database states around it.

The checklist is read from the database, never ticked by hand; each step links to the existing
screen that does the work, and only when this person may use it. Empty catalogues explain what is
missing and, for people allowed to fix it, link to the fix, without widening anyone's access.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Department, Role
from apps.approvals.models import ApprovalStep, ApprovalWorkflow
from apps.catalogue.models import Building, Resource, ResourceStatus, ResourceType
from apps.core.onboarding import setup_checklist

SETUP = "/manage/setup/"


def steps_by_key(user):
    return {s.key: s for s in setup_checklist(user)["steps"]}


def signed_in(client, user):
    client.force_login(user)
    return client


# ── What the checklist says ─────────────────────────────────────────────────


def test_fresh_installation_has_everything_left_but_the_administrator(admin_user):
    Department.objects.all().delete()  # the conftest department belongs to fixtures, not to setup
    admin_user.refresh_from_db()
    c = setup_checklist(admin_user)
    steps = {s.key: s for s in c["steps"]}
    assert [s.key for s in c["steps"]] == ["admin", "department", "block", "type", "people", "workflow", "resource"]
    assert steps["admin"].done and steps["admin"].count == 1
    assert not any(steps[k].done for k in ("department", "block", "type", "people", "workflow", "resource"))
    assert {k for k, s in steps.items() if s.optional} == {"department", "block", "workflow"}
    assert c["essential_left"] == 3 and not c["ready"] and c["done"] == 1


def test_links_go_to_the_existing_screens(admin_user):
    steps = steps_by_key(admin_user)
    assert steps["department"].add_url == "/manage/catalogue/?tab=departments&new=1"
    assert steps["block"].add_url == "/manage/catalogue/?tab=buildings&new=1"
    assert steps["type"].add_url == "/manage/catalogue/?tab=types&new=1"
    assert steps["people"].add_url == reverse("manage:user_new")
    assert steps["workflow"].add_url == reverse("manage:workflows") + "?new=1"
    assert steps["resource"].add_url == reverse("manage:resource_new")


def test_counts_follow_the_database(admin_user, lpu, cse, student, facility_manager, room_type, block34):
    steps = steps_by_key(admin_user)
    assert steps["department"].count_label == "1 department"
    assert steps["block"].count_label == "1 block"
    assert steps["type"].count_label == "1 resource type"
    assert steps["people"].count_label == "2 accounts"  # administrators are not counted
    assert not steps["resource"].done

    r = Resource.objects.create(institution=lpu, type=room_type, code="1-101", name="Room 1-101", capacity=40)
    wf = ApprovalWorkflow.objects.create(institution=lpu, name="Classrooms", resource_type=room_type)
    ApprovalStep.objects.create(workflow=wf, order=1, approver_role="facility_manager", sla_hours=24)
    c = setup_checklist(admin_user)
    assert c["ready"] and c["essential_left"] == 0 and c["done"] == 7

    # Nothing is remembered: retire the only resource and switch the workflow off, and they un-tick.
    Resource.objects.filter(pk=r.pk).update(status=ResourceStatus.RETIRED)
    ApprovalWorkflow.objects.filter(pk=wf.pk).update(active=False)
    steps = steps_by_key(admin_user)
    assert not steps["resource"].done and not steps["workflow"].done
    assert not setup_checklist(admin_user)["ready"]


def test_another_institution_does_not_count(admin_user):
    from apps.core.models import Institution

    other = Institution.objects.create(code="XU", name="Elsewhere")
    ResourceType.objects.create(institution=other, code="classroom", name="Classroom", category="space")
    Building.objects.create(institution=other, code="9", name="Block 9")
    steps = steps_by_key(admin_user)
    assert not steps["type"].done and not steps["block"].done


def test_facility_managers_see_it_without_the_add_person_link(facility_manager):
    steps = steps_by_key(facility_manager)
    assert steps["people"].add_url is None and steps["people"].view_url == reverse("manage:users")
    assert steps["type"].add_url and steps["workflow"].add_url and steps["resource"].add_url


@pytest.mark.parametrize("role", [Role.CUSTODIAN, Role.DEPT_HEAD, Role.STUDENT, Role.FACULTY])
def test_only_campus_wide_staff_get_a_checklist(make_user, role):
    assert setup_checklist(make_user(role)) is None


# ── Where it shows ──────────────────────────────────────────────────────────


def test_setup_page_shows_the_checklist_with_its_links(client, admin_user):
    html = signed_in(client, admin_user).get(SETUP).content.decode()
    assert "Getting started" in html
    assert "3 essential steps left before people can book" in html
    assert 'href="/manage/catalogue/?tab=types&amp;new=1"' in html
    assert f'href="{reverse("manage:user_new")}"' in html
    assert "Add people, change roles and deactivate accounts." in html


def test_ready_checklist_is_collapsed(client, admin_user, room, student):
    html = signed_in(client, admin_user).get(SETUP).content.decode()
    assert 'class="panel cfg-checklist is-ready"' in html and "Everything people need to book is in place" in html


def test_facility_manager_setup_page_has_no_add_person_link(client, facility_manager):
    html = signed_in(client, facility_manager).get(SETUP).content.decode()
    assert "Getting started" in html
    assert reverse("manage:user_new") not in html


def test_department_head_setup_page_has_no_checklist(client, make_user):
    hod = make_user(Role.DEPT_HEAD)
    resp = signed_in(client, hod).get(SETUP)
    assert resp.status_code == 200 and "Getting started" not in resp.content.decode()


@pytest.mark.parametrize("role", [Role.STUDENT, Role.FACULTY, Role.CUSTODIAN])
def test_setup_stays_closed_to_other_roles(client, make_user, role):
    assert signed_in(client, make_user(role)).get(SETUP).status_code == 403


def test_console_home_nudges_until_setup_is_ready(client, admin_user, lpu, room_type, student):
    signed_in(client, admin_user)
    html = client.get(reverse("manage:home")).content.decode()
    assert "Finish setting up LPU Reserve" in html and "1 essential step left" in html
    Resource.objects.create(institution=lpu, type=room_type, code="1-101", name="Room 1-101", capacity=40)
    assert "Finish setting up" not in client.get(reverse("manage:home")).content.decode()


# ── Empty-database states ───────────────────────────────────────────────────


def test_home_with_nothing_to_book(client, student, admin_user):
    html = signed_in(client, student).get("/home/").content.decode()
    assert "Nothing to book yet" in html and "once the facility office adds them" in html
    assert SETUP not in html
    client.logout()
    html = signed_in(client, admin_user).get("/home/").content.decode()
    assert "Nothing to book yet" in html and f'href="{SETUP}"' in html


def test_find_with_an_empty_catalogue(client, student, admin_user):
    html = signed_in(client, student).get("/find/").content.decode()
    assert "Nothing has been added to LPU Reserve yet" in html
    assert reverse("manage:resource_new") not in html
    client.logout()
    html = signed_in(client, admin_user).get("/find/").content.decode()
    assert f'href="{reverse("manage:resource_new")}"' in html


def test_find_with_no_match_is_still_a_no_match(client, student, room):
    html = signed_in(client, student).get("/find/?q=zzzz-nothing").content.decode()
    assert "Nothing has been added" not in html and "Clear search" in html


def test_console_screens_with_an_empty_catalogue(client, facility_manager):
    signed_in(client, facility_manager)
    board = client.get(reverse("manage:board")).content.decode()
    assert "Nothing has been added yet" in board and f'href="{reverse("manage:resource_new")}"' in board
    resources = client.get(reverse("manage:resources")).content.decode()
    assert "The catalogue is empty" in resources and f'href="{reverse("manage:resource_new")}"' in resources
    home = client.get(reverse("manage:home")).content.decode()
    assert "No resources on campus yet" in home


def test_custodian_board_keeps_its_own_message(client, custodian):
    html = signed_in(client, custodian).get(reverse("manage:board")).content.decode()
    assert "Once you're named custodian" in html.replace("&#x27;", "'")
    assert reverse("manage:resource_new") not in html


# ── Design-system inputs on the setup forms ─────────────────────────────────


def test_setup_forms_use_design_system_inputs(client, admin_user):
    signed_in(client, admin_user)
    for path, name in [
        ("/manage/catalogue/?tab=types&new=1", 'name="name"'),
        ("/manage/catalogue/?tab=buildings&new=1", 'name="code"'),
        ("/manage/catalogue/?tab=departments&new=1", 'name="code"'),
        (reverse("manage:user_new"), 'name="username"'),
    ]:
        html = client.get(path).content.decode()
        tag = html[html.rindex("<", 0, html.index(name)) : html.index(">", html.index(name))]
        assert 'class="input"' in tag, (path, tag)
    html = client.get(reverse("manage:user_new")).content.decode()
    assert 'class="select"' in html


def test_invalid_setup_fields_are_marked_for_assistive_tech(client, admin_user):
    resp = signed_in(client, admin_user).post(
        reverse("manage:user_new"), {"first_name": "A", "username": "a", "email": "nope", "role": "student"}
    )
    html = resp.content.decode()
    i = html.index('name="email"')
    tag = html[html.rindex("<", 0, i) : html.index(">", i)]
    assert 'aria-invalid="true"' in tag
