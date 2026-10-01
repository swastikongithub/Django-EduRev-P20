"""
Design-system template tags (loaded as builtins).

    {% icon "calendar" %}                    Lucide icon from the static sprite
    {% status_badge booking %}               booking status pill
    {% daystrip schedule %}                  the signature day ribbon
    {{ dt|hm }} {{ dt|dayname }} {{ minutes|duration }}
"""

from datetime import date, datetime, timedelta

from django import template
from django.templatetags.static import static
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def icon(name, size=None, cls=""):
    style = format_html(' style="--ic:{}px"', size) if size else ""
    return format_html(
        '<svg class="ic {}" aria-hidden="true" focusable="false"{}><use href="{}#i-{}"></use></svg>',
        cls,
        style,
        static("img/icons.svg"),
        name,
    )


STATUS_TONE = {
    "draft": ("neutral", "circle-dot"),
    "pending": ("pending", "hourglass"),
    "approved": ("success", "circle-check"),
    "checked_in": ("live", "zap"),
    "completed": ("neutral", "check"),
    "cancelled": ("neutral", "x"),
    "rejected": ("danger", "circle-x"),
    "expired": ("neutral", "timer"),
    "no_show": ("danger", "ban"),
}


@register.simple_tag
def status_badge(booking):
    tone, ic = STATUS_TONE.get(booking.status, ("neutral", "circle-dot"))
    return format_html(
        '<span class="badge badge--{}">{}{}</span>', tone, icon(ic), booking.get_status_display()
    )


@register.filter
def hm(value):
    if not value:
        return ""
    return timezone.localtime(value).strftime("%H:%M")


@register.filter
def dayname(value):
    """Today / Tomorrow / Mon 12 Oct."""
    if not value:
        return ""
    d = timezone.localtime(value).date() if isinstance(value, datetime) else value
    today = timezone.localdate()
    if d == today:
        return "Today"
    if d == today + timedelta(days=1):
        return "Tomorrow"
    if d == today - timedelta(days=1):
        return "Yesterday"
    fmt = "%a %d %b" if abs((d - today).days) < 180 else "%d %b %Y"
    return d.strftime(fmt)


@register.filter
def duration(minutes):
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return ""
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"


@register.filter
def pct(value, digits=0):
    try:
        return f"{float(value) * 100:.{int(digits)}f}%"
    except (TypeError, ValueError):
        return "–"


@register.filter
def inr(value):
    """Indian digit grouping: 12,34,567."""
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return "–"
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + "₹" + s


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.inclusion_tag("components/daystrip.html")
def daystrip(schedule, start_hour=8, end_hour=21, compact=True, now=None):
    """
    Render a DaySchedule as a proportional ribbon: each block positioned by its time,
    so a 2-hour class is visibly twice as long as a 1-hour booking.
    """
    if schedule is None:
        return {"segments": [], "compact": compact}
    d: date = schedule.day
    span_start = timezone.make_aware(datetime.combine(d, datetime.min.time()), timezone.get_current_timezone())
    lo = span_start + timedelta(hours=start_hour)
    hi = span_start + timedelta(hours=end_hour)
    total = (hi - lo).total_seconds()

    def pos(t):
        return max(0.0, min(100.0, (t - lo).total_seconds() / total * 100))

    closed = []
    cursor = lo
    for o, c in sorted(schedule.intervals):
        if o > cursor:
            closed.append((pos(cursor), pos(o)))
        cursor = max(cursor, c)
    if cursor < hi:
        closed.append((pos(cursor), 100.0))
    segments = [
        {"left": left, "width": right - left, "kind": "closed", "label": "Closed"} for left, right in closed if right > left
    ]
    for b in schedule.blocks:
        left, right = pos(b.start), pos(b.end)
        if right > left:
            segments.append(
                {
                    "left": left,
                    "width": right - left,
                    "kind": b.kind,
                    "label": f"{hm(b.start)}–{hm(b.end)} {b.label}",
                }
            )
    now = now or timezone.now()
    now_pos = pos(now) if lo <= now <= hi else None
    hours = [{"left": pos(lo + timedelta(hours=h)), "label": f"{start_hour + h}"} for h in range(0, end_hour - start_hour + 1, 3)]
    return {"segments": segments, "now_pos": now_pos, "hours": hours, "compact": compact}


@register.simple_tag
def initials_avatar(user, size="md"):
    return format_html('<span class="avatar avatar--{}" aria-hidden="true">{}</span>', size, user.initials)


@register.simple_tag(takes_context=True)
def active(context, *prefixes):
    path = context["request"].path
    return mark_safe(' aria-current="page"') if any(path.startswith(p) for p in prefixes) else ""


@register.simple_tag(takes_context=True)
def active_any(context, prefixes):
    return active(context, *prefixes)


ACCENT_ART = {"orange": "orange", "blue": "blue", "indigo": "indigo", "green": "green", "ink": "ink", "amber": "amber"}


@register.simple_tag
def resource_photo(resource, size="sm", cls=""):
    """Uploaded photo, else the curated photograph for its art key, else a branded tile with the type icon."""
    if resource.image:
        return format_html('<img src="{}" alt="" loading="lazy" decoding="async" class="{}">', resource.image.url, cls)
    if resource.art:
        suffix = "-sm" if size == "sm" else ""
        src = static(f"img/resources/{resource.art}{suffix}.webp")
        return format_html('<img src="{}" alt="" loading="lazy" decoding="async" width="{}" height="{}" class="{}">', src,
                           480 if size == "sm" else 960, 320 if size == "sm" else 640, cls)
    accent = ACCENT_ART.get(resource.type.accent, "orange")
    return format_html('<div class="art art--{}">{}</div>', accent, icon(resource.type.icon))


@register.simple_tag
def slot_times(step=30, first=6, last=23):
    """HH:MM options for time pickers on the resource's slot grid."""
    out = []
    m = first * 60
    while m <= last * 60:
        out.append(f"{m // 60:02d}:{m % 60:02d}")
        m += int(step)
    return out
