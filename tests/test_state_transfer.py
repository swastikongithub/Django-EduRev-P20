"""
Moving an installation's state to another database (apps.core.state_transfer, export_state,
import_state, state_inventory).

Each test builds a realistic source with the real services (timetable published, maintenance
scheduled, bookings pending and confirmed, a check-in, duplicate attempts, notifications), exports
it, wipes the database into a production-like target (an existing superuser with MFA, sitting on a
source user's primary key, and a second staff account), imports, and compares: counts, computed
availability, links, sanitised accounts, media, idempotency and the safety rails.
"""

from __future__ import annotations

import gzip
import io
import json
from datetime import time, timedelta

import pyotp
import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.urls import get_resolver, reverse

from apps.accounts import mfa
from apps.accounts.models import Role, User
from apps.approvals.models import Approval, ApprovalStep, ApprovalWorkflow
from apps.audit.models import AuditLog
from apps.bookings import services as bookings
from apps.bookings.models import Booking, BookingAttempt, BookingSlot, BookingStatus
from apps.catalogue.models import Resource, ResourceType
from apps.core import state_transfer as st
from apps.core.timeutil import trange
from apps.maintenance import services as maintenance
from apps.timetable import services as timetable
from apps.timetable.models import AcademicTerm, TimetableEntry

from .conftest import at

OWNER_PW = "x-test-password-owner"
DAYS = 3


@pytest.fixture
def source(lpu, room, room2, student, faculty, facility_manager, admin_user, monday, now):
    """A small but complete installation, built through the services the product uses."""
    wf = ApprovalWorkflow.objects.create(
        institution=lpu, name="Room 2 needs a manager", resource=room2, requester_roles=["student"]
    )
    ApprovalStep.objects.create(workflow=wf, order=1, approver_role="facility_manager", sla_hours=24)
    term = AcademicTerm.objects.create(
        institution=lpu, code="26271", name="Odd term", starts=monday, ends=monday + timedelta(days=30)
    )
    pub = timetable.stage(
        term,
        [
            TimetableEntry(
                resource=room, weekday=0, start_time=time(9), end_time=time(10), course_code="CSE326", section="K23"
            )
        ],
        actor=facility_manager,
    )
    timetable.publish(pub, facility_manager, now=now)
    maintenance.schedule(room, at(monday, 15), at(monday, 16), title="Projector service", actor=facility_manager)
    confirmed = bookings.create_booking(
        requester=student, resource=room, start=at(monday, 11), end=at(monday, 12), title="Study group", notify=False
    )
    pending = bookings.create_booking(
        requester=student, resource=room2, start=at(monday, 11), end=at(monday, 12), title="Club meet", notify=False
    )
    assert confirmed.status == BookingStatus.APPROVED and pending.status == BookingStatus.PENDING
    for _ in range(2):  # identical rows must stay two rows
        BookingAttempt.objects.create(
            user=student, resource=room, outcome="conflict", period=trange(at(monday, 11), at(monday, 12))
        )
    BookingAttempt.objects.filter(outcome="conflict").update(created_at=now)
    User.objects.filter(pk=admin_user.pk).update(is_superuser=True, is_staff=True)
    return {"room": room, "room2": room2, "confirmed": confirmed, "pending": pending, "monday": monday, "now": now}


def snapshot(source):
    days = [source["monday"] + timedelta(days=i) for i in range(DAYS)]
    return st.inventory(institution_code="LPU", resource_codes=["34-301", "34-302"], days=days, now=source["now"])


def wipe_to_production_like(taken_pk):
    """Delete everything the bundle covers, then add production's own accounts."""
    for spec, model in reversed(st.spec_models()):
        model._base_manager.all().delete()
    owner = User(pk=taken_pk, username="swastik", email="owner@example.test", role=Role.ADMIN)
    owner.is_superuser = owner.is_staff = True
    owner.set_password(OWNER_PW)
    owner.save()
    secret = pyotp.random_base32()
    User.objects.filter(pk=owner.pk).update(mfa_secret=mfa.encrypt(secret), mfa_enabled=True, mfa_last_step=7)
    demo = User.objects.create_user("Demo1", "demo1@example.test", OWNER_PW, role=Role.FACILITY_MANAGER)
    return User.objects.get(pk=owner.pk), demo, secret


def transfer(source, *, taken_pk):
    before = snapshot(source)
    bundle = st.export_bundle(institution_code="LPU")
    owner, demo, secret = wipe_to_production_like(taken_pk)
    report = st.import_bundle(bundle)
    return before, bundle, report, owner, demo, secret


# ── The whole state arrives, and computes the same availability ─────────────


def test_empty_target_receives_everything_with_identical_availability(source, student):
    before, bundle, report, owner, demo, _ = transfer(source, taken_pk=student.pk)
    after = snapshot(source)
    for label, n in before["counts"].items():
        expected = n + 2 if label == "accounts.User" else n  # plus the target's own swastik and Demo1
        assert after["counts"][label] == expected, label
    assert after["availability"] == before["availability"]
    states = {c.split(" ")[1] for d in after["availability"]["34-301"].values() for c in d}
    assert {"class", "maintenance", "booked", "free"} <= states
    assert "pending" in {c.split(" ")[1] for d in after["availability"]["34-302"].values() for c in d}


def test_links_follow_remapped_keys(source, student):
    student_username = student.username
    _, _, report, owner, _, _ = transfer(source, taken_pk=student.pk)
    moved = User.objects.get(username=student_username)
    assert moved.pk != student.pk  # its key was taken by the target's own account
    confirmed = Booking.objects.get(reference=source["confirmed"].reference)
    assert confirmed.requester_id == moved.pk and confirmed.booked_for_id == moved.pk
    assert BookingSlot.objects.get(booking=confirmed).resource_id == confirmed.resource_id
    # Non-key links (slot sources) point at the copied timetable entry and maintenance window.
    for slot in BookingSlot.objects.exclude(source_type=""):
        model = {"timetable_entry": TimetableEntry, "maintenance_window": "maintenance.MaintenanceWindow"}[
            slot.source_type
        ]
        if isinstance(model, str):
            from django.apps import apps

            model = apps.get_model(model)
        assert model.objects.filter(pk=slot.source_id, resource_id=slot.resource_id).exists()
    assert Approval.objects.get(booking__reference=source["pending"].reference).decision == "pending"
    assert report.kept_source_pk["catalogue.Resource"] == 2  # ids kept: the same curated photos


def test_identical_source_rows_are_not_collapsed(source, student):
    transfer(source, taken_pk=student.pk)
    assert BookingAttempt.objects.filter(outcome="conflict").count() == 2


def test_running_it_again_adds_nothing(source, student):
    _, bundle, _, _, _, _ = transfer(source, taken_pk=student.pk)
    counts = snapshot(source)["counts"]
    again = st.import_bundle(bundle)
    assert sum(again.created.values()) == 0
    assert snapshot(source)["counts"] == counts
    assert AuditLog.objects.filter(action="data.import_state").count() == 2  # each run is recorded


def test_partially_populated_target_is_matched_not_duplicated(source, student, lpu):
    bundle = st.export_bundle(institution_code="LPU")
    wipe_to_production_like(student.pk)
    existing = ResourceType.objects.create(institution=lpu, code="classroom", name="Old name", category="space", pk=999)
    report = st.import_bundle(bundle)
    assert ResourceType.objects.filter(code="classroom").count() == 1
    existing.refresh_from_db()
    assert existing.name == "Classroom"  # brought up to date with the source
    assert report.matched["catalogue.ResourceType"] == 1
    assert Resource.objects.get(code="34-301").type_id == 999


# ── People: preserved, sanitised, no escalation ─────────────────────────────


def test_existing_production_account_is_untouched(source, student):
    _, _, report, owner, demo, secret = transfer(source, taken_pk=student.pk)
    fresh = User.objects.get(username="swastik")
    assert (fresh.pk, fresh.is_superuser, fresh.is_staff, fresh.role) == (owner.pk, True, True, Role.ADMIN)
    assert fresh.check_password(OWNER_PW)
    assert fresh.mfa_enabled and mfa.decrypt(fresh.mfa_secret) == secret and fresh.mfa_last_step == 7
    assert User.objects.get(username="Demo1").check_password(OWNER_PW)


def test_a_source_account_with_the_same_username_attaches_to_the_existing_one(source, student, lpu):
    student.username = "swastik"
    student.save(update_fields=["username"])
    _, _, report, owner, _, _ = transfer(source, taken_pk=9999)
    assert "swastik" in report.existing_users_kept
    assert Booking.objects.get(reference=source["confirmed"].reference).requester_id == owner.pk
    assert User.objects.get(username="swastik").check_password(OWNER_PW)


def test_imported_accounts_are_sanitised(source, student, admin_user):
    transfer(source, taken_pk=student.pk)
    imported = User.objects.exclude(username__in=["swastik", "Demo1"])
    assert imported.count() >= 5
    for u in imported:
        assert not u.has_usable_password()
        assert not u.is_superuser and not u.is_staff  # the source admin was a superuser
        assert not u.mfa_enabled and u.mfa_secret == "" and u.mfa_last_step is None
        assert u.last_login is None and u.failed_logins == 0
        assert u.groups.filter(name=f"role:{u.role}").exists()
    assert User.objects.get(username=admin_user.username).role == Role.ADMIN


def test_tokens_are_regenerated(source, student):
    source_tokens = set(Booking.objects.values_list("qr_token", flat=True))
    source_feeds = set(User.objects.values_list("calendar_token", flat=True))
    transfer(source, taken_pk=student.pk)
    assert not source_tokens & set(Booking.objects.values_list("qr_token", flat=True))
    assert not source_feeds & set(
        User.objects.exclude(username__in=["swastik", "Demo1"]).values_list("calendar_token", flat=True)
    )


def test_the_bundle_holds_no_credentials(source, student, tmp_path):
    student.set_password("x-test-password-leak")
    student.save()
    User.objects.filter(pk=student.pk).update(mfa_secret=mfa.encrypt("JBSWY3DPEHPK3PXP"), mfa_enabled=True)
    path = tmp_path / "b.json.gz"
    call_command("export_state", str(path), stdout=io.StringIO())
    raw = gzip.decompress(path.read_bytes()).decode()
    student.refresh_from_db()
    for secret in (student.password, student.mfa_secret, str(student.calendar_token), source["confirmed"].qr_token):
        assert secret not in raw
    for word in ("pbkdf2", "argon2", "mfa_secret", "calendar_token", "qr_token", "password", "is_superuser"):
        assert word not in raw
    assert "sessions.session" not in raw and "audit.auditlog" not in raw


def test_privileged_imported_accounts_enrol_mfa_and_students_do_not(source, student, facility_manager, client):
    transfer(source, taken_pk=99999)
    for username, needs in ((facility_manager.username, True), (student.username, False)):
        u = User.objects.get(username=username)
        u.set_password("x-test-password-new")  # what an administrator does with changepassword
        u.save()
        c = Client()
        resp = c.post(reverse("accounts:login"), {"username": username, "password": "x-test-password-new"})
        assert (resp.url == reverse("accounts:mfa")) is needs, username
    assert (
        Client()
        .post(reverse("accounts:login"), {"username": student.username, "password": "x-test-password-123"})
        .status_code
        == 200
    )  # the development password is not a production credential


# ── The product works on the imported state ─────────────────────────────────


def test_search_booking_approval_pass_and_check_in_work_after_import(source, student, facility_manager, client):
    transfer(source, taken_pk=99999)
    s = User.objects.get(username=student.username)
    fm = User.objects.get(username=facility_manager.username)
    assert Resource.objects.get(code="34-301").search_vector  # rebuilt on the target, not copied

    client.force_login(s)
    assert "Room 34-301" in client.get("/find/?q=34-301").content.decode()
    pending = Booking.objects.get(reference=source["pending"].reference)
    approval = Approval.objects.get(booking=pending)
    from apps.approvals.services import decide

    decide(approval, fm, approve=True, now=source["now"])
    pending.refresh_from_db()
    assert pending.status == BookingStatus.APPROVED
    page = client.get(pending.get_absolute_url())
    assert page.status_code == 200 and b"Confirmed" in page.content
    assert client.get(reverse("checkins:pass", args=[pending.qr_token])).status_code == 200

    from apps.checkins.services import check_in, check_out

    live = Booking.objects.get(reference=source["confirmed"].reference)
    check_in(live, s, now=live.start + timedelta(minutes=1))
    check_out(Booking.objects.get(pk=live.pk), s, now=live.start + timedelta(minutes=30))
    assert Booking.objects.get(pk=live.pk).status == BookingStatus.COMPLETED

    new = bookings.create_booking(
        requester=s,
        resource=Resource.objects.get(code="34-301"),
        start=at(source["monday"], 13),
        end=at(source["monday"], 14),
        title="After import",
        notify=False,
    )
    assert new.status == BookingStatus.APPROVED and new.pk > max(b.pk for b in Booking.objects.exclude(pk=new.pk))


# ── Media ───────────────────────────────────────────────────────────────────


@pytest.fixture
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.STORAGES = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}}


def _photo(room, data=b"\x89PNG fake photo"):
    name = default_storage.save("resources/34-301.png", ContentFile(data))
    Resource.objects.filter(pk=room.pk).update(image=name)
    return name


def test_media_travels_and_keeps_its_reference(source, student, media_root):
    name = _photo(source["room"])
    bundle = st.export_bundle(institution_code="LPU")
    assert st.bundle_summary(bundle)["media_files"] == 1
    default_storage.delete(name)
    wipe_to_production_like(student.pk)
    report = st.import_bundle(bundle)
    assert report.media_uploaded == 1 and report.media_bytes == len(b"\x89PNG fake photo")
    assert Resource.objects.get(code="34-301").image.name == name
    with default_storage.open(name) as fh:
        assert fh.read() == b"\x89PNG fake photo"
    again = st.import_bundle(bundle)
    assert again.media_uploaded == 0 and again.media_present == 1  # no duplicate copies


def test_broken_media_reference_is_reported(source, student, media_root):
    Resource.objects.filter(pk=source["room"].pk).update(image="resources/gone.png")
    bundle = st.export_bundle(institution_code="LPU")
    assert st.bundle_summary(bundle)["media_missing"] == ["resources/gone.png"]
    wipe_to_production_like(student.pk)
    assert st.import_bundle(bundle).media_missing == ["resources/gone.png"]


def test_a_different_file_under_the_same_name_stops_the_import(source, student, media_root):
    name = _photo(source["room"])
    bundle = st.export_bundle(institution_code="LPU")
    wipe_to_production_like(student.pk)
    default_storage.delete(name)
    default_storage.save(name, ContentFile(b"someone else's photo"))
    with pytest.raises(st.TransferError, match="different contents"):
        st.import_bundle(bundle)
    assert not Resource.objects.exists()


# ── Safety rails ────────────────────────────────────────────────────────────


def test_dry_run_changes_nothing(source, student):
    bundle = st.export_bundle(institution_code="LPU")
    wipe_to_production_like(student.pk)
    report = st.import_bundle(bundle, dry_run=True)
    assert report.created["bookings.Booking"] == 2
    assert not Booking.objects.exists() and not Resource.objects.exists()
    assert not AuditLog.objects.filter(action="data.import_state").exists()


def test_production_needs_explicit_confirmation(source, student, tmp_path, settings):
    path = tmp_path / "b.json.gz"
    st.write_bundle(st.export_bundle(institution_code="LPU"), path)
    wipe_to_production_like(student.pk)
    settings.DEBUG = False
    with pytest.raises(CommandError, match="production-confirm"):
        call_command("import_state", str(path))
    assert not Booking.objects.exists()
    call_command("import_state", str(path), "--production-confirm", stdout=io.StringIO())
    assert Booking.objects.count() == 2


def test_a_bundle_from_another_schema_is_refused(source, student):
    bundle = st.export_bundle(institution_code="LPU")
    bundle["migrations"] = bundle["migrations"][:-1]
    wipe_to_production_like(student.pk)
    with pytest.raises(st.TransferError, match="different migrations"):
        st.import_bundle(bundle)
    assert not Resource.objects.exists()


def test_a_dangling_reference_stops_everything(source, student):
    bundle = st.export_bundle(institution_code="LPU")
    bundle["models"]["catalogue.ResourceType"] = []
    wipe_to_production_like(student.pk)
    with pytest.raises(st.TransferError, match="not in the bundle"):
        st.import_bundle(bundle)
    assert not Booking.objects.exists() and not Resource.objects.exists()


def test_there_is_no_web_route_to_any_of_it():
    patterns = json.dumps([str(p.pattern) for p in get_resolver().url_patterns], default=str).lower()
    for word in ("import_state", "export_state", "state_inventory", "import-state", "export-state"):
        assert word not in patterns


def test_inventory_command_prints_counts_and_availability(source, capsys):
    days = ",".join((source["monday"] + timedelta(days=i)).isoformat() for i in range(2))
    call_command("state_inventory", "--resources", "34-301", "--days", days, "--now", source["now"].isoformat())
    out = json.loads(capsys.readouterr().out)
    assert out["counts"]["bookings.Booking"] == 2 and len(out["availability_digest"]["34-301"]) == 16


# ── Fresh production credentials ────────────────────────────────────────────


def _export_with_credentials(source, existing=("swastik", "Demo1")):
    bundle = st.export_bundle(institution_code="LPU")
    issued = st.generate_credentials(bundle, existing_usernames=existing)
    return bundle, issued


def test_every_new_account_gets_its_own_valid_password(source, student, facility_manager):
    from django.contrib.auth import password_validation

    student.username = "swastik"  # the source's own swastik maps to the target's, and gets nothing
    student.save(update_fields=["username"])
    bundle, issued = _export_with_credentials(source)
    usernames = {i["username"] for i in issued}
    assert "swastik" not in usernames and "Demo1" not in usernames
    passwords = [i["password"] for i in issued]
    assert len(set(passwords)) == len(passwords) == User.objects.exclude(username="swastik").count()
    for i in issued:
        probe = User(username=i["username"], email=i["email"])
        password_validation.validate_password(i["password"], probe)
        assert i["username"].lower() not in i["password"].lower()

    owner, demo, _ = wipe_to_production_like(99999)
    report = st.import_bundle(bundle)
    assert st.accounts_digest(report.created_usernames) == bundle["credentials"]["accounts_digest"]
    for i in issued:
        u = User.objects.get(username=i["username"])
        assert u.check_password(i["password"]) and u.password != i["password"]
        assert u.password.startswith("pbkdf2_") or u.password.startswith("argon2")
    assert User.objects.get(username="swastik").check_password(OWNER_PW)
    assert User.objects.get(username="Demo1").check_password(OWNER_PW)


def test_reruns_never_reset_a_password(source, student):
    bundle, issued = _export_with_credentials(source)
    wipe_to_production_like(99999)
    st.import_bundle(bundle)
    hashes = dict(User.objects.values_list("username", "password"))
    _, again = _export_with_credentials(source, existing=())  # even a careless second export
    st.import_bundle(bundle)
    assert dict(User.objects.values_list("username", "password")) == hashes
    for i in issued:
        assert User.objects.get(username=i["username"]).check_password(i["password"])


def test_plaintext_passwords_reach_no_log_audit_row_or_bundle_text(source, student, caplog, tmp_path):
    caplog.set_level("DEBUG")
    bundle, issued = _export_with_credentials(source)
    path = tmp_path / "b.json.gz"
    st.write_bundle(bundle, path)
    raw = gzip.decompress(path.read_bytes()).decode()
    wipe_to_production_like(99999)
    st.import_bundle(bundle)
    audit = json.dumps(list(AuditLog.objects.values()), default=str)
    stored = json.dumps(list(User.objects.values()), default=str)
    for i in issued:
        for where in (raw, audit, caplog.text, stored):
            assert i["password"] not in where
    assert "pbkdf2" not in audit


def test_generated_accounts_follow_the_existing_mfa_policy(source, student, facility_manager, admin_user):
    bundle, issued = _export_with_credentials(source)
    by_name = {i["username"]: i["password"] for i in issued}
    wipe_to_production_like(99999)
    st.import_bundle(bundle)
    for username, needs in ((facility_manager.username, True), (admin_user.username, True), (student.username, False)):
        resp = Client().post(reverse("accounts:login"), {"username": username, "password": by_name[username]})
        assert (resp.url == reverse("accounts:mfa")) is needs, username
        assert not User.objects.get(username=username).mfa_enabled  # enrols fresh, if at all


def test_credentials_file_is_written_outside_the_repo_and_never_printed(source, tmp_path, settings):
    bundle_path, creds = tmp_path / "b.json.gz", tmp_path / "LPU_RESERVE_DEMO_CREDENTIALS.md"
    out = tmp_path / "stdout.txt"
    with open(out, "w") as fh:
        call_command(
            "export_state", str(bundle_path), "--credentials", str(creds), "--existing-usernames", "swastik,Demo1",
            stdout=fh,
        )  # fmt: skip
    text = creds.read_text(encoding="utf-8")
    assert text.startswith("# LPU Reserve Demo Accounts")
    assert "| Name | Username | Role | Email | VID | Password |" in text
    rows = [line for line in text.splitlines() if line.startswith("| ") and "`" in line]
    assert len(rows) == User.objects.count()
    printed = out.read_text()
    assert "passwords generated" in printed
    for row in rows:
        assert row.split("`")[1] not in printed

    with pytest.raises(CommandError, match="already exists"):
        call_command("export_state", str(bundle_path), "--credentials", str(creds))
    inside = settings.BASE_DIR / "LPU_RESERVE_DEMO_CREDENTIALS.md"
    with pytest.raises(CommandError, match="outside the repository"):
        call_command("export_state", str(bundle_path), "--credentials", str(inside))
    assert not inside.exists()


def test_credentials_markdown_escapes_table_cells():
    md = st.credentials_markdown(
        [{"name": "A | B", "username": "ab", "role": "Student", "email": "a@x.test", "vid": "", "password": "Xy-1"}]
    )
    assert "A \| B" in md and "`Xy-1`" in md


# ── Public demo Student accounts (README) ───────────────────────────────────


def test_public_demo_accounts_are_students_signing_in_by_vid(source, student, faculty, tmp_path):
    User.objects.filter(pk=student.pk).update(vid="12321411")
    User.objects.filter(pk=faculty.pk).update(vid="30001")
    bundle = st.export_bundle(institution_code="LPU")
    with pytest.raises(st.TransferError, match="Student"):
        st.generate_credentials(bundle, existing_usernames=["swastik"], public_vids=["30001"])
    with pytest.raises(st.TransferError, match="No account"):
        st.generate_credentials(bundle, existing_usernames=["swastik"], public_vids=["99999999"])
    issued = st.generate_credentials(bundle, existing_usernames=["swastik"], public_vids=["12321411"])
    public = [i for i in issued if i["public"]]
    assert [i["vid"] for i in public] == ["12321411"]

    md = st.public_demo_markdown(issued)
    assert md.splitlines()[0] == "| Student ID | Password |" and len(md.splitlines()) == 3
    assert student.username not in md and student.email not in md and "@" not in md
    private = st.credentials_markdown(issued)
    assert "(public demo, in README)" in private and private.count("(public demo, in README)") == 1

    wipe_to_production_like(99999)
    st.import_bundle(bundle)
    c = Client()
    resp = c.post(reverse("accounts:login"), {"username": "12321411", "password": public[0]["password"]})
    assert resp.status_code == 302 and resp.url == "/home/"  # VID sign-in, no MFA for a student
    u = User.objects.get(vid="12321411")
    assert u.role == Role.STUDENT and not u.is_staff and not u.is_superuser and not u.mfa_enabled


def test_public_demo_needs_both_private_files(source, tmp_path):
    with pytest.raises(CommandError, match="--public-demo-out"):
        call_command(
            "export_state", str(tmp_path / "b.json.gz"), "--credentials", str(tmp_path / "c.md"),
            "--public-demo-vids", "12321411",
        )  # fmt: skip
