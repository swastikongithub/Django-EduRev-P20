"""
M9 — the Insights dashboard (/insights/) and its CSV exports (/insights/export/<report>.csv).

Every number comes from ``apps.analytics.services`` (its module docstring defines the metrics);
this module only decides *scope* (who may see which department, which period), caches the
bundle of service results, and turns them into template-ready rows and one-sentence takeaways.

Scope is enforced here, server-side:
- ``view_campus_analytics`` (facility manager, admin): any department, any resource type.
- ``view_department_analytics`` only (head of department): always their own department —
  a ``?department=`` parameter is ignored, never trusted.

Periods are whole days ending *yesterday*: snapshots are rolled up nightly at 01:15, so today is
never complete. Presets: last 7 / 30 / 90 days and this term; or a custom start/end.
"""

from __future__ import annotations

import csv
import math
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, timedelta

from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.http import urlencode
from django.utils.text import slugify

from apps.accounts.models import Department
from apps.accounts.permissions import has_cap
from apps.catalogue.models import ResourceType
from apps.core.exports import spreadsheet_safe
from apps.core.http import date_param
from apps.core.manage_views import staff_required
from apps.core.templatetags.ui import inr

from . import charts, services
from .charts import fmt_num

ANALYTICS_CAPS = ("view_department_analytics", "view_campus_analytics")
CACHE_SECONDS = 300
CACHE_VERSION = "v2"
TERM_FALLBACK_START = date(2026, 8, 1)
MAX_RANGE_DAYS = 400
PRESETS = {"7": 7, "30": 30, "90": 90}
PERIOD_CHOICES = [("7", "7 days"), ("30", "30 days"), ("90", "90 days"), ("term", "This term")]
HEAT_HOURS = range(6, 23)  # 06:00 … 22:00 columns
HEAT_BINS = 5
TOP_ROWS = 8


# ── Scope ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Scope:
    institution_id: int
    start: date
    end: date
    department_id: int | None = None
    resource_type_id: int | None = None

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def kwargs(self) -> dict:
        return {
            "institution_id": self.institution_id,
            "start": self.start,
            "end": self.end,
            "department_id": self.department_id,
            "resource_type_id": self.resource_type_id,
        }

    def previous(self) -> Scope:
        """The equal-length period immediately before this one."""
        return replace(self, start=self.start - timedelta(days=self.days), end=self.start - timedelta(days=1))


@dataclass
class Filters:
    scope: Scope
    period: str
    campus: bool
    department: Department | None
    resource_type: ResourceType | None
    group: str  # "department" | "building"
    departments: list
    types: list
    errors: list
    see_people: bool

    def query(self, **overrides) -> str:
        """The querystring that reproduces this view (used by preset links and CSV links)."""
        params = {"period": self.period}
        if self.period == "custom":
            params |= {"start": self.scope.start.isoformat(), "end": self.scope.end.isoformat()}
        if self.campus and self.department:
            params["department"] = self.department.code
        if self.resource_type:
            params["type"] = self.resource_type.code
        params["by"] = self.group
        params |= overrides
        return urlencode({k: v for k, v in params.items() if v not in (None, "")})


def _term_start(institution_id, today: date) -> date:
    from apps.timetable.models import AcademicTerm

    term = (
        AcademicTerm.objects.filter(institution_id=institution_id, starts__lte=today, ends__gte=today)
        .order_by("-starts")
        .values_list("starts", flat=True)
        .first()
    )
    return term or TERM_FALLBACK_START


def _period(q, institution_id) -> tuple[str, date, date, list[str]]:
    today = timezone.localdate()
    last = today - timedelta(days=1)
    errors: list[str] = []
    period = q.get("period") or "30"
    start = end = None
    if period == "term":
        start, end = min(_term_start(institution_id, today), last), last
    elif period in PRESETS:
        start, end = last - timedelta(days=PRESETS[period] - 1), last
    else:
        period = "custom"

    raw_start, raw_end = q.get("start"), q.get("end")
    if raw_start or raw_end:
        cs, ce = date_param(raw_start, today=today), date_param(raw_end, today=today)
        if cs is None or ce is None:
            errors.append("Enter both dates as day, month and year to use a custom range.")
        else:
            ce = min(ce, today)
            if (cs, ce) != (start, end):
                if cs > ce:
                    errors.append("The start date is after the end date, so the last 30 days are shown instead.")
                elif (ce - cs).days + 1 > MAX_RANGE_DAYS:
                    errors.append(f"Custom ranges can cover up to {MAX_RANGE_DAYS} days. Pick a shorter range.")
                else:
                    period, start, end = "custom", cs, ce
    if start is None:
        period, start, end = "30", last - timedelta(days=29), last
    return period, start, end, errors


def _filters(request) -> Filters:
    user = request.user
    q = request.GET
    inst = user.institution_id
    campus = has_cap(user, "view_campus_analytics")
    period, start, end, errors = _period(q, inst)

    types = list(ResourceType.objects.filter(institution_id=inst).order_by("name").only("id", "code", "name", "plural"))
    rtype = next((t for t in types if t.code == q.get("type")), None)
    if campus:
        departments = list(Department.objects.filter(institution_id=inst).order_by("name").only("id", "code", "name"))
        department = next((d for d in departments if d.code == q.get("department")), None)
    else:
        # Department-scoped analysts are locked to their own department, whatever the URL says.
        departments = []
        department = user.department
    group = q.get("by")
    if group not in ("department", "building"):
        group = "department" if campus and department is None else "building"
    scope = Scope(inst, start, end, department.pk if department else None, rtype.pk if rtype else None)
    return Filters(
        scope=scope,
        period=period,
        campus=campus,
        department=department,
        resource_type=rtype,
        group=group,
        departments=departments,
        types=types,
        errors=errors,
        see_people=campus or has_cap(user, "approve_bookings"),
    )


# ── Data (cached per scope) ─────────────────────────────────────────────────


def _cache_key(scope: Scope, group: str) -> str:
    s = scope
    return (
        f"insights:{CACHE_VERSION}:{s.institution_id}:{s.department_id}:{s.resource_type_id}:{s.start}:{s.end}:{group}"
    )


def _open_days(series: list[dict]) -> int:
    return sum(1 for d in series if d["open_hours"] or d["class_hours"])


def _compute(scope: Scope, group: str) -> dict:
    kw = scope.kwargs()
    prev = scope.previous().kwargs()
    now = timezone.now()
    # Quotas are a live gauge: for periods that run to yesterday show the window we are in now.
    live = scope.end >= timezone.localdate() - timedelta(days=1)
    return {
        "computed_at": now,
        "overview": services.overview(**kw),
        "previous": services.overview(**prev),
        "previous_days": _open_days(services.daily_series(**prev)),
        "series": services.daily_series(**kw),
        "by_type": services.utilisation_by("type", **kw),
        "by_group": services.utilisation_by(group, **kw),
        "idle": services.idle_capacity_ranking(**kw, limit=10),
        "heatmap": services.heatmap(**kw),
        "no_shows": services.no_show_rates(**kw),
        "demand": services.demand_vs_supply(**kw),
        "approvals": services.approval_turnaround(**kw),
        "maintenance": services.maintenance_downtime(**kw),
        "quotas": services.department_quota_consumption(**kw, at=now if live else None),
    }


def report_data(scope: Scope, group: str) -> dict:
    """Every service result the dashboard needs, cached for five minutes per (scope, period, grouping)."""
    key = _cache_key(scope, group)
    data = cache.get(key)
    if data is None:
        data = _compute(scope, group)
        cache.set(key, data, CACHE_SECONDS)
    return data


# ── Presentation: wording ───────────────────────────────────────────────────


def _plural(n, word: str, plural: str | None = None) -> str:
    return f"{fmt_num(n, 0)} {word if n == 1 else (plural or word + 's')}"


def _period_phrase(f: Filters) -> str:
    if f.period in PRESETS:
        return f"the last {f.scope.days} days"
    if f.period == "term":
        return "this term"
    return f"{charts.short_date(f.scope.start)} to {charts.short_date(f.scope.end)}"


def _type_names(f: Filters) -> dict:
    return {t.pk: (t.plural or t.name) for t in f.types}


KPI_SPECS = [
    # key, label, icon, unit, delta kind, higher is better
    ("utilisation_pct", "Utilisation", "gauge", "%", "pts", True),
    ("realised_pct", "Realised utilisation", "circle-check", "%", "pts", True),
    ("booked_hours", "Booked hours", "calendar-check", "h", "rel", True),
    ("idle_hours", "Idle hours", "hourglass", "h", "rel", False),
    ("no_show_rate_pct", "No-show rate", "ban", "%", "pts", False),
    ("avg_turnaround_hours", "Approval turnaround", "timer", "h", "abs", False),
]


def _kpis(ov: dict, prev: dict, f: Filters, coverage: tuple[int, int]) -> list[dict]:
    """``coverage`` = (days with data now, days with data in the previous period)."""
    hints = {
        "utilisation_pct": "Classes and bookings, of usable time",
        "realised_pct": "Time actually used after check-in",
        "booked_hours": _plural(ov["bookings"], "booking"),
        "idle_hours": "Open but nobody booked it",
        "no_show_rate_pct": f"{fmt_num(ov['no_shows'], 0)} of {_plural(ov['bookings'], 'booking')}",
        "avg_turnaround_hours": f"{fmt_num(ov['pending_approvals'], 0)} waiting now",
    }
    versus = f"vs previous {f.scope.days} days"
    now_days, prev_days = coverage
    # Totals (hours) only compare like with like when the earlier period has as many days on record;
    # rates (percentages, averages) compare fine either way.
    partial = prev_days < now_days * 0.8
    out = []
    for key, label, icon, unit, kind, higher_good in KPI_SPECS:
        cur, old = ov.get(key), prev.get(key)
        delta = {"tone": "", "dir": "", "text": "No earlier data to compare"}
        if kind == "rel" and partial and prev.get("resources"):
            delta = {"tone": "", "dir": "", "text": f"Earlier data covers only {_plural(prev_days, 'day')}"}
        elif cur is not None and old is not None and prev.get("resources"):
            if kind == "pts":
                diff, text = cur - old, f"{fmt_num(abs(cur - old))} pts"
            elif kind == "abs":
                diff, text = cur - old, f"{fmt_num(abs(cur - old))} h"
            else:
                diff = cur - old
                text = f"{fmt_num(abs(diff) / old * 100, 0)} %" if old else f"{fmt_num(abs(diff))} h"
            if abs(diff) < 0.05:
                delta = {"tone": "", "dir": "", "text": f"No change {versus}"}
            else:
                good = (diff > 0) == higher_good
                delta = {
                    "tone": "up" if good else "down",
                    "dir": "up" if diff > 0 else "down",
                    "text": f"{'Up' if diff > 0 else 'Down'} {text} {versus}",
                }
        out.append(
            {
                "label": label,
                "icon": icon,
                "value": "–" if cur is None else fmt_num(cur),
                "unit": "" if cur is None else unit,
                "hint": hints[key],
                "delta": delta,
            }
        )
    return out


def _kpi_takeaway(ov: dict, prev: dict, f: Filters) -> str:
    s = f"Resources were claimed {fmt_num(ov['utilisation_pct'])} % of the time they could be used in {_period_phrase(f)}"
    if prev.get("resources"):
        diff = ov["utilisation_pct"] - prev["utilisation_pct"]
        if abs(diff) >= 0.05:
            s += f", {'up' if diff > 0 else 'down'} {fmt_num(abs(diff))} points on the period before"
    s += "."
    if ov["booked_hours"]:
        lost = max(0.0, ov["utilisation_pct"] - ov["realised_pct"])
        s += f" No-shows and early exits took {fmt_num(lost)} points off what was actually used."
    return s


# ── Presentation: sections ──────────────────────────────────────────────────


def _trend(series: list[dict], f: Filters) -> dict:
    open_days = [d for d in series if d["open_hours"] or d["class_hours"]]
    if not open_days or not any(d["booked_hours"] or d["class_hours"] for d in open_days):
        return {"empty": True}
    avg = round(sum(d["utilisation_pct"] for d in open_days) / len(open_days), 1)
    peak = max(open_days, key=lambda d: (d["utilisation_pct"], d["date"]))
    booked = sum(d["booked_hours"] for d in series)
    used = sum(d["used_hours"] for d in series)
    take = (
        f"Utilisation averaged {fmt_num(avg)} % on open days and peaked at {fmt_num(peak['utilisation_pct'])} % "
        f"on {charts.day_label(peak['date'])}."
    )
    if booked:
        take += f" {fmt_num(used / booked * 100, 0)} % of booked hours were actually used."
    return {
        "empty": False,
        "takeaway": take,
        "hours_svg": charts.hours_chart(series, "vz-hours"),
        "util_svg": charts.utilisation_chart(series, "vz-util", average=avg),
        "booked": booked,
        "used": used,
        "rows": series,
        "has_closed": len(open_days) < len(series),
    }


def _bars(rows: list[dict], label_key="label") -> list[dict]:
    return [
        {
            "label": r[label_key],
            "pct": min(r["utilisation_pct"], 100),
            "value": f"{fmt_num(r['utilisation_pct'])} %",
            "sub": f"{_plural(r['resources'], 'resource')}, {fmt_num(r['booked_hours'])} h booked",
            "title": (
                f"{r[label_key]}: {fmt_num(r['utilisation_pct'])} % utilised, {fmt_num(r['realised_pct'])} % realised, "
                f"{fmt_num(r['idle_hours'])} h idle"
            ),
        }
        for r in rows
    ]


def _by_type(rows: list[dict], f: Filters) -> dict:
    if not rows:
        return {"empty": True}
    names = _type_names(f)
    for r in rows:
        r["display"] = names.get(r["key"], r["label"])
    top, low = rows[0], rows[-1]
    take = f"{top['display']} are the busiest at {fmt_num(top['utilisation_pct'])} %"
    take += f"; {low['display']} the least used at {fmt_num(low['utilisation_pct'])} %." if len(rows) > 1 else "."
    return {"empty": False, "takeaway": take, "bars": _bars(rows, "display")}


def _by_group(rows: list[dict], f: Filters) -> dict:
    noun = f.group
    if not rows:
        return {"empty": True, "noun": noun}
    top = rows[0]
    take = f"{top['label']} leads at {fmt_num(top['utilisation_pct'])} %"
    if len(rows) > 1:
        spread = top["utilisation_pct"] - rows[-1]["utilisation_pct"]
        take += f", {fmt_num(spread)} points ahead of {rows[-1]['label']}."
    else:
        take += "."
    shown = rows[:10]
    return {
        "empty": False,
        "noun": noun,
        "takeaway": take,
        "bars": _bars(shown),
        "more": len(rows) - len(shown),
    }


def _heatmap(hm: dict, f: Filters) -> dict:
    s = f.scope
    weekdays = Counter((s.start + timedelta(days=i)).weekday() for i in range(s.days))
    grid = []
    vmax = 0.0
    for row in hm["rows"]:
        n = weekdays.get(row["weekday"], 0)
        vals = [(h, row["minutes"][h] / 60 / n if n else 0.0) for h in HEAT_HOURS]
        vmax = max([vmax, *(v for _, v in vals)])
        grid.append((row, vals, n))
    if not hm["total"] or vmax <= 0:
        return {"empty": True}
    rows = []
    peak = (0.0, None, None)
    for row, vals, n in grid:
        cells = []
        for h, v in vals:
            level = 0 if v <= 0 else min(HEAT_BINS, max(1, math.ceil(v * HEAT_BINS / vmax)))
            cells.append(
                {
                    "level": int(level),
                    "value": v,
                    "title": f"{row['label']} {h:02d}:00–{h + 1:02d}:00: {fmt_num(v)} resources busy on average",
                }
            )
            if v > peak[0]:
                peak = (v, row["label"], h)
        rows.append({"label": row["label"], "cells": cells, "total": row["total"] / 60 / n if n else 0.0})
    busiest = max(rows, key=lambda r: r["total"])
    quietest = min(rows, key=lambda r: r["total"])
    take = (
        f"The peak is {peak[1]} {peak[2]:02d}:00, with {fmt_num(peak[0])} resources busy on average; "
        f"{busiest['label']} is the busiest day and {quietest['label']} the quietest."
    )
    step = vmax / HEAT_BINS
    legend = [{"level": i, "label": f"up to {fmt_num(step * i)}"} for i in range(1, HEAT_BINS + 1)]
    return {
        "empty": False,
        "takeaway": take,
        "hours": [f"{h:02d}" for h in HEAT_HOURS],
        "rows": rows,
        "legend": legend,
    }


def _idle(rows: list[dict], f: Filters) -> dict:
    if not rows:
        return {"empty": True}
    max_score = max(r["idle_cost_score"] for r in rows)
    max_idle = max(r["idle_hours"] for r in rows) or 1
    for i, r in enumerate(rows):
        r["bar"] = (r["idle_cost_score"] / max_score * 100) if max_score else (r["idle_hours"] / max_idle * 100)
        r["lead"] = i == 0
    hero = next((r for r in rows if r["acquisition_cost"] and r["idle_cost_score"] > 0), None)
    headline = None
    if hero:
        headline = (
            f"cost {inr(hero['acquisition_cost'])} and sat idle for {fmt_num(hero['idle_hours'])} of its "
            f"{fmt_num(hero['open_hours'])} open hours in {_period_phrase(f)}, "
            f"{fmt_num(hero['utilisation_pct'])} % utilised. It is the most expensive under-used asset in this view."
        )
    costed = [r for r in rows if r["acquisition_cost"]]
    take = f"The {len(rows)} resources below sat idle for {fmt_num(sum(r['idle_hours'] for r in rows))} h in total"
    take += (
        f"; the {len(costed)} with a recorded cost are worth {inr(sum(r['acquisition_cost'] for r in costed))}."
        if costed
        else ". None has an acquisition cost recorded, so they are ranked by idle hours alone."
    )
    return {
        "empty": False,
        "rows": rows,
        "hero": hero,
        "headline": headline,
        "takeaway": take,
        "by_cost": bool(max_score),
    }


def _demand(rows: list[dict], f: Filters) -> dict:
    rows = [r for r in rows if r["demand"]]
    if not rows:
        return {"empty": True}
    names = _type_names(f)
    max_demand = max(r["demand"] for r in rows)
    for r in rows:
        r["display"] = names.get(r["type_id"], r["type"])
        r["served_w"] = r["bookings"] / max_demand * 100
        r["denied_w"] = r["denied_attempts"] / max_demand * 100
    flagged = [r for r in rows if r["needs_capacity"]]
    if flagged:
        r = flagged[0]
        take = (
            f"{r['display']} turned away {_plural(r['denied_attempts'], 'request')} ({fmt_num(r['denial_rate_pct'])} %) "
            f"— consider adding capacity or opening longer hours."
        )
        if len(flagged) > 1:
            others = ", ".join(x["display"] for x in flagged[1:3])
            take += f" {others} {'also need' if len(flagged) > 2 else 'also needs'} more capacity."
    else:
        worst = max(rows, key=lambda r: r["denial_rate_pct"])
        take = "No resource type turned away enough requests to need more capacity" + (
            f"; the highest denial rate was {worst['display']} at {fmt_num(worst['denial_rate_pct'])} %."
            if worst["denied_attempts"]
            else "."
        )
    return {"empty": False, "rows": rows, "takeaway": take}


def _no_shows(ns: dict, f: Filters) -> dict:
    o = ns["overall"]
    if not o["bookings"]:
        return {"empty": True}
    take = (
        f"{fmt_num(o['rate_pct'])} % of bookings were no-shows ({fmt_num(o['no_shows'], 0)} of "
        f"{fmt_num(o['bookings'], 0)})"
    )
    if ns["by_resource"]:
        r = ns["by_resource"][0]
        take += f"; {r['name']} had the most, {r['no_shows']}."
    else:
        take += "."
    return {
        "empty": False,
        "overall": o,
        "users": ns["by_user"][:TOP_ROWS] if f.see_people else [],
        "resources": ns["by_resource"][:TOP_ROWS],
        "takeaway": take,
    }


def _approvals(a: dict, f: Filters) -> dict:
    if not a["decided"] and not a["pending_now"]:
        return {"empty": True}
    names = _type_names(f)
    types = [t for t in a["by_type"] if t["avg_hours"] is not None]
    max_h = max([t["avg_hours"] for t in types] or [0]) or 1
    for t in types:
        t["display"] = names.get(t["type_id"], t["type"])
        t["bar"] = t["avg_hours"] / max_h * 100
    if a["avg_hours"] is not None:
        take = f"Requests waited {fmt_num(a['avg_hours'])} h on average for a decision"
        take += f"; {types[0]['display']} were slowest at {fmt_num(types[0]['avg_hours'])} h." if types else "."
    else:
        take = "No requests were decided in this period."
    if a["overdue_now"]:
        take += f" {_plural(a['overdue_now'], 'request is', 'requests are')} overdue right now."
    elif a["pending_now"]:
        take += " Nothing in the queue is overdue."
    return {"empty": False, "takeaway": take, "types": types, **{k: a[k] for k in a if k != "by_type"}}


def _maintenance(m: dict, f: Filters) -> dict:
    if not m["windows"]:
        return {"empty": True}
    names = _type_names(f)
    max_h = max([t["hours"] for t in m["by_type"]] or [0]) or 1
    for t in m["by_type"]:
        t["display"] = names.get(t["type_id"], t["type"])
        t["bar"] = t["hours"] / max_h * 100
    worst = m["by_type"][0]
    take = (
        f"Maintenance took {fmt_num(m['total_hours'])} h across {_plural(m['windows'], 'window')}, costing "
        f"{fmt_num(m['lost_open_hours'])} bookable hours; {worst['display']} lost the most ({fmt_num(worst['hours'])} h)."
    )
    return {
        "empty": False,
        "takeaway": take,
        "types": m["by_type"],
        "resources": m["by_resource"][:TOP_ROWS],
        "total_hours": m["total_hours"],
        "lost_open_hours": m["lost_open_hours"],
        "windows": m["windows"],
    }


def _quotas(rows: list[dict], f: Filters) -> dict:
    if not rows:
        return {"empty": True}
    now = timezone.now()
    for r in rows:
        r["level"] = "is-high" if r["pct"] >= 90 else "is-mid" if r["pct"] >= 70 else ""
        code = r["department_code"]
        r["label"] = r["name"] if code.lower() in r["name"].lower() else f"{code}, {r['name']}"
        r["ended"] = r["window_end"] <= now
    top = rows[0]
    near = sum(1 for r in rows if r["pct"] >= 80)
    take = f"The fullest is {top['label']}, at {top['pct']} % of its limit"
    if near > 1:
        take += f"; {_plural(near, 'quota is', 'quotas are')} above 80 %."
    elif top["pct"] < 80:
        take += ", so no department is close to running out."
    else:
        take += "."
    return {"empty": False, "rows": rows, "takeaway": take}


# ── Views ───────────────────────────────────────────────────────────────────


@staff_required(*ANALYTICS_CAPS)
def dashboard(request):
    """GET /insights/ — utilisation, idle capacity, demand and the rest of §10 for the user's scope."""
    f = _filters(request)
    base = {"f": f, "period_choices": PERIOD_CHOICES}
    if not f.campus and f.department is None:
        return render(request, "insights/dashboard.html", {**base, "no_department": True})

    data = report_data(f.scope, f.group)
    ov, prev = data["overview"], data["previous"]
    has_data = bool(ov["resources"])
    preset_links = [
        (key, label, f.query(period=key, start=None, end=None), key == f.period) for key, label in PERIOD_CHOICES
    ]
    ctx = {
        **base,
        "has_data": has_data,
        "computed_at": data["computed_at"],
        "qs": f.query(),
        "preset_links": preset_links,
        "group_links": [(g, g.capitalize(), f.query(by=g), g == f.group) for g in ("department", "building")],
        "scope_label": f.department.name if f.department else "the whole campus",
        "period_phrase": _period_phrase(f),
        "overview": ov,
        "kpis": _kpis(ov, prev, f, (_open_days(data["series"]), data["previous_days"])),
        "kpi_takeaway": _kpi_takeaway(ov, prev, f) if has_data else "",
        "trend": _trend(data["series"], f),
        "by_type": _by_type([dict(r) for r in data["by_type"]], f),
        "by_group": _by_group(data["by_group"], f),
        "heat": _heatmap(data["heatmap"], f),
        "idle": _idle([dict(r) for r in data["idle"]], f),
        "demand": _demand([dict(r) for r in data["demand"]], f),
        "no_shows": _no_shows(data["no_shows"], f),
        "approvals": _approvals({**data["approvals"], "by_type": [dict(t) for t in data["approvals"]["by_type"]]}, f),
        "maintenance": _maintenance(
            {**data["maintenance"], "by_type": [dict(t) for t in data["maintenance"]["by_type"]]}, f
        ),
        "quotas": _quotas([dict(r) for r in data["quotas"]], f),
    }
    return render(request, "insights/dashboard.html", ctx)


# ── CSV exports ─────────────────────────────────────────────────────────────


_safe = spreadsheet_safe  # names in insights rows come from users and custodians


def _util_cols(rows, key_label):
    head = [
        key_label,
        "Resources",
        "Utilisation %",
        "Realised %",
        "Open h",
        "Class h",
        "Booked h",
        "Used h",
        "Idle h",
        "Maintenance h",
        "Bookings",
        "No-shows",
        "No-show %",
        "Cancellations",
        "Denied attempts",
    ]
    body = [
        [
            r["label"],
            r["resources"],
            r["utilisation_pct"],
            r["realised_pct"],
            r["open_hours"],
            r["class_hours"],
            r["booked_hours"],
            r["used_hours"],
            r["idle_hours"],
            r["maintenance_hours"],
            r["bookings"],
            r["no_shows"],
            r["no_show_rate_pct"],
            r["cancellations"],
            r["denied_attempts"],
        ]
        for r in rows
    ]
    return head, body


def _csv_overview(d, f):
    keys = [
        "utilisation_pct",
        "realised_pct",
        "booked_hours",
        "used_hours",
        "idle_hours",
        "open_hours",
        "class_hours",
        "maintenance_hours",
        "released_hours",
        "bookings",
        "no_shows",
        "no_show_rate_pct",
        "cancellations",
        "denied_attempts",
        "resources",
        "pending_approvals",
        "avg_turnaround_hours",
    ]
    return ["Metric", "This period", "Previous period"], [[k, d["overview"].get(k), d["previous"].get(k)] for k in keys]


def _csv_trend(d, f):
    head = [
        "Date",
        "Open h",
        "Class h",
        "Booked h",
        "Used h",
        "Utilisation %",
        "Bookings",
        "No-shows",
        "Cancellations",
        "Denied attempts",
    ]
    return head, [
        [
            r["date"].isoformat(),
            r["open_hours"],
            r["class_hours"],
            r["booked_hours"],
            r["used_hours"],
            r["utilisation_pct"],
            r["bookings"],
            r["no_shows"],
            r["cancellations"],
            r["denied_attempts"],
        ]
        for r in d["series"]
    ]


def _csv_heatmap(d, f):
    return ["Weekday", "Hour", "Booked + class minutes"], [
        [r["label"], f"{h:02d}:00", r["minutes"][h]] for r in d["heatmap"]["rows"] for h in range(24)
    ]


def _csv_idle(d, f):
    head = [
        "Resource",
        "Code",
        "Type",
        "Department",
        "Building",
        "Acquisition cost (INR)",
        "Open h",
        "Booked h",
        "Idle h",
        "Idle %",
        "Utilisation %",
        "Idle cost score",
    ]
    return head, [
        [
            r["name"],
            r["code"],
            r["type"],
            r["department"],
            r["building"],
            r["acquisition_cost"],
            r["open_hours"],
            r["booked_hours"],
            r["idle_hours"],
            r["idle_pct"],
            r["utilisation_pct"],
            r["idle_cost_score"],
        ]
        for r in d["idle"]
    ]


def _csv_demand(d, f):
    head = [
        "Type",
        "Resources",
        "Bookings",
        "Denied attempts",
        "Demand",
        "Denial %",
        "Utilisation %",
        "Booked h",
        "Open h",
        "Needs capacity",
    ]
    return head, [
        [
            r["type"],
            r["resources"],
            r["bookings"],
            r["denied_attempts"],
            r["demand"],
            r["denial_rate_pct"],
            r["utilisation_pct"],
            r["booked_hours"],
            r["open_hours"],
            "yes" if r["needs_capacity"] else "no",
        ]
        for r in d["demand"]
    ]


def _csv_no_show_people(d, f):
    if not f.see_people:
        raise Http404
    return ["Name", "Username", "VID", "Bookings", "No-shows", "No-show %"], [
        [u["name"], u["username"], u["vid"], u["bookings"], u["no_shows"], u["rate_pct"]]
        for u in d["no_shows"]["by_user"]
    ]


def _csv_no_show_resources(d, f):
    return ["Resource", "Bookings", "No-shows", "No-show %"], [
        [r["name"], r["bookings"], r["no_shows"], r["rate_pct"]] for r in d["no_shows"]["by_resource"]
    ]


def _csv_approvals(d, f):
    a = d["approvals"]
    rows = [[t["type"], t["avg_hours"], t["decided"]] for t in a["by_type"]]
    rows.append(["All types", a["avg_hours"], a["decided"]])
    return ["Type", "Average hours to decision", "Decided"], rows


def _csv_maintenance(d, f):
    return ["Resource", "Type", "Downtime h", "Windows", "Bookable hours lost"], [
        [r["name"], r["type"], r["hours"], r["windows"], r["lost_open_hours"]] for r in d["maintenance"]["by_resource"]
    ]


def _csv_quotas(d, f):
    head = [
        "Department",
        "Quota",
        "Resource type",
        "Period",
        "Window start",
        "Window end",
        "Hours used",
        "Max hours",
        "Bookings used",
        "Max bookings",
        "Used %",
    ]
    return head, [
        [
            r["department"],
            r["name"],
            r["resource_type"] or "All",
            r["period_label"],
            r["window_start"].isoformat(),
            r["window_end"].isoformat(),
            r["hours_used"],
            r["max_hours"],
            r["bookings_used"],
            r["max_bookings"],
            r["pct"],
        ]
        for r in d["quotas"]
    ]


EXPORTS = {
    "overview": _csv_overview,
    "trend": _csv_trend,
    "types": lambda d, f: _util_cols(d["by_type"], "Resource type"),
    "groups": lambda d, f: _util_cols(d["by_group"], f.group.capitalize()),
    "heatmap": _csv_heatmap,
    "idle": _csv_idle,
    "demand": _csv_demand,
    "no-shows-people": _csv_no_show_people,
    "no-shows-resources": _csv_no_show_resources,
    "approvals": _csv_approvals,
    "maintenance": _csv_maintenance,
    "quotas": _csv_quotas,
}


@staff_required(*ANALYTICS_CAPS)
def export(request, report: str):
    """GET /insights/export/<report>.csv — the rows behind one dashboard section, same scope rules."""
    builder = EXPORTS.get(report)
    if builder is None:
        raise Http404
    f = _filters(request)
    if not f.campus and f.department is None:
        raise Http404
    head, rows = builder(report_data(f.scope, f.group), f)
    scope = slugify(f.department.code) if f.department else "campus"
    # Some exports name people (no-show rates), so every download is on the audit trail.
    from apps.audit.services import record

    record(
        request.user,
        "insights.export",
        request.user,
        after={"report": report, "scope": scope, "from": f"{f.scope.start}", "to": f"{f.scope.end}"},
        request=request,
    )
    name = f"insights-{report}-{scope}-{f.scope.start:%Y%m%d}-{f.scope.end:%Y%m%d}.csv"
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    resp.write("﻿")  # BOM so Excel opens ₹ and names correctly
    w = csv.writer(resp)
    w.writerow(head)
    for row in rows:
        w.writerow([_safe(v) for v in row])
    return resp
