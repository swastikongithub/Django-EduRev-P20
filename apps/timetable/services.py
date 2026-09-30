"""
M4 service interface.

    parse_rows(text | rows, institution_id) -> (entries, errors)   CSV export or P13 JSON payload
    stage(term, entries, source, actor)     -> TimetablePublication (draft)
    publish(publication, actor)             -> summary dict
    occupied(resource, start, end)          -> bool (is a class running then?)

Publishing writes every remaining occurrence of every class this term into the
BookingSlot ledger (kind=class). Republishing supersedes the previous version in
the same transaction: its class slots are removed and the new ones written, so
the change of timetable and the change of availability are one atomic event.
Ordinary bookings that collide with the new timetable are cancelled and their
owners told, with alternatives — the timetable is a hard constraint.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.permissions import has_cap
from apps.bookings.models import HOLDING_STATUSES, Booking, BookingSlot, SlotKind
from apps.catalogue.models import Resource
from apps.core.errors import BookingRejected, NotPermitted
from apps.core.timeutil import aware, trange

from .models import AcademicTerm, PublicationStatus, TimetableEntry, TimetablePublication

SOURCE = "timetable_entry"
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
COLUMNS = ["room_code", "day", "start", "end", "course_code", "course_title", "section", "faculty", "kind"]


def _day(v: str) -> int:
    v = str(v).strip().lower()
    if v.isdigit() and 0 <= int(v) <= 6:
        return int(v)
    if v[:3] in DAYS:
        return DAYS[v[:3]]
    raise ValueError(f"unknown day '{v}'")


def _time(v: str) -> time:
    v = str(v).strip()
    for fmt in ("%H:%M", "%H.%M", "%I:%M %p", "%I:%M%p", "%H:%M:%S"):
        try:
            return datetime.strptime(v.upper(), fmt).time()
        except ValueError:
            continue
    raise ValueError(f"unreadable time '{v}'")


def parse_rows(source, institution_id):
    """Accepts CSV text or a list of dicts. Returns (unsaved TimetableEntry list, [error strings])."""
    if isinstance(source, str):
        reader = csv.DictReader(io.StringIO(source.strip()))
        rows = list(reader)
        missing = {"room_code", "day", "start", "end", "course_code"} - set(reader.fieldnames or [])
        if missing:
            return [], [f"Missing column(s): {', '.join(sorted(missing))}. Expected: {', '.join(COLUMNS)}"]
    else:
        rows = list(source)
    rooms = {r.code: r for r in Resource.objects.filter(institution_id=institution_id)}
    entries, errors = [], []
    for n, row in enumerate(rows, start=2):
        try:
            code = str(row.get("room_code", "")).strip()
            resource = rooms.get(code)
            if not resource:
                raise ValueError(f"unknown room '{code}'")
            start, end = _time(row["start"]), _time(row["end"])
            if start >= end:
                raise ValueError("start must be before end")
            entries.append(
                TimetableEntry(
                    resource=resource,
                    weekday=_day(row["day"]),
                    start_time=start,
                    end_time=end,
                    course_code=str(row["course_code"]).strip()[:16],
                    course_title=str(row.get("course_title") or "").strip()[:160],
                    section=str(row.get("section") or "").strip()[:24],
                    faculty=str(row.get("faculty") or "").strip()[:120],
                    kind=str(row.get("kind") or "Lecture").strip()[:16] or "Lecture",
                )
            )
        except (KeyError, ValueError) as exc:
            errors.append(f"Row {n}: {exc}")
    errors.extend(_internal_clashes(entries))
    return entries, errors


def _internal_clashes(entries) -> list[str]:
    """Two classes in one room at once is a timetable error, not something to 'resolve' silently."""
    by_slot = defaultdict(list)
    for e in entries:
        by_slot[(e.resource.code, e.weekday)].append(e)
    errors = []
    for (code, wd), items in by_slot.items():
        items.sort(key=lambda e: e.start_time)
        for a, b in zip(items, items[1:], strict=False):
            if b.start_time < a.end_time:
                day = list(DAYS)[wd].title()
                errors.append(
                    f"{code} {day}: {a.course_code} {a.section} ({a.start_time:%H:%M}–{a.end_time:%H:%M}) overlaps "
                    f"{b.course_code} {b.section} ({b.start_time:%H:%M}–{b.end_time:%H:%M})"
                )
    return errors


def stage(term: AcademicTerm, entries, *, source="csv", actor=None, notes="") -> TimetablePublication:
    with transaction.atomic():
        version = (term.publications.order_by("-version").values_list("version", flat=True).first() or 0) + 1
        pub = TimetablePublication.objects.create(
            institution_id=term.institution_id,
            term=term,
            version=version,
            source=source,
            entry_count=len(entries),
            notes=notes,
            published_by=actor,
        )
        for e in entries:
            e.publication = pub
        TimetableEntry.objects.bulk_create(entries)
    return pub


def _occurrences(entry: TimetableEntry, first_day, last_day):
    d = first_day + timedelta(days=(entry.weekday - first_day.weekday()) % 7)
    while d <= last_day:
        yield aware(d, entry.start_time), aware(d, entry.end_time)
        d += timedelta(days=7)


def publish(pub: TimetablePublication, actor=None, *, now=None, request=None, enforce_permissions=True) -> dict:
    from apps.bookings.services import displace_bookings, release_blocks

    if enforce_permissions and not has_cap(actor, "manage_timetable"):
        raise NotPermitted("Only facility managers and administrators can publish timetables.")
    now = now or timezone.now()
    term = pub.term
    first_day = max(term.starts, timezone.localtime(now).date())
    last_day = term.ends

    with transaction.atomic():
        AcademicTerm.objects.select_for_update().get(pk=term.pk)  # one publication per term at a time
        pub = TimetablePublication.objects.select_for_update().get(pk=pub.pk)
        if pub.status != PublicationStatus.DRAFT:
            raise BookingRejected("Only a draft timetable can be published.", code="policy")

        previous = list(term.publications.filter(status=PublicationStatus.PUBLISHED))
        for old in previous:
            release_blocks(SOURCE, old.entries.values_list("pk", flat=True))
            old.status = PublicationStatus.SUPERSEDED
            old.save(update_fields=["status", "updated_at"])

        entries = list(pub.entries.select_related("resource"))
        slots, windows_by_resource = [], defaultdict(list)
        for e in entries:
            for s, t in _occurrences(e, first_day, last_day):
                if t <= now:
                    continue
                slots.append(
                    BookingSlot(
                        resource=e.resource,
                        period=trange(s, t),
                        kind=SlotKind.CLASS,
                        source_type=SOURCE,
                        source_id=e.pk,
                        label=e.label,
                    )
                )
                windows_by_resource[e.resource].append((s, t, e.label))

        # Displace ordinary bookings that the new timetable now overrides.
        displaced = 0
        span = trange(aware(first_day, time.min), aware(last_day + timedelta(days=1), time.min))
        for resource, windows in windows_by_resource.items():
            holding = Booking.objects.filter(resource=resource, status__in=HOLDING_STATUSES, period__overlap=span)
            for b in holding:
                for s, t, label in windows:
                    if b.start < t and s < b.end:
                        reason = f"The published timetable now uses {resource.name} for {label}."
                        displaced += len(displace_bookings(resource, s, t, reason=reason))
                        break
        try:
            with transaction.atomic():
                BookingSlot.objects.bulk_create(slots, batch_size=1000)
        except IntegrityError as exc:
            # A booking committed between our displacement and insert, or a class overlaps a
            # maintenance window. The whole publication rolls back — the previous version stays live.
            raise BookingRejected(
                "Some class times clash with maintenance or a booking made seconds ago. Nothing was published; "
                "check maintenance windows and publish again.",
                code="conflict",
                detail={"db": str(exc)[:300]},
            ) from None

        pub.status = PublicationStatus.PUBLISHED
        pub.published_at = now
        pub.published_by = actor
        pub.occurrence_count = len(slots)
        pub.displaced_count = displaced
        pub.save(
            update_fields=[
                "status",
                "published_at",
                "published_by",
                "occurrence_count",
                "displaced_count",
                "updated_at",
            ]
        )
        if actor:
            from apps.audit.services import record

            record(
                actor,
                "timetable.publish",
                pub,
                after={"version": pub.version, "occurrences": len(slots), "displaced": displaced},
                request=request,
            )
    return {"publication": pub, "occurrences": len(slots), "displaced": displaced, "superseded": len(previous)}


def import_and_publish(term, source, *, actor, fmt_source="csv", request=None) -> dict:
    entries, errors = parse_rows(source, term.institution_id)
    if errors:
        return {"publication": None, "errors": errors}
    pub = stage(term, entries, source=fmt_source, actor=actor)
    result = publish(pub, actor, request=request)
    result["errors"] = []
    return result


def current_publication(term):
    return term.publications.filter(status=PublicationStatus.PUBLISHED).first()


def export_csv(pub: TimetablePublication) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(COLUMNS)
    for e in pub.entries.select_related("resource"):
        w.writerow(
            [
                e.resource.code,
                list(DAYS)[e.weekday].title(),
                f"{e.start_time:%H:%M}",
                f"{e.end_time:%H:%M}",
                e.course_code,
                e.course_title,
                e.section,
                e.faculty,
                e.kind,
            ]
        )
    return out.getvalue()
