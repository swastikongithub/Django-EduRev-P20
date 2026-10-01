"""
Server-rendered charts for the Insights dashboard — no chart library, no script (CSP is
``script-src 'self'``), and every colour comes from CSS classes so light and dark mode both work.

Each chart is a *hybrid* figure: the marks are an inline SVG whose x-axis stretches to the
container (``preserveAspectRatio="none"``, strokes kept at 2 px with ``non-scaling-stroke``),
while every piece of text — axis ticks, end labels — is HTML positioned in percentages. Text
therefore stays at the page's type size from a 360 px phone to a 1440 px monitor, which a
scaled ``viewBox`` cannot do.

    svg_hours(days, uid)        booked hours (columns) + used hours (line), one hours axis
    svg_utilisation(days, uid)  utilisation % (area + line) with the period average
    hours_chart(days)           the figure: y ticks + svg_hours + end dot
    utilisation_chart(days)     the figure: y ticks + svg_utilisation + end label + x ticks

Hours and utilisation are two charts stacked on one shared x (small multiples), never one chart
with two y-scales. Each day carries a full-height hit area with a ``<title>`` that reads out every
series for that day, so hovering anywhere over a date explains it; the page also renders the same
numbers as a visually hidden table.

Palette (validated with the dataviz six-checks script against both surfaces):
slot 1 ``--viz-1`` = saffron-600 (booked, utilisation), slot 2 ``--viz-2`` = indigo-700 light /
indigo-500 dark (used). Saffron-500 itself fails 3:1 on white as a mark, so charts use step 600.
"""

from __future__ import annotations

import math
from datetime import date

from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe

W = 1000  # viewBox width; stretched horizontally to whatever the container is
HOURS_H = 200  # plot heights in CSS px (viewBox height == rendered height, so y is never scaled)
UTIL_H = 120
NS = "http://www.w3.org/2000/svg"


# ── Number helpers ──────────────────────────────────────────────────────────


def fmt_num(v, digits: int = 1) -> str:
    """1,240 / 86.5 / 0 — thousands-comma'd, decimals only when they carry information."""
    if v is None:
        return "–"
    v = float(v)
    if abs(v) >= 100 or digits == 0 or v == int(v):
        return f"{v:,.0f}"
    return f"{v:,.{digits}f}"


def nice_scale(vmax: float, ticks: int = 4) -> tuple[float, list[float]]:
    """A clean axis top (1/2/2.5/5 × 10ⁿ steps) at or above ``vmax`` and its tick values."""
    if not vmax or vmax <= 0:
        return 4.0, [0.0, 1.0, 2.0, 3.0, 4.0]
    raw = vmax / ticks
    mag = 10 ** math.floor(math.log10(raw))
    step = mag * 10
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= raw:
            step = m * mag
            break
    top = step * math.ceil(vmax / step - 1e-9)
    return top, [round(step * i, 6) for i in range(round(top / step) + 1)]


def _f(v: float) -> str:
    """Compact coordinate."""
    return f"{v:.2f}".rstrip("0").rstrip(".")


def short_date(d: date) -> str:
    return f"{d.day} {d:%b}"


def day_label(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def _x_ticks(n: int) -> list[int]:
    """At most ~7 date labels, anchored on the last day so 'yesterday' is always labelled."""
    if n <= 0:
        return []
    step = max(1, math.ceil(n / 7))
    return sorted(i for i in range(n - 1, -1, -step))


def _closed(day: dict) -> bool:
    return not (day.get("open_hours") or day.get("class_hours"))


# ── SVG pieces ──────────────────────────────────────────────────────────────


def _svg_open(uid: str, height: int, title: str, desc: str) -> str:
    return format_html(
        '<svg xmlns="{}" class="vz__svg" viewBox="0 0 {} {}" preserveAspectRatio="none" role="img" '
        'aria-labelledby="{}-t {}-d" focusable="false"><title id="{}-t">{}</title><desc id="{}-d">{}</desc>',
        NS,
        W,
        height,
        uid,
        uid,
        uid,
        title,
        uid,
        desc,
    )


def _grid(values, top: float, height: int) -> str:
    lines = "".join(
        f'<line x1="0" x2="{W}" y1="{_f(height - v / top * height)}" y2="{_f(height - v / top * height)}" '
        'vector-effect="non-scaling-stroke"/>'
        for v in values
    )
    return f'<g class="vz__grid" aria-hidden="true">{lines}</g>'


def _closed_bands(days, band: float, height: int) -> str:
    rects = "".join(
        f'<rect x="{_f(i * band)}" y="0" width="{_f(band)}" height="{height}"/>'
        for i, d in enumerate(days)
        if _closed(d)
    )
    return f'<g class="vz__closed" aria-hidden="true">{rects}</g>' if rects else ""


def _column(x: float, w: float, y: float, base: float) -> str:
    """A column with a rounded data end (4 px tall corners) and a square baseline."""
    h = base - y
    if h <= 0:
        return ""
    ry = min(4.0, h)
    rx = min(w / 2, 3.0)
    return (
        f'<path d="M{_f(x)} {_f(base)}V{_f(y + ry)}Q{_f(x)} {_f(y)} {_f(x + rx)} {_f(y)}'
        f'H{_f(x + w - rx)}Q{_f(x + w)} {_f(y)} {_f(x + w)} {_f(y + ry)}V{_f(base)}Z"/>'
    )


def _hits(days, band: float, height: int, titles) -> str:
    out = "".join(
        format_html(
            '<rect class="vz__hit" x="{}" y="0" width="{}" height="{}"><title>{}</title></rect>',
            _f(i * band),
            _f(band),
            height,
            t,
        )
        for i, t in enumerate(titles)
    )
    return f'<g class="vz__hits">{out}</g>'


def _day_title(d: dict) -> str:
    if _closed(d):
        return f"{day_label(d['date'])}: closed"
    return (
        f"{day_label(d['date'])}: {fmt_num(d['booked_hours'])} h booked, {fmt_num(d['used_hours'])} h used, "
        f"{fmt_num(d['utilisation_pct'])} % utilisation"
        + (f", {d['no_shows']} no-show{'s' if d['no_shows'] != 1 else ''}" if d.get("no_shows") else "")
    )


def svg_hours(days: list[dict], uid: str = "vz-hours", top: float | None = None) -> SafeString:
    """Booked hours as columns (slot 1) and used hours as a 2 px line (slot 2), one hours axis."""
    n = len(days)
    vmax = max([max(d["booked_hours"], d["used_hours"]) for d in days] or [0])
    if top is None:
        top, _ = nice_scale(vmax)
    _, ticks = nice_scale(top)
    band = W / max(n, 1)
    bar_w = min(band * 0.62, 24.0)
    total_booked = sum(d["booked_hours"] for d in days)
    total_used = sum(d["used_hours"] for d in days)
    desc = (
        f"Daily booked and used hours over {n} days from {short_date(days[0]['date'])} to "
        f"{short_date(days[-1]['date'])}: {fmt_num(total_booked)} h booked, {fmt_num(total_used)} h used."
        if days
        else "No days in range."
    )

    def y(v):
        return HOURS_H - (v / top) * HOURS_H if top else HOURS_H

    cols = "".join(
        _column(i * band + (band - bar_w) / 2, bar_w, y(d["booked_hours"]), HOURS_H) for i, d in enumerate(days)
    )
    pts = " ".join(f"{_f((i + 0.5) * band)},{_f(y(d['used_hours']))}" for i, d in enumerate(days))
    parts = [
        _svg_open(uid, HOURS_H, "Booked and used hours per day", desc),
        _closed_bands(days, band, HOURS_H),
        _grid(ticks, top, HOURS_H),
        f'<g class="vz__bars">{cols}</g>',
        f'<polyline class="vz__line vz__line--2" points="{pts}" vector-effect="non-scaling-stroke"/>' if n > 1 else "",
        _hits(days, band, HOURS_H, [_day_title(d) for d in days]),
        "</svg>",
    ]
    return mark_safe("".join(parts))  # noqa: S308 - every interpolated string is escaped or numeric


def svg_utilisation(days: list[dict], uid: str = "vz-util", average: float | None = None) -> SafeString:
    """Utilisation % per day as a 10 % area wash under a 2 px line, plus a hairline at the average."""
    n = len(days)
    band = W / max(n, 1)

    def y(v):
        return UTIL_H - (min(v, 100.0) / 100.0) * UTIL_H

    xs = [(i + 0.5) * band for i in range(n)]
    ys = [y(d["utilisation_pct"]) for d in days]
    line = " ".join(f"{_f(x)},{_f(v)}" for x, v in zip(xs, ys, strict=True))
    area = (
        f"M{_f(xs[0])} {UTIL_H}L"
        + "L".join(f"{_f(x)} {_f(v)}" for x, v in zip(xs, ys, strict=True))
        + (f"L{_f(xs[-1])} {UTIL_H}Z")
        if n
        else ""
    )
    desc = (
        f"Daily utilisation from {short_date(days[0]['date'])} to {short_date(days[-1]['date'])}"
        + (f", averaging {fmt_num(average)} % on open days." if average is not None else ".")
        if days
        else "No days in range."
    )
    parts = [
        _svg_open(uid, UTIL_H, "Utilisation per day", desc),
        _closed_bands(days, band, UTIL_H),
        _grid([0, 50, 100], 100, UTIL_H),
        f'<path class="vz__area" d="{area}"/>' if n > 1 else "",
        (
            f'<line class="vz__avg" x1="0" x2="{W}" y1="{_f(y(average))}" y2="{_f(y(average))}" '
            'vector-effect="non-scaling-stroke"/>'
        )
        if average is not None
        else "",
        f'<polyline class="vz__line vz__line--1" points="{line}" vector-effect="non-scaling-stroke"/>' if n > 1 else "",
        _hits(days, band, UTIL_H, [_day_title(d) for d in days]),
        "</svg>",
    ]
    return mark_safe("".join(parts))  # noqa: S308 - every interpolated string is escaped or numeric


# ── Figures (SVG + HTML text) ───────────────────────────────────────────────


def _y_axis(ticks, top: float, unit: str) -> str:
    spans = "".join(
        format_html('<span style="bottom:{}%">{}{}</span>', _f(v / top * 100), fmt_num(v), unit) for v in ticks
    )
    return f'<div class="vz__y" aria-hidden="true">{spans}</div>'


def _x_axis(days) -> str:
    n = len(days)
    out = []
    ticks = _x_ticks(n)
    for k, i in enumerate(ticks):
        pos = (i + 0.5) / n * 100
        edge = " is-first" if pos < 6 else " is-last" if pos > 94 else ""
        if (len(ticks) - 1 - k) % 2:  # every other label, counted from the last, drops out on phones
            edge += " is-minor"
        out.append(
            format_html('<span class="vz__xt{}" style="left:{}%">{}</span>', edge, _f(pos), short_date(days[i]["date"]))
        )
    return f'<div class="vz__x" aria-hidden="true">{"".join(out)}</div>'


def _dot(cls: str, x_pct: float, y_px: float) -> str:
    return format_html(
        '<span class="vz__dot {}" style="left:{}%;top:{}px" aria-hidden="true"></span>', cls, _f(x_pct), _f(y_px)
    )


def hours_chart(days: list[dict], uid: str = "vz-hours") -> SafeString:
    vmax = max([max(d["booked_hours"], d["used_hours"]) for d in days] or [0])
    top, ticks = nice_scale(vmax)
    n = len(days)
    end = ""
    if n:
        last = days[-1]
        end = _dot("vz__dot--2", (n - 0.5) / n * 100, HOURS_H - last["used_hours"] / top * HOURS_H)
    return mark_safe(  # noqa: S308 - assembled from escaped parts
        f'<div class="vz" style="--plot-h:{HOURS_H}px">{_y_axis(ticks, top, " h")}'
        f'<div class="vz__plot">{svg_hours(days, uid, top)}{end}</div></div>'
    )


def utilisation_chart(days: list[dict], uid: str = "vz-util", average: float | None = None) -> SafeString:
    n = len(days)
    end = ""
    avg_label = ""
    if n:
        last = days[-1]
        y = UTIL_H - min(last["utilisation_pct"], 100) / 100 * UTIL_H
        end = _dot("vz__dot--1", (n - 0.5) / n * 100, y) + format_html(
            '<span class="vz__end" style="top:{}px">{} %</span>', _f(y), fmt_num(last["utilisation_pct"])
        )
    if average is not None:
        avg_label = format_html(
            '<span class="vz__avglabel" style="bottom:{}%">avg {} %</span>', _f(min(average, 100)), fmt_num(average)
        )
    return mark_safe(  # noqa: S308 - assembled from escaped parts
        f'<div class="vz vz--util" style="--plot-h:{UTIL_H}px">{_y_axis([0, 50, 100], 100, " %")}'
        f'<div class="vz__plot">{svg_utilisation(days, uid, average)}{end}{avg_label}</div>'
        f"{_x_axis(days)}</div>"
    )


__all__ = [
    "fmt_num",
    "hours_chart",
    "nice_scale",
    "svg_hours",
    "svg_utilisation",
    "utilisation_chart",
]
