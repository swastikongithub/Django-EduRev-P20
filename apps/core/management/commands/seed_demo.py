"""
Seed a believable LPU Reserve campus for demos and load tests.

    python manage.py seed_demo                    # idempotent: upserts reference data; builds history once
    python manage.py seed_demo --reset            # wipe bookings & co. (never the audit log) and rebuild
    python manage.py seed_demo --weeks-history 8  # how far back the booking history goes

Reference data (departments, people, blocks, resources, rules, workflows, inventory, the
academic term) is upserted by natural key on every run. Domain data (timetable publication,
bookings, check-ins, maintenance, notifications, analytics snapshots) is generated only when
none exists yet, or after ``--reset`` — so running the command twice never duplicates history.

Past activity is written directly (the booking service rightly refuses past times); every
present and future booking goes through the real services — ``create_booking``,
``create_series``, ``approvals.decide``, ``check_in``, ``maintenance.schedule``,
``report_breakdown``, ``timetable.publish`` — so the rules, the ledger and the
notifications behave exactly as they will in the demo.

Passwords: set ``DEMO_PASSWORD`` to give every seeded account that password; otherwise new
accounts get an unusable password (use the one-click persona sign-in with ``DEMO_MODE=1``).
"""

from __future__ import annotations

import math
import os
import random
import time as clock
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from itertools import batched
from unittest import mock

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import Department, Role, User
from apps.analytics import services as analytics
from apps.analytics.models import UtilisationSnapshot
from apps.approvals import services as approvals
from apps.approvals.models import Approval, ApprovalStep, ApprovalWorkflow, Decision
from apps.bookings import services as bookings
from apps.bookings.models import (
    AttemptOutcome,
    Booking,
    BookingAttempt,
    BookingSeries,
    BookingSlot,
    BookingStatus,
    SlotKind,
)
from apps.catalogue.models import (
    Building,
    Custodian,
    Feature,
    Resource,
    ResourceAttribute,
    ResourceType,
    SavedResource,
)
from apps.catalogue.search import refresh_search_vectors
from apps.checkins import services as checkins
from apps.checkins.models import CheckIn, CheckInMethod, NoShow, Restriction
from apps.core import demo_data as D
from apps.core.errors import DomainError
from apps.core.models import Institution, SweepRun
from apps.core.timeutil import aware, ceil_to, floor_to, minutes_between, trange
from apps.inventory.models import InventoryItem, Issuance, IssuanceStatus, ItemKind, StockMovement
from apps.maintenance import services as maintenance
from apps.maintenance.models import BreakdownReport, MaintenanceWindow, ReportStatus, WindowStatus
from apps.notifications.models import Kind, Notification
from apps.rules import services as rules
from apps.rules.models import AvailabilityRule, Blackout, BookingPolicy, Quota, RestrictionTier, Scope
from apps.timetable import services as timetable
from apps.timetable.models import AcademicTerm, TimetableEntry, TimetablePublication

STUDENT_TEMPLATE = "s{n:03d}"
MAINT_SOURCE = "maintenance_window"
CLASS_SOURCE = "timetable_entry"


@contextmanager
def _no_outbound_email():
    """
    Seeding creates hundreds of notifications. Keep them in the in-app inbox only: the
    addresses are @lpu.example (reserved, undeliverable) and a dev box may have a live worker.
    """
    from apps.notifications import tasks

    with mock.patch.object(tasks.send_notification_email, "delay", lambda *a, **k: None):
        yield


def _dt(value: str) -> datetime:
    return timezone.make_aware(datetime.strptime(value, "%Y-%m-%d %H:%M"))


def _hm(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def _local(dt: datetime) -> datetime:
    return timezone.localtime(dt)


def _overlaps(intervals, s, e) -> bool:
    return any(s < b and a < e for a, b, *_ in intervals)


@dataclass
class Plan:
    """One history booking before it becomes rows."""

    resource: Resource
    user: User
    start: datetime
    end: datetime
    title: str
    attendees: int = 1
    group_label: str = ""
    status: str = ""  # forced status, else drawn
    early: bool | None = None


class Command(BaseCommand):
    help = "Seed a realistic LPU campus: people, resources, rules, timetable, history and live demo bookings."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete bookings and related data first.")
        parser.add_argument("--weeks-history", type=int, default=6, help="Weeks of past bookings (default 6).")
        parser.add_argument("--seed", type=int, default=2026, help="Random seed (default 2026).")

    # ── Entry point ─────────────────────────────────────────────────────────

    def handle(self, *args, reset=False, weeks_history=6, seed=2026, **opts):
        if weeks_history < 1 or weeks_history > 26:
            raise CommandError("--weeks-history must be between 1 and 26.")
        t0 = clock.monotonic()
        self.seed = seed
        self.rng = random.Random(seed)
        self.now = timezone.now().replace(microsecond=0)
        self.today = _local(self.now).date()
        self.hist_start = self.today - timedelta(weeks=weeks_history)
        self.cheat: dict[str, list[str]] = defaultdict(list)
        self.notes: list[str] = []

        with _no_outbound_email():
            self.inst = self._institution()
            if reset:
                self._step("Reset", self._reset)
            fresh = not self._domain_exists()
            self._step("Organisation & people", self._people)
            self._step("Campus & resources", lambda: self._campus(fresh))
            self._step("Rules & workflows", self._rules)
            self._step("Inventory & term", lambda: self._inventory_and_term(fresh))
            self._load_context()
            if fresh:
                self._step("Timetable", self._timetable)
                self._step("History", self._history)
                self._step("Live & upcoming bookings", self._future)
                self._step("Maintenance & breakdowns", self._maintenance_future)
                self._step("Notifications", self._notifications)
                self._step("Analytics backfill", lambda: analytics.backfill(self.hist_start, self.today, self.inst.pk))
            else:
                self.notes.append(
                    "Bookings/timetable already exist — reference data refreshed, history left untouched. "
                    "Use --reset to rebuild (and to get a fresh cheat-sheet with today's times)."
                )
            self._step("Search vectors", lambda: refresh_search_vectors(Resource.objects.filter(institution=self.inst)))

        self._summary(clock.monotonic() - t0)

    def _step(self, label, fn):
        t = clock.monotonic()
        with transaction.atomic():
            fn()
        self.stdout.write(f"  {label:<28} {clock.monotonic() - t:6.1f}s")

    def _institution(self):
        inst, _ = Institution.objects.update_or_create(
            code=getattr(settings, "DEFAULT_INSTITUTION_CODE", D.INSTITUTION["code"]),
            defaults={"name": D.INSTITUTION["name"], "short_name": D.INSTITUTION["short_name"]},
        )
        return inst

    def _domain_exists(self) -> bool:
        return (
            Booking.objects.filter(institution=self.inst).exists()
            or TimetablePublication.objects.filter(institution=self.inst).exists()
            or MaintenanceWindow.objects.filter(institution=self.inst).exists()
        )

    def _reset(self):
        inst = self.inst
        StockMovement.objects.filter(item__institution=inst).delete()
        Issuance.objects.filter(booking__institution=inst).delete()
        Approval.objects.filter(booking__institution=inst).delete()
        CheckIn.objects.filter(booking__institution=inst).delete()
        NoShow.objects.filter(institution=inst).delete()
        BookingSlot.objects.filter(resource__institution=inst).delete()
        Booking.objects.filter(institution=inst).delete()
        BookingSeries.objects.filter(institution=inst).delete()
        BookingAttempt.objects.filter(resource__institution=inst).delete()
        Restriction.objects.filter(institution=inst).delete()
        BreakdownReport.objects.filter(institution=inst).delete()
        MaintenanceWindow.objects.filter(institution=inst).delete()
        TimetableEntry.objects.filter(publication__institution=inst).delete()
        TimetablePublication.objects.filter(institution=inst).delete()
        UtilisationSnapshot.objects.filter(resource__institution=inst).delete()
        Notification.objects.filter(user__institution=inst).delete()
        SweepRun.objects.all().delete()

    # ── Reference data ──────────────────────────────────────────────────────

    def _people(self):
        inst = self.inst
        self.depts = {}
        for code, name, school in D.DEPARTMENTS:
            self.depts[code], _ = Department.objects.update_or_create(
                institution=inst, code=code, defaults={"name": name, "school": school}
            )
        password = os.environ.get("DEMO_PASSWORD", "")
        # Hash once: PBKDF2 at Django's work factor costs ~0.3 s per call, and every account shares it.
        self.password_hash = make_password(password) if password else None

        self.p = {}  # persona username -> User
        for spec in D.PERSONAS:
            spec = dict(spec)
            first, last, vid = spec["first_name"], spec["last_name"], spec["vid"]
            email = f"{first}.{vid}" if spec["role"] == Role.STUDENT else f"{first}.{last}"
            self.p[spec["username"]] = self._user(
                spec["username"],
                first=first,
                last=last,
                role=spec["role"],
                dept=spec["dept"],
                vid=vid,
                email=email,
                section=spec.get("section", ""),
                programme=spec.get("programme", ""),
                designation=spec.get("designation", ""),
                phone=spec.get("phone", ""),
                is_staff=spec.get("is_staff", False),
                is_superuser=spec.get("is_superuser", False),
            )

        self.staff_by_vid = {}
        for vid, first, last, role, dept, designation in D.STAFF:
            username = f"{first}.{last}".lower().replace(" ", "")
            self.staff_by_vid[vid] = self._user(
                username,
                first=first,
                last=last,
                role=role,
                dept=dept,
                vid=vid,
                email=f"{first}.{last}",
                designation=designation,
            )

        rng = random.Random(f"{self.seed}-students")
        total = sum(w for _, w in D.STUDENT_MIX)
        counts = [(code, round(w * D.BACKGROUND_STUDENTS / total)) for code, w in D.STUDENT_MIX]
        counts[0] = (counts[0][0], counts[0][1] + D.BACKGROUND_STUDENTS - sum(c for _, c in counts))
        self.students = []
        n = 0
        for dept, k in counts:
            for _ in range(k):
                n += 1
                female = rng.random() < 0.45
                first = rng.choice(D.FIRST_NAMES_F if female else D.FIRST_NAMES_M)
                last = rng.choice(D.LAST_NAMES)
                section = rng.choice(D.SECTIONS[dept])
                vid = f"12{section[2]}2{(37 * n + 1300) % 10000:04d}"
                self.students.append(
                    self._user(
                        STUDENT_TEMPLATE.format(n=n),
                        first=first,
                        last=last,
                        role=Role.STUDENT,
                        dept=dept,
                        vid=vid,
                        email=f"{first}.{vid}",
                        section=section,
                        programme=D.PROGRAMMES[dept],
                    )
                )

    def _user(self, username, *, first, last, role, dept, vid, email, section="", programme="", designation="",
              phone="", is_staff=False, is_superuser=False) -> User:  # fmt: skip
        user = User.objects.filter(username=username).first()
        created = user is None
        if created:
            user = User(username=username)
        user.institution = self.inst
        user.first_name, user.last_name = first, last
        user.role = role
        user.department = self.depts.get(dept)
        user.vid = vid
        user.email = f"{email.lower().replace(' ', '')}@{D.EMAIL_DOMAIN}"
        user.section, user.programme, user.designation, user.phone = section, programme, designation, phone
        user.is_staff, user.is_superuser, user.is_active = is_staff, is_superuser, True
        user.failed_logins, user.locked_until = 0, None
        if self.password_hash:
            user.password = self.password_hash
        elif created:
            user.set_unusable_password()
        user.save()  # post_save keeps the role group in sync
        return user

    def _person(self, key) -> User:
        """Persona username, background student username, or staff VID."""
        if key in self.p:
            return self.p[key]
        if key in self.staff_by_vid:
            return self.staff_by_vid[key]
        return User.objects.get(username=key)

    def _campus(self, fresh):
        inst = self.inst
        self.buildings = {}
        for code, name, zone, desc, x, y in D.BUILDINGS:
            self.buildings[code], _ = Building.objects.update_or_create(
                institution=inst,
                code=code,
                defaults={"name": name, "zone": zone, "description": desc, "map_x": x, "map_y": y},
            )
        self.types = {}
        for code, name, plural, cat, icon, accent, roles, order, desc in D.RESOURCE_TYPES:
            self.types[code], _ = ResourceType.objects.update_or_create(
                institution=inst,
                code=code,
                defaults={
                    "name": name,
                    "plural": plural,
                    "category": cat,
                    "icon": icon,
                    "accent": accent,
                    "allowed_roles": list(roles),
                    "sort_order": order,
                    "description": desc,
                },
            )
        features = {}
        for name, icon, keywords in D.FEATURES:
            features[name], _ = Feature.objects.update_or_create(
                institution=inst, name=name, defaults={"icon": icon, "keywords": keywords}
            )

        for spec in D.RESOURCES:
            assert spec["art"] in D.ART_KEYS, spec["code"]
            defaults = {
                "type": self.types[spec["type"]],
                "name": spec["name"],
                "slug": slugify(f"{spec['code']}-{spec['name']}")[:80],
                "tagline": spec["tagline"],
                "description": spec["description"],
                "capacity": spec["capacity"],
                "building": self.buildings[spec["building"]],
                "floor": spec["floor"],
                "room": spec["room"],
                "department": self.depts.get(spec["dept"]),
                "acquisition_cost": Decimal(str(round(spec["cost"], 2))) if spec["cost"] else None,
                "art": spec["art"],
                "is_bookable": True,
            }
            status = {"status": spec["status"], "status_note": spec["status_note"]}
            # On a refresh run, leave live status alone (a critical breakdown may have taken it offline).
            if fresh:
                defaults.update(status)
            r, _ = Resource.objects.update_or_create(
                institution=inst, code=spec["code"], defaults=defaults, create_defaults={**defaults, **status}
            )
            r.features.set([features[f] for f in spec["features"]])
            r.attributes.all().delete()
            ResourceAttribute.objects.bulk_create(
                [ResourceAttribute(resource=r, key=k, value=v, sort_order=i) for i, (k, v) in enumerate(spec["attrs"])]
            )
            if spec["custodian"]:
                keeper = self._person(spec["custodian"])
                Custodian.objects.get_or_create(resource=r, user=keeper, defaults={"is_primary": True})
                Custodian.objects.filter(resource=r).exclude(user=keeper).delete()

        for username, codes in D.SAVED_RESOURCES.items():
            for code in codes:
                SavedResource.objects.get_or_create(
                    user=self.p[username], resource=Resource.objects.get(institution=inst, code=code)
                )

    def _rules(self):
        inst = self.inst
        BookingPolicy.objects.update_or_create(
            institution=inst, scope=Scope.CAMPUS, resource_type=None, resource=None, defaults=D.CAMPUS_POLICY
        )
        for code, values in D.TYPE_POLICIES.items():
            BookingPolicy.objects.update_or_create(
                institution=inst, scope=Scope.TYPE, resource_type=self.types[code], resource=None, defaults=values
            )
        for code, values in D.RESOURCE_POLICIES.items():
            r = Resource.objects.get(institution=inst, code=code)
            BookingPolicy.objects.update_or_create(
                institution=inst, scope=Scope.RESOURCE, resource=r, resource_type=None, defaults=values
            )

        AvailabilityRule.objects.filter(
            institution=inst, scope=Scope.TYPE, resource_type__in=self.types.values()
        ).delete()
        AvailabilityRule.objects.bulk_create(
            [
                AvailabilityRule(
                    institution=inst,
                    scope=Scope.TYPE,
                    resource_type=self.types[code],
                    weekday=wd,
                    opens=_hm(opens),
                    closes=_hm(closes),
                )
                for code, (days, opens, closes) in D.HOURS.items()
                for wd in days
            ]
        )

        for title, kind, scope, target, start, end, exempt, note in D.BLACKOUTS:
            Blackout.objects.update_or_create(
                institution=inst,
                title=title,
                defaults={
                    "kind": kind,
                    "scope": scope,
                    "resource_type": self.types[target] if scope == Scope.TYPE else None,
                    "resource": Resource.objects.get(institution=inst, code=target)
                    if scope == Scope.RESOURCE
                    else None,
                    "building": None,
                    "period": trange(_dt(start), _dt(end)),
                    "exempt_roles": list(exempt),
                    "note": note,
                },
            )

        for name, role, dept, type_code, period, max_hours, max_bookings in D.QUOTAS:
            Quota.objects.update_or_create(
                institution=inst,
                name=name,
                defaults={
                    "role": role or "",
                    "department": self.depts[dept] if dept else None,
                    "resource_type": self.types[type_code] if type_code else None,
                    "period": period,
                    "max_hours": Decimal(max_hours) if max_hours is not None else None,
                    "max_bookings": max_bookings,
                    "active": True,
                },
            )

        for no_shows, window, days, label in D.RESTRICTION_TIERS:
            RestrictionTier.objects.update_or_create(
                institution=inst,
                no_shows=no_shows,
                defaults={"window_days": window, "restrict_days": days, "label": label},
            )

        for name, desc, type_code, res_code, roles, min_att, min_dur, auto, priority, steps in D.WORKFLOWS:
            wf, _ = ApprovalWorkflow.objects.update_or_create(
                institution=inst,
                name=name,
                defaults={
                    "description": desc,
                    "resource_type": self.types[type_code] if type_code else None,
                    "resource": Resource.objects.get(institution=inst, code=res_code) if res_code else None,
                    "requester_roles": list(roles),
                    "min_attendees": min_att,
                    "min_duration_minutes": min_dur,
                    "auto_approve": auto,
                    "priority": priority,
                    "active": True,
                },
            )
            wf.steps.all().delete()
            ApprovalStep.objects.bulk_create(
                [
                    ApprovalStep(workflow=wf, order=i, approver_role=role, sla_hours=sla)
                    for i, (role, sla) in enumerate(steps, start=1)
                ]
            )

    def _inventory_and_term(self, fresh):
        inst = self.inst
        for sku, name, kind, unit, res_code, type_code, total, available, reorder, per, desc in D.INVENTORY:
            defaults = {
                "name": name,
                "kind": kind,
                "unit": unit,
                "resource": Resource.objects.get(institution=inst, code=res_code) if res_code else None,
                "resource_type": self.types[type_code] if type_code else None,
                "reorder_level": reorder,
                "max_per_booking": per,
                "description": desc,
            }
            stock = {"quantity_total": total, "quantity_available": available}
            if fresh:
                defaults.update(stock)
            InventoryItem.objects.update_or_create(
                institution=inst, sku=sku, defaults=defaults, create_defaults={**defaults, **stock}
            )
        self.term, _ = AcademicTerm.objects.update_or_create(
            institution=inst,
            code=D.TERM["code"],
            defaults={"name": D.TERM["name"], "starts": D.TERM["starts"], "ends": D.TERM["ends"]},
        )

    # ── Lookup tables for generation ────────────────────────────────────────

    def _load_context(self):
        inst = self.inst
        self.resources = list(
            Resource.objects.filter(institution=inst).select_related("type", "building", "department").order_by("pk")
        )
        self.res = {r.code: r for r in self.resources}
        self.policy = {r.pk: rules.policy_for(r) for r in self.resources}
        self.hours = {r.pk: rules.weekly_hours(r) for r in self.resources}
        self.custodian_of = {
            c.resource_id: c.user
            for c in Custodian.objects.filter(resource__institution=inst).select_related("user").order_by("-is_primary")
        }
        self.head_of = {
            u.department_id: u for u in User.objects.filter(institution=inst, role=Role.DEPT_HEAD, is_active=True)
        }
        self.workflows = list(
            ApprovalWorkflow.objects.filter(institution=inst, active=True).prefetch_related("steps").order_by("pk")
        )
        self.blackouts = list(Blackout.objects.filter(institution=inst))
        self.items = defaultdict(list)
        for item in InventoryItem.objects.filter(institution=inst):
            for r in self.resources:
                if item.resource_id == r.pk or (item.resource_id is None and item.resource_type_id == r.type_id):
                    self.items[r.pk].append(item)

        reserved = {"student", "student2", D.NO_SHOW_DEMO_STUDENT}
        students = [u for u in self.students if u.username not in reserved]
        staff = list(self.staff_by_vid.values())
        faculty = [u for u in staff if u.role == Role.FACULTY]
        self.pools = {
            Role.STUDENT: students,
            Role.FACULTY: faculty + [self.p["faculty"]] * 3,
            Role.STAFF: [u for u in staff if u.role == Role.STAFF],
            Role.DEPT_HEAD: [u for u in staff if u.role == Role.DEPT_HEAD] + [self.p["hod"]] * 2,
        }
        self.students_by_dept = defaultdict(list)
        for u in students:
            self.students_by_dept[u.department_id].append(u)
        self.faculty_by_dept = defaultdict(list)
        for u in faculty:
            self.faculty_by_dept[u.department_id].append(u)
        self.flaky = {u.pk for u in self.students if u.username in D.FLAKY_STUDENTS}

        # Per-user load, so generated history stays inside the quotas the rules enforce.
        self.week_hours = defaultdict(float)
        self.week_type_hours = defaultdict(float)
        self.day_count = defaultdict(int)
        self.user_busy = defaultdict(list)
        self.no_show_count = defaultdict(int)
        # Per-resource-day claimed time: (start, end, kind)
        self.busy = defaultdict(list)

    def _workflow_for(self, resource, role, attendees, minutes):
        """In-memory twin of approvals.services.resolve_workflow (no query per history booking)."""
        matching = [
            w
            for w in self.workflows
            if (
                w.resource_id == resource.pk
                or (w.resource_id is None and w.resource_type_id == resource.type_id)
                or (w.resource_id is None and w.resource_type_id is None)
            )
            and (not w.requester_roles or role in w.requester_roles)
            and (w.min_attendees is None or attendees >= w.min_attendees)
            and (w.min_duration_minutes is None or minutes >= w.min_duration_minutes)
        ]
        if not matching:
            return None
        matching.sort(key=lambda w: (w.specificity, w.priority), reverse=True)
        chosen = matching[0]
        if not chosen.auto_approve and not chosen.steps.all():
            return None
        return chosen

    def _needs_approval(self, resource, role, minutes, attendees=1):
        wf = self._workflow_for(resource, role, attendees, minutes)
        return bool(wf and not wf.auto_approve)

    def _approver(self, role, resource) -> User:
        if role == "custodian":
            return self.custodian_of.get(resource.pk) or self.p["facility"]
        if role == "dept_head":
            return self.head_of.get(resource.department_id) or self.p["facility"]
        if role == "facility_manager":
            return self.p["facility"]
        return self.p["admin"]

    # ── Timetable ───────────────────────────────────────────────────────────

    def _timetable_rows(self):
        rng = random.Random(f"{self.seed}-timetable")
        rows, section_busy, faculty_busy = [], set(), set()
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        for code, pool in D.TIMETABLE_ROOMS.items():
            is_lab = pool.endswith("_lab")
            is_theatre = "-LT-" in code
            for wd in range(5):
                taken = []
                want = rng.randint(2, 4) if is_lab else rng.randint(2, 3) if is_theatre else rng.randint(4, 6)
                starts = [8, 9, 10, 11, 13, 14, 15] if is_lab else [8, 9, 10, 11, 12, 13, 14, 15, 16]
                tries = 0
                while len(taken) < want and tries < 60:
                    tries += 1
                    dur = 2 if is_lab else 1
                    h = rng.choice(starts)
                    if h + dur > 17 or any(h < e and s < h + dur for s, e in taken):
                        continue
                    course, title = rng.choice(D.COURSES[pool])
                    if is_theatre:
                        a, b = rng.sample(D.TIMETABLE_SECTIONS[pool], 2)
                        sections = [a, b]
                        section = f"{a}+{b}"
                    else:
                        section = rng.choice(D.TIMETABLE_SECTIONS[pool])
                        sections = [section]
                    teacher = rng.choice(D.TIMETABLE_FACULTY[pool])
                    hours = range(h, h + dur)
                    if any((s, wd, x) in section_busy for s in sections for x in hours):
                        continue
                    if any((teacher, wd, x) in faculty_busy for x in hours):
                        continue
                    for x in hours:
                        faculty_busy.add((teacher, wd, x))
                        for s in sections:
                            section_busy.add((s, wd, x))
                    taken.append((h, h + dur))
                    kind = "Practical" if is_lab else ("Tutorial" if rng.random() < 0.1 else "Lecture")
                    rows.append(
                        {
                            "room_code": code,
                            "day": day_names[wd],
                            "start": f"{h:02d}:00",
                            "end": f"{h + dur:02d}:00",
                            "course_code": course,
                            "course_title": title,
                            "section": section,
                            "faculty": teacher,
                            "kind": kind,
                        }
                    )
        return rows

    def _timetable(self):
        entries, errors = timetable.parse_rows(self._timetable_rows(), self.inst.pk)
        if errors:
            raise CommandError("Generated timetable is invalid: " + "; ".join(errors[:5]))
        actor = self.p["facility"]
        pub = timetable.stage(
            self.term, entries, source="p13-api", actor=actor, notes="Imported from the UMS timetable export."
        )
        result = timetable.publish(pub, actor, now=self.now, enforce_permissions=False)
        self.publication = result["publication"]

        # publish() writes occurrences from today on; a timetable live since term start also
        # claimed the weeks behind us, which the utilisation history needs.
        self.classes = defaultdict(list)  # (resource_id, weekday) -> [(start_time, end_time, label)]
        entries = list(self.publication.entries.all())
        for e in entries:
            self.classes[(e.resource_id, e.weekday)].append((e.start_time, e.end_time, e.label))
        past = []
        d = max(self.term.starts, self.hist_start)
        while d <= self.today:
            for e in entries:
                if e.weekday != d.weekday():
                    continue
                s, t = aware(d, e.start_time), aware(d, e.end_time)
                if t <= self.now:
                    past.append(
                        BookingSlot(
                            resource_id=e.resource_id,
                            period=trange(s, t),
                            kind=SlotKind.CLASS,
                            source_type=CLASS_SOURCE,
                            source_id=e.pk,
                            label=e.label,
                        )
                    )
            d += timedelta(days=1)
        BookingSlot.objects.bulk_create(past, batch_size=1000)
        self.notes.append(
            f"Timetable {self.term.code} v{self.publication.version}: {len(entries)} weekly classes, "
            f"{result['occurrences']} future occurrences on the ledger + {len(past)} past ones back-filled."
        )

    def _class_intervals(self, resource_id, d):
        if d < self.term.starts or d > self.term.ends:
            return []
        return [(aware(d, s), aware(d, e), "class") for s, e, _ in self.classes.get((resource_id, d.weekday()), [])]

    def _busy(self, r, d):
        key = (r.pk, d)
        if key not in self.busy:
            self.busy[key] = list(self._class_intervals(r.pk, d))
        return self.busy[key]

    # ── History ─────────────────────────────────────────────────────────────

    def _history(self):
        self._past_maintenance()
        plans = self._persona_history()
        plans += self._background_history()
        self._write_history(plans)
        self._denied_attempts()
        self._persona_standing()

    def _past_maintenance(self):
        windows, slots = [], []
        for code, days_ago, start, hours, title, kind, vendor, status in D.PAST_MAINTENANCE:
            r = self.res[code]
            d = self.today - timedelta(days=days_ago)
            s = aware(d, _hm(start))
            e = s + timedelta(hours=hours)
            if e > self.now or _overlaps(self._busy(r, d), s, e):
                continue
            w = MaintenanceWindow(
                institution=self.inst,
                resource=r,
                title=title,
                kind=kind,
                period=trange(s, e),
                status=status,
                vendor=vendor,
                notes="Routine work logged by the custodian." if status == "completed" else "Vendor rescheduled.",
                created_by=self.custodian_of.get(r.pk),
                completed_at=e if status == WindowStatus.COMPLETED else None,
            )
            windows.append((w, s - timedelta(days=self.rng.randint(2, 6)), e))
            if status == WindowStatus.COMPLETED:
                self._busy(r, d).append((s, e, "maintenance"))
        MaintenanceWindow.objects.bulk_create([w for w, _, _ in windows])
        for w, _, _ in windows:
            if w.status == WindowStatus.COMPLETED:
                slots.append(
                    BookingSlot(
                        resource=w.resource,
                        period=w.period,
                        kind=SlotKind.MAINTENANCE,
                        source_type=MAINT_SOURCE,
                        source_id=w.pk,
                        label=w.title,
                    )
                )
        BookingSlot.objects.bulk_create(slots)
        self._backdate(MaintenanceWindow, [(w.pk, c, u) for w, c, u in windows], ["created_at", "updated_at"])

        reports = []
        for code, days_ago, who, severity, summary, resolution in D.RESOLVED_BREAKDOWNS:
            created = self.now - timedelta(days=days_ago, hours=self.rng.randint(1, 8))
            resolved = created + timedelta(hours=self.rng.randint(5, 40))
            rep = BreakdownReport(
                institution=self.inst,
                resource=self.res[code],
                reported_by=self._person(who),
                summary=summary,
                severity=severity,
                status=ReportStatus.RESOLVED,
                resolved_at=resolved,
                resolution=resolution,
            )
            reports.append((rep, created, resolved))
        BreakdownReport.objects.bulk_create([r for r, _, _ in reports])
        self._backdate(BreakdownReport, [(r.pk, c, u) for r, c, u in reports], ["created_at", "updated_at"])

    # Who, where, when — persona history is fixed so the demo story is the same every time.
    PERSONA_HISTORY = {
        "student": [
            (3, "38-MR-1", "16:00", 60, "completed", "Capstone stand-up · Byte Busters"),
            (8, "38-LAB-2", "17:00", 120, "completed", "Kaggle study group"),
            (10, "SPT-BB-1", "18:00", 60, "completed", "Pickup game"),
            (15, "38-MR-1", "15:00", 60, "early", "Capstone review with mentor"),
            (17, "38-LAB-2", "17:30", 90, "completed", "Extra practice · INT354"),
            (22, "SPT-BB-1", "19:00", 60, "cancelled", "Practice · inter-hostel league"),
            (24, "EQ-VR-01", "11:00", 120, "completed", "XR coursework demo"),
            (29, "34-406", "14:00", 60, "completed", "Group study · CSE316"),
            (36, "38-LAB-2", "18:00", 120, "completed", "Hackathon prep · Byte Busters"),
        ],
        "student2": [
            (31, "SPT-BB-2", "18:00", 60, "completed", "Pickup game"),
            (24, "38-LAB-2", "17:00", 120, "no_show", "Kaggle study group"),
            (18, "34-LAB-3", "17:00", 60, "completed", "Packet Tracer practice"),
            (11, "SPT-BB-1", "18:00", 60, "no_show", "Practice · inter-hostel league"),
            (3, "38-MR-2", "14:00", 60, "no_show", "Project sync · Null Pointers"),
        ],
    }

    def _persona_history(self):
        plans = []
        for username, items in self.PERSONA_HISTORY.items():
            user = self.p[username]
            for days_ago, code, hhmm, minutes, status, title in items:
                r = self.res[code]
                for shift in range(8):  # slide earlier until the room is open and free
                    d = self.today - timedelta(days=days_ago + shift)
                    s = aware(d, _hm(hhmm))
                    e = s + timedelta(minutes=minutes)
                    opening = rules.opening_intervals(r, d, self.hours[r.pk])
                    if (
                        e <= self.now
                        and any(o <= s and e <= c for o, c in opening)
                        and not _overlaps(self._busy(r, d), s, e)
                    ):
                        break
                else:
                    continue
                self._charge(user, r, d, s, e)
                self._busy(r, d).append((s, e, "booking"))
                forced = "completed" if status == "early" else status
                plans.append(
                    Plan(r, user, s, e, title, attendees=min(r.capacity, 4), status=forced, early=status == "early")
                )
        return plans

    def _poisson(self, lam):
        if lam <= 0:
            return 0
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= limit:
                return k
            k += 1

    def _day_factor(self, type_code, d, progress):
        wd = d.weekday()
        if type_code == "sports":
            f = 1.25 if wd >= 5 else 1.0
        elif type_code == "vehicle":
            f = 0.5 if wd >= 5 else 1.0
        else:
            f = 0.5 if wd == 5 else 1.0
        if type_code in ("computer-lab", "electronics-lab", "classroom", "meeting-room"):
            f *= 0.8 + 0.45 * progress  # busier as mid-terms approach
        return f

    def _background_history(self):
        plans = []
        span = max(1, (self.today - self.hist_start).days)
        d = self.hist_start
        while d <= self.today:
            progress = (d - self.hist_start).days / span
            for r in self.resources:
                if not self.hours[r.pk].get(d.weekday()):
                    continue
                if r.status != "active" and (self.today - d).days < 10:
                    continue  # broke recently
                lam = D.TYPE_RATE[r.type.code] * D.HEAT.get(r.code, 1.0) * self._day_factor(r.type.code, d, progress)
                for _ in range(self._poisson(lam)):
                    plan = self._plan(r, d)
                    if plan:
                        plans.append(plan)
            d += timedelta(days=1)
        return plans

    def _start_options(self, r, d, minutes, profile):
        slot = self.policy[r.pk].slot_minutes
        out = []
        for o, c in self.hours[r.pk].get(d.weekday(), []):
            lo, hi = o.hour * 60 + o.minute, c.hour * 60 + c.minute
            for h, w in D.HOUR_PROFILES[profile].items():
                for m in (0, 30) if slot <= 30 else (0,):
                    st = h * 60 + m
                    if st >= lo and st + minutes <= hi:
                        out.append((st, w if m == 0 else w / 2))
        return out

    def _plan(self, r, d, *, until=None, after=None):
        """Pick a free, open time and an eligible person for one booking on resource r, day d."""
        rng = self.rng
        profile, durations = D.TYPE_PROFILE[r.type.code]
        policy = self.policy[r.pk]
        until = until or self.now
        for _ in range(6):
            minutes = min(rng.choice(durations), policy.max_duration_minutes)
            options = self._start_options(r, d, minutes, profile)
            if not options:
                continue
            st = rng.choices([o for o, _ in options], weights=[w for _, w in options])[0]
            s = aware(d, time(st // 60, st % 60))
            e = s + timedelta(minutes=minutes)
            if e > until or (after and s < after):
                continue
            if _overlaps(self._busy(r, d), s, e) or self._blacked_out(r, s, e):
                continue
            user = self._pick_user(r, d, s, e)
            if not user:
                continue
            self._busy(r, d).append((s, e, "booking"))
            title, group = self._title(r, user)
            return Plan(r, user, s, e, title, attendees=self._attendees(r), group_label=group)
        return None

    def _blacked_out(self, r, s, e):
        for b in self.blackouts:
            if not (b.period.lower < e and s < b.period.upper):
                continue
            if (
                b.scope == Scope.CAMPUS
                or (b.scope == Scope.TYPE and b.resource_type_id == r.type_id)
                or (b.scope == Scope.RESOURCE and b.resource_id == r.pk)
            ):
                return True
        return False

    def _pick_user(self, r, d, s, e):
        rng = self.rng
        roles = [(role, w) for role, w in D.BOOKERS[r.type.code] if r.type.role_may_book(role)]
        if not roles:
            return None
        for _ in range(8):
            role = rng.choices([x for x, _ in roles], weights=[w for _, w in roles])[0]
            pool = self.pools[role]
            if role == Role.STUDENT and r.department_id and rng.random() < 0.7:
                pool = self.students_by_dept.get(r.department_id) or pool
            if role == Role.FACULTY and r.department_id and rng.random() < 0.7:
                pool = self.faculty_by_dept.get(r.department_id) or pool
            if not pool:
                continue
            user = rng.choice(pool)
            if self._fits(user, r, d, s, e):
                self._charge(user, r, d, s, e)
                return user
        return None

    def _week(self, d):
        return d.isocalendar()[:2]

    def _fits(self, user, r, d, s, e):
        hours = (e - s).total_seconds() / 3600
        if _overlaps(self.user_busy[(user.pk, d)], s, e):
            return False
        wk = self._week(d)
        if user.role == Role.STUDENT:
            if self.day_count[(user.pk, d)] >= 2 or self.week_hours[(user.pk, wk)] + hours > 6:
                return False
            if r.type.code == "equipment" and self.week_type_hours[(user.pk, wk, "equipment")] + hours > 8:
                return False
        elif user.role == Role.FACULTY and self.week_hours[(user.pk, wk)] + hours > 20:
            return False
        return True

    def _charge(self, user, r, d, s, e):
        hours = (e - s).total_seconds() / 3600
        wk = self._week(d)
        self.user_busy[(user.pk, d)].append((s, e))
        self.week_hours[(user.pk, wk)] += hours
        self.week_type_hours[(user.pk, wk, r.type.code)] += hours
        self.day_count[(user.pk, d)] += 1

    def _course(self, r):
        dept = r.department.code if r.department else ""
        pool = {"CSE": "cse", "ECE": "ece", "LSB": "lsb"}.get(dept, "gen")
        if r.type.code in ("computer-lab", "electronics-lab"):
            pool = "ece_lab" if dept == "ECE" else "cse_lab"
        return self.rng.choice(D.COURSES[pool])[0]

    def _title(self, r, user):
        rng = self.rng
        if r.type.code == "equipment":
            pool = D.EQUIPMENT_TITLES.get(r.art) or ["Project work"]
        else:
            pool = D.TITLES.get(r.type.code) or ["Booking"]
        values = {
            "course": self._course(r),
            "club": rng.choice(D.CLUBS),
            "topic": rng.choice(D.TOPICS),
            "team": rng.choice(D.TEAMS),
            "section": user.section or rng.choice(D.SECTIONS["CSE"]),
        }
        template = rng.choice(pool)
        title = template.format(**values)
        group = ""
        # Only staff-side roles may book on behalf of a class or club (book_on_behalf).
        if user.role != Role.STUDENT and r.type.category in ("space", "lab") and rng.random() < 0.5:
            group = values["club"] if "{club}" in template else values["section"]
        return title[:140], group

    def _attendees(self, r):
        rng, cap = self.rng, r.capacity
        code = r.type.code
        if code == "equipment" or cap <= 1:
            return 1
        if code in ("seminar-hall", "lecture-theatre"):
            return max(1, int(cap * rng.uniform(0.35, 0.9)))
        if code in ("classroom", "computer-lab", "electronics-lab", "vehicle"):
            return max(1, int(cap * rng.uniform(0.15, 0.85)))
        return rng.randint(min(2, cap), cap)

    # History rows ───────────────────────────────────────────────────────────

    def _lead(self, r, user):
        code = r.type.code
        if code in ("seminar-hall", "vehicle"):
            hours = self.rng.uniform(52, 240)
        elif user.role == Role.STUDENT:
            hours = self.rng.uniform(1.5, 50)
        else:
            hours = self.rng.uniform(6, 120)
        if r.code == "18-AUD":
            hours = max(hours, 80)
        return timedelta(hours=hours)

    def _draw_status(self, plan, steps):
        if plan.status:
            return plan.status
        rng = self.rng
        x = rng.random()
        if steps:
            if x < 0.09:
                return BookingStatus.REJECTED
            if x < 0.13:
                return BookingStatus.EXPIRED
        if rng.random() < 0.08:
            return BookingStatus.CANCELLED
        p_no_show = 0.05
        if plan.resource.type.code in ("sports", "computer-lab", "meeting-room"):
            p_no_show = 0.08
        if plan.user.pk in self.flaky:
            p_no_show = 0.35
        if rng.random() < p_no_show and self.no_show_count[plan.user.pk] < 2 and plan.user.role == Role.STUDENT:
            return BookingStatus.NO_SHOW
        return BookingStatus.COMPLETED

    def _write_history(self, plans):
        rng = self.rng
        rows = []  # (Booking, plan, meta)
        for plan in plans:
            r, user, s, e = plan.resource, plan.user, plan.start, plan.end
            policy = self.policy[r.pk]
            minutes = minutes_between(s, e)
            wf = self._workflow_for(r, user.role, plan.attendees, minutes)
            steps = list(wf.steps.all()) if wf and not wf.auto_approve else []
            status = self._draw_status(plan, steps)
            if status == BookingStatus.NO_SHOW:
                self.no_show_count[user.pk] += 1
            created = max(s - self._lead(r, user), s - timedelta(days=policy.max_advance_days - 1))
            meta = {"wf": wf, "steps": steps, "created": created, "approvals": [], "original": (s, e)}
            b = Booking(
                institution=self.inst,
                resource=r,
                requester=user,
                booked_for=user,
                group_label=plan.group_label,
                title=plan.title,
                attendees=plan.attendees,
                period=trange(s, e),
                status=status,
                requires_checkin=policy.requires_checkin,
                checkin_grace_minutes=policy.checkin_grace_minutes,
            )
            last = self._approval_trail(b, meta, status)
            grace = policy.checkin_grace_minutes
            if status == BookingStatus.COMPLETED:
                ci = s + timedelta(minutes=rng.randint(-min(10, policy.checkin_opens_minutes), max(1, grace - 3)))
                early = plan.early if plan.early is not None else rng.random() < 0.25
                if early and minutes >= 60:
                    cut = s + timedelta(minutes=minutes * rng.uniform(0.45, 0.8))
                    cut = ceil_to(max(cut, ci + timedelta(minutes=10)), 5)
                    if cut < e:
                        out = cut - timedelta(minutes=rng.randint(0, 4))
                        meta["released"] = minutes_between(cut, e)
                        b.period = trange(s, cut)
                        meta["checkout"] = (out, False)
                if "checkout" not in meta:
                    meta["checkout"] = (e, rng.random() < 0.6)
                    meta["released"] = 0
                b.checked_in_at = ci
                b.checked_out_at = meta["checkout"][0]
                meta["checkin"] = ci
                last = b.checked_out_at
            elif status == BookingStatus.NO_SHOW:
                detected = s + timedelta(minutes=grace + 1, seconds=rng.randint(0, 50))
                b.status_reason = f"Not checked in within {grace} minutes"
                meta["no_show"] = (detected, minutes_between(detected, e))
                last = detected
            elif status == BookingStatus.CANCELLED:
                b.cancelled_at = meta["created"] + (s - meta["created"]) * rng.uniform(0.3, 0.95)
                b.status_reason = rng.choice(D.CANCEL_REASONS)
                last = b.cancelled_at
            elif status == BookingStatus.EXPIRED:
                b.status_reason = "No decision before the start time"
                last = s
            meta["updated"] = last or created
            rows.append((b, plan, meta))

        Booking.objects.bulk_create([b for b, _, _ in rows], batch_size=500)
        self._backdate(Booking, [(b.pk, m["created"], m["updated"]) for b, _, m in rows], ["created_at", "updated_at"])

        approvals_rows, approval_times, checkin_rows, no_show_rows, attempts = [], [], [], [], []
        issuances, attempt_times = [], []
        for b, _plan, meta in rows:
            for kw in meta["approvals"]:
                approvals_rows.append(Approval(booking=b, **kw))
                approval_times.append(meta["created"])
            s, e = meta["original"]
            attempts.append(
                BookingAttempt(resource=b.resource, user=b.booked_for, period=trange(s, e), outcome="booked")
            )
            attempt_times.append(meta["created"])
            if "checkin" in meta:
                out, auto = meta["checkout"]
                keeper = self.custodian_of.get(b.resource_id) or b.booked_for
                method = rng.choices(
                    [CheckInMethod.APP, CheckInMethod.RESOURCE_QR, CheckInMethod.PASS_QR], weights=[5, 4, 1]
                )[0]
                checkin_rows.append(
                    CheckIn(
                        booking=b,
                        checked_in_at=meta["checkin"],
                        method=method,
                        checked_in_by=keeper if method == CheckInMethod.PASS_QR else b.booked_for,
                        checked_out_at=out,
                        checked_out_by=None if auto else b.booked_for,
                        auto_checked_out=auto,
                        minutes_released=meta.get("released", 0),
                    )
                )
                if self.items.get(b.resource_id) and rng.random() < 0.3:
                    issuances.append((b, rng.choice(self.items[b.resource_id]), meta))
            if "no_show" in meta:
                detected, freed = meta["no_show"]
                no_show_rows.append(
                    NoShow(
                        institution=self.inst,
                        booking=b,
                        user=b.booked_for,
                        resource=b.resource,
                        detected_at=detected,
                        released_minutes=freed,
                    )
                )
        Approval.objects.bulk_create(approvals_rows, batch_size=1000)
        self._backdate(
            Approval, [(a.pk, t) for a, t in zip(approvals_rows, approval_times, strict=True)], ["created_at"]
        )
        CheckIn.objects.bulk_create(checkin_rows, batch_size=1000)
        NoShow.objects.bulk_create(no_show_rows, batch_size=1000)
        BookingAttempt.objects.bulk_create(attempts, batch_size=1000)
        self._backdate(
            BookingAttempt, [(a.pk, t) for a, t in zip(attempts, attempt_times, strict=True)], ["created_at"]
        )
        self._history_issuances(issuances)
        self.history_bookings = len(rows)

    def _approval_trail(self, b, meta, status):
        """Approval rows (kwargs) for a history booking; sets b.decided_at; returns the last event time."""
        rng = self.rng
        wf, steps, created = meta["wf"], meta["steps"], meta["created"]
        s = b.period.lower
        if not steps:
            meta["approvals"].append(
                {
                    "workflow": wf,
                    "step_order": 0,
                    "approver_role": "admin",
                    "decision": Decision.SKIPPED,
                    "comment": f"Auto-confirmed by rule: {wf.name}" if wf else "No approval required",
                    "decided_at": created,
                }
            )
            b.decided_at = None if status == BookingStatus.EXPIRED else created
            return created
        reject_at = rng.randrange(len(steps)) if status == BookingStatus.REJECTED else None
        t = created
        window = s - created
        last = created
        for i, step in enumerate(steps):
            row = {"workflow": wf, "step_order": step.order, "approver_role": step.approver_role}
            due = t + timedelta(hours=step.sla_hours)
            if status == BookingStatus.EXPIRED or (reject_at is not None and i > reject_at):
                row.update(decision=Decision.SKIPPED, due_at=due if i == 0 else None)
                meta["approvals"].append(row)
                continue
            t = t + window * rng.uniform(0.05, 0.4)
            decider = self._approver(step.approver_role, b.resource)
            if reject_at == i:
                comment = rng.choice(D.REJECTION_REASONS)
                row.update(decision=Decision.REJECTED, decided_by=decider, decided_at=t, comment=comment, due_at=due)
                b.status_reason = comment
            else:
                row.update(decision=Decision.APPROVED, decided_by=decider, decided_at=t, due_at=due)
            meta["approvals"].append(row)
            last = t
        b.decided_at = None if status == BookingStatus.EXPIRED else last
        return last

    def _history_issuances(self, issuances):
        rows, moves = [], []
        for b, item, meta in issuances:
            qty = min(item.max_per_booking, self.rng.randint(1, 2))
            keeper = self.custodian_of.get(b.resource_id)
            out = meta["checkout"][0]
            if item.kind == ItemKind.ACCESSORY:
                iss = Issuance(
                    booking=b,
                    item=item,
                    quantity=qty,
                    status=IssuanceStatus.RETURNED,
                    issued_at=meta["checkin"],
                    returned_at=out,
                    handled_by=keeper,
                )
            else:
                iss = Issuance(
                    booking=b,
                    item=item,
                    quantity=qty,
                    status=IssuanceStatus.CONSUMED,
                    issued_at=meta["checkin"],
                    handled_by=keeper,
                )
            rows.append((iss, meta["created"]))
        Issuance.objects.bulk_create([i for i, _ in rows], batch_size=1000)
        self._backdate(Issuance, [(i.pk, c) for i, c in rows], ["created_at"])
        times = []
        for iss, _ in rows:
            if iss.status == IssuanceStatus.RETURNED:
                moves.append(
                    StockMovement(
                        item=iss.item, delta=-iss.quantity, reason="issue", issuance=iss, actor=iss.handled_by
                    )
                )
                times.append(iss.issued_at)
                moves.append(
                    StockMovement(
                        item=iss.item, delta=iss.quantity, reason="return", issuance=iss, actor=iss.handled_by
                    )
                )
                times.append(iss.returned_at)
            else:
                moves.append(
                    StockMovement(
                        item=iss.item, delta=-iss.quantity, reason="consume", issuance=iss, actor=iss.handled_by
                    )
                )
                times.append(iss.issued_at)
        # A couple of restocks per consumable over the history window.
        for item in InventoryItem.objects.filter(institution=self.inst, kind=ItemKind.CONSUMABLE):
            for _ in range(self.rng.randint(1, 2)):
                when = self.now - timedelta(days=self.rng.uniform(3, (self.today - self.hist_start).days))
                keeper = self.custodian_of.get(item.resource_id) if item.resource_id else self.p["facility"]
                moves.append(
                    StockMovement(
                        item=item,
                        delta=max(2, item.quantity_total // 3),
                        reason="restock",
                        actor=keeper,
                        note="Monthly indent from central stores",
                    )
                )
                times.append(when)
        StockMovement.objects.bulk_create(moves, batch_size=1000)
        self._backdate(StockMovement, [(m.pk, t) for m, t in zip(moves, times, strict=True)], ["created_at"])

    def _denied_attempts(self):
        """Unmet demand: refused attempts concentrated on the hot resources, plus scattered rule refusals."""
        rng = self.rng
        rows, times = [], []
        students = self.pools[Role.STUDENT]
        d = self.hist_start
        while d <= self.today:
            for code, heat in D.HOT_DEMAND.items():
                r = self.res[code]
                busy = [x for x in self._busy(r, d) if x[1] <= self.now]
                if not busy:
                    continue
                for _ in range(self._poisson(heat * 1.6)):
                    s, e, kind = rng.choice(busy)
                    want = 60 if self.policy[r.pk].slot_minutes >= 60 else rng.choice([60, 90, 120])
                    start = s if kind != "booking" or rng.random() < 0.5 else floor_to(s + (e - s) / 2, 30)
                    outcome = {"class": AttemptOutcome.TIMETABLE, "maintenance": AttemptOutcome.MAINTENANCE}.get(
                        kind, AttemptOutcome.CONFLICT
                    )
                    rows.append(
                        BookingAttempt(
                            resource=r,
                            user=rng.choice(students),
                            period=trange(start, start + timedelta(minutes=want)),
                            outcome=outcome,
                        )
                    )
                    times.append(min(self.now, start - timedelta(hours=rng.uniform(0.2, 30))))
            for r in rng.sample(self.resources, k=3):
                if not self.hours[r.pk].get(d.weekday()):
                    continue
                outcome = rng.choice(
                    [AttemptOutcome.QUOTA, AttemptOutcome.CLOSED, AttemptOutcome.POLICY, AttemptOutcome.QUOTA]
                )
                start = aware(d, time(rng.choice([7, 12, 15, 20, 21])))
                if start >= self.now:
                    continue
                rows.append(
                    BookingAttempt(
                        resource=r,
                        user=rng.choice(students),
                        period=trange(start, start + timedelta(hours=2)),
                        outcome=outcome,
                    )
                )
                times.append(start - timedelta(hours=rng.uniform(1, 20)))
            d += timedelta(days=1)
        BookingAttempt.objects.bulk_create(rows, batch_size=1000)
        self._backdate(BookingAttempt, [(a.pk, t) for a, t in zip(rows, times, strict=True)], ["created_at"])
        self.denied_history = len(rows)

    def _persona_standing(self):
        """student2: three no-shows in 30 days -> the 7-day tier fired at the third one."""
        user = self.p["student2"]
        shows = list(NoShow.objects.filter(user=user).order_by("detected_at"))
        notes = []
        for n in shows:
            notes.append(
                (
                    Kind.AUTO_RELEASED,
                    f"Released · {n.resource.name}",
                    f"No check-in by {_local(n.booking.checkin_deadline):%H:%M}, so the slot went back to campus. "
                    "Repeated no-shows pause booking.",
                    n.booking.get_absolute_url(),
                    n.detected_at,
                )
            )
        if len(shows) >= 2:
            notes.append(
                (
                    Kind.RESTRICTED,
                    "Heads up: no-shows are adding up",
                    "2 missed check-ins in 30 days. One more and booking will be paused.",
                    "/me/standing/",
                    shows[1].detected_at + timedelta(seconds=5),
                )
            )
        if len(shows) >= 3:
            third = shows[2].detected_at
            Restriction.objects.create(
                institution=self.inst,
                user=user,
                starts_at=third,
                ends_at=third + timedelta(days=7),
                reason="3 no-shows in 30 days",
                tier_label="7-day pause",
            )
            notes.append(
                (
                    Kind.RESTRICTED,
                    "Booking paused for 7 days",
                    f"3 missed check-ins in 30 days (7-day pause). You can book again from "
                    f"{_local(third + timedelta(days=7)):%d %b}.",
                    "/me/standing/",
                    third + timedelta(seconds=5),
                )
            )
            self.cheat["student2"].append(
                f"Restricted until {_local(third + timedelta(days=7)):%a %d %b %H:%M} after 3 no-shows "
                f"({', '.join(f'{_local(n.detected_at):%d %b}' for n in shows)})."
            )
        self._notes(user, notes)

    # ── Live & upcoming (through the real services) ─────────────────────────

    def _book(self, user, r, s, e, title, *, now=None, attendees=1, group_label="", items=None, notify=False):
        try:
            return bookings.create_booking(
                requester=user,
                resource=r,
                start=s,
                end=e,
                title=title,
                attendees=attendees,
                group_label=group_label,
                items=items,
                notify=notify,
                now=now,
            )
        except DomainError:
            return None

    def _open_at(self, r, s, e):
        d = _local(s).date()
        return any(o <= s and e <= c for o, c in rules.opening_intervals(r, d, self.hours[r.pk]))

    def _next_open_day(self, r, after: date, hhmm="09:00", minutes=60):
        d = after
        for _ in range(10):
            s = aware(d, _hm(hhmm))
            if self._open_at(r, s, s + timedelta(minutes=minutes)):
                return d
            d += timedelta(days=1)
        return after

    def _future(self):
        self._live_now()
        self._student_demo()
        self._faculty_demo()
        self._approval_queues()
        self._random_future()
        self._decide_some_pending()

    def _live_window(self, r, *, min_ago, min_left):
        """A slot-aligned (start, end) with start <= now - min_ago and end >= now + min_left, open and free."""
        policy = self.policy[r.pk]
        slot = timedelta(minutes=policy.slot_minutes)
        base = floor_to(_local(self.now), policy.slot_minutes)
        for k in range(6):
            s = base - k * slot
            if self.now - s < timedelta(minutes=min_ago):
                continue
            e = s + slot
            while e < self.now + timedelta(minutes=min_left):
                e += slot
            if minutes_between(s, e) > policy.max_duration_minutes:
                return None
            if self._open_at(r, s, e) and not _overlaps(self._busy(r, self.today), s, e):
                return s, e
        return None

    def _live_now(self):
        """Bookings in progress right now, and one that is past its check-in grace (no-show sweep demo)."""
        rng = self.rng
        # 1) The no-show demo: approved, started ~20 min ago, never checked in.
        ns_user = User.objects.get(username=D.NO_SHOW_DEMO_STUDENT)
        rooms = ["38-MR-2", "34-406", "38-MR-1", "34-LAB-3", "34-304", "13-STU-1"]
        breaking = {code for code, _, severity, *_ in D.BREAKDOWNS if severity == "critical"}
        courts = [r.code for r in self.resources if r.type.code == "sports" and r.status == "active"]
        for code in [c for c in rooms + courts if c not in breaking]:
            r = self.res[code]
            window = self._live_window(r, min_ago=self.policy[r.pk].checkin_grace_minutes + 4, min_left=15)
            if not window:
                continue
            s, e = window
            # Requested yesterday (and, where a workflow applies, approved yesterday) — so it is a
            # perfectly ordinary confirmed booking that nobody turned up for.
            asked = s - timedelta(hours=26)
            b = self._book(
                ns_user, r, s, e, self._title(r, ns_user)[0], now=asked, attendees=min(3, r.capacity), notify=True
            )
            while b and b.status == BookingStatus.PENDING:
                step = b.approvals.filter(decision=Decision.PENDING).first()
                b = approvals.decide(
                    step,
                    self._approver(step.approver_role, r),
                    approve=True,
                    comment="OK",
                    now=asked + timedelta(hours=3),
                )
            if b:
                self._busy(r, self.today).append((s, e, "booking"))
                self.cheat["live"].append(
                    f"No-show demo: {b.reference} · {ns_user.display_name} ({ns_user.username}) · {r.name} "
                    f"{_local(s):%H:%M}–{_local(e):%H:%M}, not checked in (grace {b.checkin_grace_minutes} min "
                    "passed). Run the no-show sweep to see it auto-released."
                )
                break
        else:
            self.notes.append("Nothing is open right now, so the live no-show demo booking was skipped.")

        # 2) A few sessions in progress, checked in a few minutes after they started.
        candidates = ["38-LAB-1", "34-MR-1", "38-MR-1", "34-LAB-2", "SPT-BB-2", "SPT-GYM-1", "SPT-BD-2", "13-STU-1"]
        made = 0
        for code in candidates:
            if made >= 4:
                break
            r = self.res[code]
            window = self._live_window(r, min_ago=3, min_left=40)
            if not window:
                continue
            s, e = window
            roles = (
                [Role.STUDENT, Role.STAFF] if r.type.code in ("sports", "studio", "meeting-room") else [Role.FACULTY]
            )
            roles = [x for x in roles if not self._needs_approval(r, x, minutes_between(s, e))]
            if not roles:
                continue
            user = rng.choice(self.pools[roles[0]])
            title = self._title(r, user)[0]
            b = self._book(user, r, s, e, title, now=s - timedelta(hours=2), attendees=self._attendees(r))
            if not b:
                continue
            grace = b.checkin_grace_minutes
            ci = s + timedelta(minutes=rng.randint(0, max(0, min(grace - 1, minutes_between(s, self.now)))))
            try:
                checkins.check_in(b, user, method=CheckInMethod.RESOURCE_QR, now=ci)
            except DomainError:
                continue
            made += 1
            self._busy(r, self.today).append((s, e, "booking"))
            line = f"In use now: {r.name} · {b.reference} · {user.display_name} {_local(s):%H:%M}–{_local(e):%H:%M}"
            self.cheat["custodian" if self.custodian_of.get(r.pk) == self.p["custodian"] else "live"].append(line)

    def _student_demo(self):
        user = self.p["student"]
        now_local = _local(self.now)
        # Today's booking, starting in 60–90 minutes, for the QR check-in demo.
        made = None
        for code in ["38-MR-1", "38-MR-2", "34-406", "34-MR-1"]:
            r = self.res[code]
            s = ceil_to(now_local + timedelta(minutes=60), 30)
            e = s + timedelta(minutes=60)
            if not self._open_at(r, s, e):
                d = self._next_open_day(r, self.today + timedelta(days=1))
                s = aware(d, time(9))
                e = s + timedelta(minutes=60)
            made = self._book(user, r, s, e, "Capstone stand-up · Byte Busters", attendees=5, notify=True)
            if made:
                break
        if made and _local(made.start).date() != self.today:
            self.notes.append(
                f"Late in the day: the student's check-in demo booking is on {_local(made.start):%a %d %b %H:%M}."
            )
        if made:
            opens = made.start - timedelta(minutes=self.policy[made.resource_id].checkin_opens_minutes)
            self.cheat["student"].append(
                f"{made.reference} · {made.resource.name} · {_local(made.start):%a %d %b %H:%M}–{_local(made.end):%H:%M} "
                f"(approved; check-in opens {_local(opens):%H:%M}, door QR or pass)"
            )

        # Tomorrow: the GPU lab after classes, falling back to the basketball court.
        tomorrow = self.today + timedelta(days=1)
        for code, hhmm, minutes, title in [
            ("38-LAB-2", "17:00", 90, "Kaggle study group"),
            ("38-LAB-2", "18:30", 90, "Kaggle study group"),
            ("SPT-BB-1", "18:00", 60, "Pickup game"),
        ]:
            r = self.res[code]
            d = self._next_open_day(r, tomorrow, hhmm, minutes)
            s = aware(d, _hm(hhmm))
            b = self._book(user, r, s, s + timedelta(minutes=minutes), title, attendees=4, notify=True)
            if b:
                self.cheat["student"].append(
                    f"{b.reference} · {r.name} · {_local(b.start):%a %d %b %H:%M}–{_local(b.end):%H:%M} (approved)"
                )
                break

        # A pending equipment request in the custodian's queue.
        r = self.res["EQ-GPU-01"]
        d = self.today + timedelta(days=2)
        for _ in range(7):
            if d.weekday() < 5:
                s = aware(d, time(10))
                b = self._book(user, r, s, s + timedelta(hours=2), "Model training run · Byte Busters", notify=True)
                if b:
                    self.cheat["student"].append(
                        f"{b.reference} · {r.name} · {_local(b.start):%a %d %b %H:%M}–{_local(b.end):%H:%M} "
                        "(pending — custodian approves)"
                    )
                    break
            d += timedelta(days=1)

        # One they cancelled, so "My bookings" shows the full lifecycle.
        r = self.res["SPT-BB-1"]
        d = self._next_open_day(r, self.today + timedelta(days=3), "19:00")
        b = self._book(user, r, aware(d, time(19)), aware(d, time(20)), "Practice · inter-hostel league")
        if b:
            bookings.cancel_booking(b, user, reason="Team couldn't make it")

        # student2 tries anyway and is refused (restriction) — shows up as a denied attempt.
        self._book(
            self.p["student2"], self.res["38-LAB-2"], aware(tomorrow, time(19)), aware(tomorrow, time(20)), "Practice"
        )

    def _faculty_demo(self):
        fac = self.p["faculty"]
        lab = self.res["34-LAB-2"]
        # Weekly extra lab on Wednesdays 17:00–19:00 for four weeks, with one date already taken.
        start = self.today + timedelta(days=(2 - self.today.weekday()) % 7 or 7)
        until = start + timedelta(weeks=3)
        clash_day = start + timedelta(weeks=2)
        blocker = self.rng.choice(self.students_by_dept[self.depts["CSE"].pk])
        clash = self._book(
            blocker, lab, aware(clash_day, time(17, 30)), aware(clash_day, time(18, 30)), "Lab re-test · CSE326"
        )
        try:
            series, created, skipped = bookings.create_series(
                requester=fac,
                resource=lab,
                title="Extra practice · CSE326 Internet Programming",
                frequency="weekly",
                interval=1,
                weekdays=[start.weekday()],
                start_date=start,
                until_date=until,
                start_time=time(17),
                end_time=time(19),
                attendees=55,
                group_label="K23KF",
            )
            self.cheat["faculty"].append(
                f"Series '{series.title}' · {lab.name} · {start:%a}s 17:00–19:00 from {start:%d %b}: "
                f"{len(created)} booked, {len(skipped)} skipped"
                + (f" ({clash_day:%d %b} clashes with {clash.reference})" if clash and skipped else "")
            )
        except DomainError as exc:
            self.notes.append(f"Faculty series not created: {exc.message}")

        # A seminar-hall request waiting for the custodian, and a lecture theatre for a combined class.
        hall = self.res["34-SH-1"]
        d = self._next_open_day(hall, self.today + timedelta(days=6), "14:00", 120)
        b = self._book(fac, hall, aware(d, time(14)), aware(d, time(16)), "Guest lecture · Generative AI in practice",
                       attendees=120, group_label="K23KF", notify=True)  # fmt: skip
        if b:
            self.cheat["faculty"].append(f"{b.reference} · {hall.name} {d:%a %d %b} 14:00–16:00 (pending custodian)")
        lt = self.res["34-LT-1"]
        for offset in range(2, 9):
            d = self.today + timedelta(days=offset)
            if d.weekday() >= 5:
                continue
            b = self._book(fac, lt, aware(d, time(17)), aware(d, time(18, 30)), "Combined class · CSE310 revision",
                           attendees=180, group_label="K23KF+K23KG", notify=True)  # fmt: skip
            if b:
                self.cheat["faculty"].append(f"{b.reference} · {lt.name} {d:%a %d %b} 17:00–18:30 (confirmed)")
                break

    def _approval_queues(self):
        """Requests sitting at each approver persona."""
        cust = self.p["custodian"]
        staff = {u.username: u for u in self.pools[Role.STAFF]}
        rahul = staff.get("rahul.gupta") or self.pools[Role.STAFF][0]
        shalini = staff.get("shalini.rawat") or self.pools[Role.STAFF][0]
        coach = staff.get("manjit.sandhu") or self.pools[Role.STAFF][0]
        hall = self.res["34-SH-1"]

        # 1) Staff seminar request: custodian approves step 1 -> waits for the HoD.
        d = self._next_open_day(hall, self.today + timedelta(days=8), "10:00", 120)
        b = self._book(rahul, hall, aware(d, time(10)), aware(d, time(12)), "Pre-placement talk · product companies",
                       attendees=140, group_label="K22FS", notify=True)  # fmt: skip
        if b:
            step = b.approvals.get(decision=Decision.PENDING)
            approvals.decide(step, cust, approve=True, comment="Hall free; AV crew booked.")
            self.cheat["hod"].append(f"{b.reference} · {hall.name} {d:%a %d %b} 10:00–12:00 · {rahul.display_name}")
        # 2) Another one still at the custodian.
        d = self._next_open_day(hall, self.today + timedelta(days=10), "15:00", 120)
        b = self._book(shalini, hall, aware(d, time(15)), aware(d, time(17)), "Workshop · Design thinking for engineers",
                       attendees=90, notify=True)  # fmt: skip
        if b:
            self.cheat["custodian"].append(
                f"Approve: {b.reference} · {hall.name} {d:%a %d %b} 15:00–17:00 (step 1 of 2)"
            )

        # 3) Auditorium: custodian (estate) approves -> facility manager signs off.
        aud = self.res["18-AUD"]
        d = self._next_open_day(aud, self.today + timedelta(days=5), "14:00", 240)
        b = self._book(shalini, aud, aware(d, time(14)), aware(d, time(18)), "Freshers' welcome rehearsal",
                       attendees=600, notify=True)  # fmt: skip
        if b:
            step = b.approvals.get(decision=Decision.PENDING)
            approvals.decide(step, self._approver("custodian", aud), approve=True, comment="Stage crew confirmed.")
            self.cheat["facility"].append(f"{b.reference} · {aud.name} {d:%a %d %b} 14:00–18:00 (step 2 of 2)")

        # 4) Vehicles wait for the facility manager.
        bus = self.res["VEH-BUS-3"]
        d = self.today + timedelta(days=7)
        b = self._book(self.p["faculty"], bus, aware(d, time(7)), aware(d, time(17)),
                       "Industrial visit · K23KF · Quark City, Mohali", attendees=48, group_label="K23KF", notify=True)  # fmt: skip
        if b:
            self.cheat["facility"].append(f"{b.reference} · {bus.name} {d:%a %d %b} 07:00–17:00 (vehicle requisition)")
        van = self.res["VEH-VAN-1"]
        d = self.today + timedelta(days=4)
        b = self._book(coach, van, aware(d, time(6)), aware(d, time(18)), "Team travel · inter-university meet, Patiala",
                       attendees=12, group_label="Basketball Squad", notify=True)  # fmt: skip
        if b:
            self.cheat["facility"].append(f"{b.reference} · {van.name} {d:%a %d %b} 06:00–18:00 (vehicle requisition)")

        # 5) Student equipment requests on the custodian's kit.
        vr = self.res["EQ-VR-01"]
        for offset in range(1, 6):
            d = self.today + timedelta(days=offset)
            if d.weekday() >= 5:
                continue
            u = self.rng.choice(self.students_by_dept[self.depts["CSE"].pk])
            b = self._book(u, vr, aware(d, time(14)), aware(d, time(16)), "VR usability study", notify=True)
            if b:
                self.cheat["custodian"].append(
                    f"Approve: {b.reference} · {vr.name} {d:%a %d %b} 14:00–16:00 · {u.display_name}"
                )
                break

    def _random_future(self):
        rng = self.rng
        horizon = 14
        made = tried = 0
        for offset in range(horizon + 1):
            d = self.today + timedelta(days=offset)
            decay = max(0.15, 1 - offset / 12) * 0.75
            for r in self.resources:
                if r.status != "active" or not self.hours[r.pk].get(d.weekday()):
                    continue
                lam = D.TYPE_RATE[r.type.code] * D.HEAT.get(r.code, 1.0) * self._day_factor(r.type.code, d, 1.0) * decay
                for _ in range(self._poisson(lam)):
                    plan = self._plan(
                        r, d, until=aware(d + timedelta(days=1), time.min), after=self.now + timedelta(minutes=30)
                    )
                    if not plan:
                        continue
                    tried += 1
                    wf = self._workflow_for(r, plan.user.role, plan.attendees, minutes_between(plan.start, plan.end))
                    pending = bool(wf and not wf.auto_approve)
                    items = None
                    if self.items.get(r.pk) and rng.random() < 0.25:
                        item = rng.choice(self.items[r.pk])
                        items = {item.pk: 1}
                    b = self._book(plan.user, r, plan.start, plan.end, plan.title, attendees=plan.attendees,
                                   group_label=plan.group_label, items=items, notify=pending)  # fmt: skip
                    if b:
                        made += 1
        self.notes.append(f"Upcoming fill: {made} of {tried} generated requests accepted by create_booking.")

    def _decide_some_pending(self):
        rng = self.rng
        keep_for_custodian = 6
        pending = list(
            Booking.objects.filter(institution=self.inst, status=BookingStatus.PENDING, period__startswith__gt=self.now)
            .select_related("resource")
            .order_by("period")
        )
        mentioned = " ".join(line for lines in self.cheat.values() for line in lines)
        for b in pending:
            step = b.approvals.filter(decision=Decision.PENDING).first()
            if not step:
                continue
            persona_queue = (
                step.approver_role == "custodian" and self.custodian_of.get(b.resource_id) == self.p["custodian"]
            )
            if persona_queue and keep_for_custodian > 0:
                keep_for_custodian -= 1
                continue
            if b.reference in mentioned:
                continue
            x = rng.random()
            if x < 0.4:
                continue
            approve = x > 0.48
            while step:
                decider = self._approver(step.approver_role, b.resource)
                try:
                    b = approvals.decide(step, decider, approve=approve,
                                         comment="" if approve else rng.choice(D.REJECTION_REASONS))  # fmt: skip
                except DomainError:
                    break
                if not approve or b.status != BookingStatus.PENDING:
                    break
                step = b.approvals.filter(decision=Decision.PENDING).first()

    # ── Maintenance (future) ────────────────────────────────────────────────

    def _maintenance_future(self):
        for code, ahead, start, hours, title, kind, vendor, displace in D.FUTURE_MAINTENANCE:
            r = self.res[code]
            if ahead == "next-sat":
                d = self.today + timedelta(days=(5 - self.today.weekday()) % 7 or 7)
            else:
                d = self.today + timedelta(days=ahead)
            s = aware(d, _hm(start))
            e = s + timedelta(hours=hours)
            victim = None
            if displace:
                # Someone already holds part of the window: scheduling the work moves them off, with a notice.
                for u in self.rng.sample(self.students_by_dept[self.depts["CSE"].pk], 8):
                    for hours_in in (1, 2, 0):
                        vs = s + timedelta(hours=hours_in)
                        victim = self._book(u, r, vs, vs + timedelta(minutes=90), "Capstone project work")
                        if victim:
                            break
                    if victim:
                        break
            try:
                actor = self.custodian_of.get(r.pk) or self.p["facility"]
                w = maintenance.schedule(
                    r, s, e, title=title, kind=kind, actor=actor, vendor=vendor, enforce_permissions=False
                )
            except DomainError as exc:
                self.notes.append(f"Maintenance '{title}' on {r.code} skipped: {exc.message}")
                continue
            if r.code.startswith(("34-", "38-")) or r.code in ("EQ-GPU-01", "EQ-VR-01"):
                line = f"Maintenance: {title} · {r.name} {d:%a %d %b} {start}–{_local(e):%H:%M}"
                if w.displaced_bookings:
                    who = f" incl. {victim.reference}" if victim else ""
                    line += f" — displaced {w.displaced_bookings} booking(s){who}; owners were told, with alternatives"
                self.cheat["custodian"].append(line)

        for code, who, severity, summary, details, ack in D.BREAKDOWNS:
            r = Resource.objects.get(pk=self.res[code].pk)
            rep = maintenance.report_breakdown(
                r, self._person(who), summary=summary, details=details, severity=severity
            )
            if ack:
                rep.status = ReportStatus.ACKNOWLEDGED
                rep.save(update_fields=["status", "updated_at"])
            if severity == "critical":
                self.cheat["facility"].append(f"Critical breakdown: {r.name} is out of service — '{summary}'")

    # ── Notifications ───────────────────────────────────────────────────────

    def _notes(self, user, rows, read_before=None):
        """rows: (kind, title, body, url, created_at)."""
        from apps.notifications.services import TONES

        objs = [
            Notification(
                user=user,
                kind=k,
                title=t[:160],
                body=b[:500],
                url=u,
                tone=TONES.get(k, "info"),
                read_at=(c + timedelta(hours=2)) if read_before and c < read_before else None,
            )
            for k, t, b, u, c in rows
        ]
        Notification.objects.bulk_create(objs)
        self._backdate(Notification, [(n.pk, row[4]) for n, row in zip(objs, rows, strict=True)], ["created_at"])

    def _notifications(self):
        now = self.now
        day = timedelta(days=1)
        # Older items people have already seen, so inboxes are not all-unread.
        student = self.p["student"]
        past = Booking.objects.filter(booked_for=student, status=BookingStatus.COMPLETED).order_by("-period")[:3]
        rows = [
            (Kind.BOOKING_CONFIRMED, f"Confirmed · {b.resource.name}",
             f"{_local(b.start):%a %d %b}, {_local(b.start):%H:%M}–{_local(b.end):%H:%M}. Your QR pass is ready.",
             b.get_absolute_url(), b.start - timedelta(hours=20))
            for b in past
        ]  # fmt: skip
        rows.append((Kind.REMINDER, "Check in within 15 minutes of the start",
                     "Bookings not checked in are released automatically so others can use the space.",
                     "/me/standing/", now - 30 * day))  # fmt: skip
        self._notes(student, rows, read_before=now - day)

        low = [i for i in InventoryItem.objects.filter(institution=self.inst) if i.is_low]
        for username in ("custodian", "facility", "admin"):
            user = self.p[username]
            mine = [
                i
                for i in low
                if username != "custodian" or (i.resource_id and self.custodian_of.get(i.resource_id) == user)
            ]
            if username == "custodian" and not mine:
                mine = [i for i in low if i.resource_type_id and i.resource_type.code == "computer-lab"]
            rows = [
                (Kind.STOCK_LOW, f"Low stock · {i.name}", f"{i.quantity_available} {i.unit} left (reorder at {i.reorder_level}).",
                 "/manage/inventory/", now - timedelta(hours=self.rng.randint(3, 60)))
                for i in mine[:4]
            ]  # fmt: skip
            self._notes(user, rows, read_before=now - 2 * day)
        for rep in BreakdownReport.objects.filter(institution=self.inst, severity="critical").exclude(
            status=ReportStatus.RESOLVED
        ):
            for username in ("facility", "admin"):
                self._notes(
                    self.p[username],
                    [(Kind.BREAKDOWN, f"Breakdown reported · {rep.resource.name}",
                      f"{rep.get_severity_display()}: {rep.summary}", "/manage/maintenance/", rep.created_at)],
                )  # fmt: skip

    # ── Utilities ───────────────────────────────────────────────────────────

    def _backdate(self, model, rows, cols):
        """Set auto_now/auto_now_add timestamps that bulk_create can't (one UPDATE ... FROM VALUES per 1000)."""
        if not rows:
            return
        table = connection.ops.quote_name(model._meta.db_table)
        sets = ", ".join(f"{c} = v.{c}" for c in cols)
        names = ", ".join(cols)
        row_sql = "(%s::bigint" + ", %s::timestamptz" * len(cols) + ")"
        with connection.cursor() as cur:
            for chunk in batched(rows, 1000):
                params = [x for row in chunk for x in row]
                values = ", ".join([row_sql] * len(chunk))
                # Identifiers come from model metadata; every value is a bound parameter.
                sql = f"UPDATE {table} AS t SET {sets} FROM (VALUES {values}) AS v(id, {names}) WHERE t.id = v.id"  # noqa: S608
                cur.execute(sql, params)

    ASCII_FALLBACK = {"·": "-", "–": "-", "—": "-", "→": "->", "…": "...", "•": "*", "₹": "Rs ", "×": "x"}

    def _write(self, text):
        """Windows consoles often run cp1252; degrade punctuation instead of crashing on it."""
        encoding = getattr(self.stdout._out, "encoding", None) or "utf-8"
        try:
            text.encode(encoding)
        except UnicodeEncodeError:
            for k, v in self.ASCII_FALLBACK.items():
                text = text.replace(k, v)
            text = text.encode(encoding, "replace").decode(encoding)
        self.stdout.write(text)

    def _summary(self, elapsed):
        inst = self.inst
        counts = [
            ("Departments", Department.objects.filter(institution=inst)),
            ("Users", User.objects.filter(institution=inst)),
            ("  students", User.objects.filter(institution=inst, role=Role.STUDENT)),
            ("  faculty & staff", User.objects.filter(institution=inst).exclude(role=Role.STUDENT)),
            ("Buildings", Building.objects.filter(institution=inst)),
            ("Resource types", ResourceType.objects.filter(institution=inst)),
            ("Resources", Resource.objects.filter(institution=inst)),
            ("  out of service", Resource.objects.filter(institution=inst, status="out_of_service")),
            ("Booking policies", BookingPolicy.objects.filter(institution=inst)),
            ("Opening-hour rules", AvailabilityRule.objects.filter(institution=inst)),
            ("Blackouts", Blackout.objects.filter(institution=inst)),
            ("Quotas", Quota.objects.filter(institution=inst)),
            ("Approval workflows", ApprovalWorkflow.objects.filter(institution=inst)),
            ("Timetable entries", TimetableEntry.objects.filter(publication__institution=inst)),
            ("Ledger slots · class", BookingSlot.objects.filter(resource__institution=inst, kind=SlotKind.CLASS)),
            ("Ledger slots · booking", BookingSlot.objects.filter(resource__institution=inst, kind=SlotKind.BOOKING)),
            (
                "Ledger slots · maint.",
                BookingSlot.objects.filter(resource__institution=inst, kind=SlotKind.MAINTENANCE),
            ),
            ("Bookings", Booking.objects.filter(institution=inst)),
        ]
        for status, label in BookingStatus.choices:
            counts.append((f"  {label.lower()}", Booking.objects.filter(institution=inst, status=status)))
        counts += [
            ("Booking series", BookingSeries.objects.filter(institution=inst)),
            ("Booking attempts", BookingAttempt.objects.filter(resource__institution=inst)),
            ("  denied (unmet demand)", BookingAttempt.objects.filter(
                resource__institution=inst, outcome__in=analytics.DENIED_OUTCOMES)),
            ("Approvals", Approval.objects.filter(booking__institution=inst)),
            ("Check-ins", CheckIn.objects.filter(booking__institution=inst)),
            ("No-shows", NoShow.objects.filter(institution=inst)),
            ("Restrictions (active)", Restriction.objects.filter(institution=inst, ends_at__gt=self.now, lifted_at__isnull=True)),
            ("Maintenance windows", MaintenanceWindow.objects.filter(institution=inst)),
            ("Breakdown reports", BreakdownReport.objects.filter(institution=inst)),
            ("Inventory items", InventoryItem.objects.filter(institution=inst)),
            ("  at/below reorder level", [i for i in InventoryItem.objects.filter(institution=inst) if i.is_low]),
            ("Issuances", Issuance.objects.filter(booking__institution=inst)),
            ("Stock movements", StockMovement.objects.filter(item__institution=inst)),
            ("Notifications", Notification.objects.filter(user__institution=inst)),
            ("Utilisation snapshots", UtilisationSnapshot.objects.filter(resource__institution=inst)),
        ]  # fmt: skip
        w = self._write
        w("")
        w(self.style.MIGRATE_HEADING("Seeded data"))
        for label, qs in counts:
            n = len(qs) if isinstance(qs, list) else qs.count()
            w(f"  {label:<28} {n:>7}")
        w(f"  {'elapsed':<28} {elapsed:>6.1f}s")

        w("")
        w(self.style.MIGRATE_HEADING("Personas (one-click sign-in with DEMO_MODE=1)"))
        pw = "DEMO_PASSWORD" if self.password_hash else "unusable password — use one-click persona sign-in"
        w(f"  Password: {pw}. Background students: {STUDENT_TEMPLATE} (s001…s{D.BACKGROUND_STUDENTS:03d}).")
        guide = [
            ("student", "Aarav Sharma · B.Tech CSE K23KF", "Home → today's booking → QR pass / check in; Find: 'lab for 30 tomorrow after 5pm', 'block 34'"),
            ("student2", "Kabir Malhotra", "Me → Standing: 3 no-shows, booking paused"),
            ("faculty", "Dr. Neha Verma · CSE", "Recurring series with a skipped date; seminar-hall request pending"),
            ("custodian", "Rajinder Singh · Lab Superintendent, Blocks 34 & 38", "Manage → Approvals, Board, Maintenance, Inventory"),
            ("hod", "Prof. Vikram Sethi · HoD CSE", "Approvals (step 2), Insights for CSE, quota consumption"),
            ("facility", "Harpreet Dhillon · Facility Manager", "Insights (utilisation, demand vs supply, idle kit), vehicle & auditorium approvals"),
            ("admin", "Anjali Mehta · System Administrator", "Workflows, roles, audit log"),
        ]  # fmt: skip
        for username, who, what in guide:
            w(self.style.SUCCESS(f"  {username:<10}") + f" {who}")
            w(f"             {what}")
            for line in self.cheat.get(username, []):
                w(f"             • {line}")
        for line in self.cheat.get("live", []):
            w(self.style.WARNING(f"  live       • {line}"))
        for line in self.notes:
            w(self.style.WARNING(f"  note: {line}"))
