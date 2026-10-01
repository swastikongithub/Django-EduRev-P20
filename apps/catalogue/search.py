"""
Resource discovery.

`parse(text)` turns what people actually type — "lab for 40 tomorrow after 3pm",
"projector block 34", "basketball court free now" — into structured filters, and
reports back how it understood the query so the UI can show (and let people undo)
each interpretation. Whatever words are left over go to PostgreSQL full-text search
(weighted SearchVector) with a trigram fallback for typos ("semnar hall").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector, TrigramSimilarity
from django.db.models import F, Q, TextField, Value
from django.db.models.functions import Greatest
from django.utils import timezone

# Words that name a resource type (matched against ResourceType.code). Longest phrases first.
TYPE_WORDS = [
    ("computer lab", "computer-lab"),
    ("electronics lab", "electronics-lab"),
    ("seminar hall", "seminar-hall"),
    ("lecture theatre", "lecture-theatre"),
    ("lecture hall", "lecture-theatre"),
    ("meeting room", "meeting-room"),
    ("conference room", "meeting-room"),
    ("auditorium", "seminar-hall"),
    ("seminar", "seminar-hall"),
    ("classroom", "classroom"),
    ("class room", "classroom"),
    ("lab", "computer-lab"),
    ("labs", "computer-lab"),
    ("court", "sports"),
    ("ground", "sports"),
    ("sports", "sports"),
    ("gym", "sports"),
    ("basketball", "sports"),
    ("badminton", "sports"),
    ("football", "sports"),
    ("tennis", "sports"),
    ("cricket", "sports"),
    ("camera", "equipment"),
    ("equipment", "equipment"),
    ("printer", "equipment"),
    ("3d printer", "equipment"),
    ("drone", "equipment"),
    ("vr", "equipment"),
    ("oscilloscope", "equipment"),
    ("microscope", "equipment"),
    ("bus", "vehicle"),
    ("van", "vehicle"),
    ("vehicle", "vehicle"),
    ("studio", "studio"),
    ("room", "classroom"),
]
SPECIFIC_WORDS = {
    "basketball",
    "badminton",
    "football",
    "tennis",
    "cricket",
    "gym",
    "camera",
    "printer",
    "3d printer",
    "drone",
    "vr",
    "oscilloscope",
    "microscope",
    "bus",
    "van",
    "auditorium",
}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


@dataclass
class Intent:
    text: str = ""
    type_codes: list[str] = field(default_factory=list)
    capacity: int | None = None
    building: str | None = None
    day: date | None = None
    start: time | None = None
    end: time | None = None
    free_now: bool = False
    feature_words: list[str] = field(default_factory=list)
    understood: list[tuple[str, str]] = field(default_factory=list)  # (param to clear, human label)


def _t(h, m=0, ampm=None):
    h, m = int(h), int(m or 0)
    if ampm:
        ampm = ampm.lower()
        if ampm.startswith("p") and h < 12:
            h += 12
        if ampm.startswith("a") and h == 12:
            h = 0
    elif h < 7:  # "at 3" on campus means 3 pm
        h += 12
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return time(h, m)


MAX_QUERY_CHARS = 200  # longer than any real search; also bounds the full-text query

TIME = r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?"


def parse(text: str, *, today: date | None = None, feature_names: list[str] | None = None) -> Intent:
    today = today or timezone.localdate()
    it = Intent()
    # Whitespace runs collapse and the query is capped before any pattern runs: several patterns
    # scan `\s*` after digits, which is quadratic over a long run of spaces (SEC-08).
    s = " " + " ".join((text or "").lower().split())[:MAX_QUERY_CHARS] + " "

    def cut(pattern):
        nonlocal s
        m = re.search(pattern, s)
        if m:
            s = s[: m.start()] + " " + s[m.end() :]
        return m

    if cut(r"\b(free|available|open)\s+(right\s+)?now\b|\bright now\b|\bnow\b"):
        it.free_now = True
        it.understood.append(("now", "Free right now"))

    m = cut(
        r"\b(?:for|seats?|capacity|of)\s+(\d{1,4})\b(?:\s*(?:people|persons|students|seats|pax))?|\b(\d{1,4})\s*(?:people|persons|students|seats|pax)\b"
    )
    if m:
        it.capacity = int(m.group(1) or m.group(2))
        it.understood.append(("people", f"{it.capacity}+ people"))

    m = cut(r"\b(?:block|blk|b)\s*-?\s*(\d{1,3})\b")
    if m:
        it.building = m.group(1)
        it.understood.append(("building", f"Block {it.building}"))

    if cut(r"\btoday\b|\btonight\b"):
        it.day = today
    elif cut(r"\btomorrow\b|\btmrw\b"):
        it.day = today + timedelta(days=1)
    else:
        m = cut(r"\b(?:next\s+|this\s+)?(" + "|".join(DAYS) + r"|mon|tue|wed|thu|fri|sat|sun)\b")
        if m:
            name = m.group(1)[:3]
            target = [d[:3] for d in DAYS].index(name)
            delta = (target - today.weekday()) % 7 or 7
            it.day = today + timedelta(days=delta)
        else:
            m = cut(r"\b(\d{1,2})\s*(" + "|".join(MONTHS) + r")[a-z]*\b")
            if m:
                month = MONTHS.index(m.group(2)) + 1
                year = today.year + (1 if month < today.month else 0)
                try:
                    it.day = date(year, month, int(m.group(1)))
                except ValueError:
                    it.day = None
    if it.day:
        it.understood.append(
            (
                "date",
                "Today"
                if it.day == today
                else "Tomorrow"
                if it.day == today + timedelta(days=1)
                else it.day.strftime("%a %d %b"),
            )
        )

    m = cut(r"\b(?:from\s+)?" + TIME + r"\s*(?:-|–|to|till|until)\s*" + TIME + r"\b")
    if m:
        end_ampm = m.group(6)
        it.start = _t(m.group(1), m.group(2), m.group(3) or end_ampm)
        it.end = _t(m.group(4), m.group(5), end_ampm)
    else:
        m = cut(r"\b(?:at|after|from|around)\s+" + TIME + r"\b") or cut(
            r"\b" + r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)\b"
        )
        if m:
            it.start = _t(m.group(1), m.group(2), m.group(3))
    if it.start:
        if not it.end:
            it.end = (datetime.combine(today, it.start) + timedelta(hours=1)).time()
        it.understood.append(("from", f"{it.start:%H:%M}–{it.end:%H:%M}"))

    for phrase, code in TYPE_WORDS:
        if re.search(r"\b" + re.escape(phrase) + r"s?\b", s):
            # Generic words ("lab", "court") only pick the type. Specific ones ("microscope",
            # "basketball") pick the type AND stay in the text, so they still narrow the results.
            if phrase not in SPECIFIC_WORDS:
                s = re.sub(r"\b" + re.escape(phrase) + r"s?\b", " ", s)
            if code not in it.type_codes:
                it.type_codes.append(code)
    if it.type_codes:
        it.understood.append(("type", " or ".join(c.replace("-", " ").capitalize() for c in it.type_codes)))

    for fname in feature_names or []:
        key = fname.lower()
        if re.search(r"\b" + re.escape(key) + r"\b", s):
            s = re.sub(r"\b" + re.escape(key) + r"\b", " ", s)
            it.feature_words.append(fname)
    for alias, fname in (
        ("ac", "Air conditioned"),
        ("a/c", "Air conditioned"),
        ("wheelchair", "Wheelchair access"),
        ("smartboard", "Smart board"),
        ("vc", "Video conferencing"),
        ("pcs", None),
    ):
        if fname and fname in (feature_names or []) and re.search(r"\b" + re.escape(alias) + r"\b", s):
            s = re.sub(r"\b" + re.escape(alias) + r"\b", " ", s)
            if fname not in it.feature_words:
                it.feature_words.append(fname)
    for f in it.feature_words:
        it.understood.append(("feature", f))

    leftover = re.sub(r"\b(a|an|the|for|with|in|at|on|and|near|need|want|book|free|available|please|me|i)\b", " ", s)
    it.text = re.sub(r"\s+", " ", leftover).strip()
    return it


def search_vector_expression():
    return (
        SearchVector("name", weight="A", config="english")
        + SearchVector("code", weight="A", config="simple")
        + SearchVector("tagline", weight="B", config="english")
        + SearchVector("description", weight="C", config="english")
    )


def refresh_search_vectors(queryset=None):
    """Recompute the weighted document for resources (name, code, type, block, features, attributes, description)."""
    from .models import Resource

    qs = queryset if queryset is not None else Resource.objects.all()
    for r in qs.select_related("type", "building").prefetch_related("features", "attributes"):
        extra = " ".join(
            [r.type.name, r.type.plural, r.building.name if r.building else "", r.building.code if r.building else ""]
            + [f.name + " " + f.keywords for f in r.features.all()]
            + [f"{a.key} {a.value}" for a in r.attributes.all()]
        )
        Resource.objects.filter(pk=r.pk).update(
            search_vector=search_vector_expression()
            + SearchVector(Value(extra, output_field=TextField()), weight="B", config="english")
        )


def apply_text(queryset, text: str):
    """Full-text match ranked by weight, falling back to trigram similarity for typos."""
    if not text:
        return queryset, False
    query = SearchQuery(text, search_type="websearch", config="english")
    qs = queryset.annotate(
        rank=SearchRank(F("search_vector"), query),
        sim=Greatest(TrigramSimilarity("name", text), TrigramSimilarity("code", text)),
    ).filter(Q(search_vector=query) | Q(sim__gt=0.18))
    return qs.order_by("-rank", "-sim"), True
